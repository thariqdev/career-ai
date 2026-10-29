"""Production embeddings: GeminiEmbedder and the retry helper. A fake server stands in for
Google (httpx.MockTransport); no request ever leaves the machine, and no key is real."""

import json

import httpx
import pytest

from app.rag.assistant import configured_embedder
from app.rag.embeddings import (
    DOC_PREFIX,
    QUERY_PREFIX,
    EmbeddingUnavailableError,
    GeminiEmbedder,
    OllamaEmbedder,
    gemini_text,
)
from app.rag.http_retry import MAX_WAIT_SECONDS, retry_wait

KEY = "test-key-not-real"


def _answer(request: httpx.Request, dims: int = 768) -> httpx.Response:
    body = json.loads(request.content)
    return httpx.Response(200, json={"embeddings": [{"values": [0.1] * dims} for _ in body["requests"]]})


def _embedder(handler, sleeps: list[float] | None = None) -> GeminiEmbedder:
    waits = sleeps if sleeps is not None else []
    return GeminiEmbedder(KEY, transport=httpx.MockTransport(handler), sleep=waits.append)


def test_it_sends_768_dimensions_the_right_task_format_and_the_key_in_a_header() -> None:
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return _answer(request)

    vectors = _embedder(handler).embed([DOC_PREFIX + "Python is verified.", QUERY_PREFIX + "my proof"])

    assert len(vectors) == 2 and len(vectors[0]) == 768
    [request] = seen
    body = json.loads(request.content)
    assert request.url.path.endswith("/models/gemini-embedding-2:batchEmbedContents")
    assert request.headers["x-goog-api-key"] == KEY and KEY not in str(request.url)
    assert [r["content"]["parts"][0]["text"] for r in body["requests"]] == [
        "title: none | text: Python is verified.",
        "task: search result | query: my proof",
    ]
    assert {r["outputDimensionality"] for r in body["requests"]} == {768}


def test_large_inputs_are_split_into_batches_of_100() -> None:
    sizes = []

    def handler(request: httpx.Request) -> httpx.Response:
        sizes.append(len(json.loads(request.content)["requests"]))
        return _answer(request)

    assert len(_embedder(handler).embed([f"note {i}" for i in range(230)])) == 230
    assert sizes == [100, 100, 30]


def test_429_is_retried_with_backoff_then_succeeds() -> None:
    answers = iter([httpx.Response(429), httpx.Response(503, headers={"retry-after": "3"})])
    sleeps: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        return next(answers, None) or _answer(request)

    assert len(_embedder(handler, sleeps).embed(["hello"])) == 1
    assert sleeps == [1.0, 3.0]  # doubling first, then the server's Retry-After


def test_it_gives_up_after_the_retries_without_leaking_the_key() -> None:
    sleeps: list[float] = []
    embedder = _embedder(lambda request: httpx.Response(429), sleeps)

    with pytest.raises(EmbeddingUnavailableError, match="Gemini answered 429") as error:
        embedder.embed(["hello"])

    assert len(sleeps) == 4 and KEY not in str(error.value)


def test_a_wrong_key_fails_at_once_and_a_bad_answer_is_rejected() -> None:
    sleeps: list[float] = []
    with pytest.raises(EmbeddingUnavailableError, match="403"):
        _embedder(lambda request: httpx.Response(403), sleeps).embed(["x"])
    assert sleeps == []  # 4xx other than 429 is never retried

    with pytest.raises(EmbeddingUnavailableError, match="size"):
        _embedder(lambda request: _answer(request, dims=3)).embed(["x"])


def test_unreachable_server_becomes_the_usual_unavailable_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no network")

    with pytest.raises(EmbeddingUnavailableError, match="Gemini isn't reachable"):
        _embedder(handler).embed(["x"])


def test_retry_waits_are_capped_and_texts_without_a_prefix_pass_through() -> None:
    assert retry_wait(None, 10) == MAX_WAIT_SECONDS
    assert retry_wait(httpx.Response(429, headers={"retry-after": "600"}), 0) == MAX_WAIT_SECONDS
    assert gemini_text("plain") == "plain"


def test_the_provider_is_chosen_by_env_and_local_stays_on_ollama(monkeypatch: pytest.MonkeyPatch) -> None:
    assert configured_embedder() is None  # nothing set: keyword search only

    monkeypatch.setenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")
    assert isinstance(configured_embedder().inner, OllamaEmbedder)

    monkeypatch.setenv("EMBED_PROVIDER", "gemini")
    assert configured_embedder() is None  # gemini without a key: keyword only, never a crash
    monkeypatch.setenv("GEMINI_API_KEY", KEY)
    embedder = configured_embedder()
    assert isinstance(embedder.inner, GeminiEmbedder) and embedder.name == "gemini-embedding-2"
