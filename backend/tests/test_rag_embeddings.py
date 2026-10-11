"""Tests for RAG stage 66: embeddings, cosine similarity, hybrid search (RRF), fallback.

No Ollama needed: a tiny FAKE embedder stands in for the model. It maps words to a few
"concept" dimensions, so synonyms ("K8s", "Kubernetes", "container orchestration") get
the same direction, which is exactly the property a real embedding model learns. These
tests check our plumbing and maths, not the real model's quality (that's
app/rag/evaluate.py's job once Ollama is installed).
"""

import json
import math

import httpx
import pytest

from app.rag.assistant import NOT_FOUND, retrieve
from app.rag.chunker import Chunk
from app.rag.embeddings import (
    DOC_PREFIX,
    QUERY_PREFIX,
    CachedEmbedder,
    EmbeddingUnavailableError,
    OllamaEmbedder,
    VectorIndex,
    cosine,
    reciprocal_rank_fusion,
)

CONCEPTS = [
    {"kubernetes", "k8s", "container", "orchestration", "pods"},
    {"python", "django", "fastapi"},
    {"job", "jobs", "role", "position", "vacancy"},
    {"proof", "evidence", "verified", "proven"},
    {"learn", "study", "course", "tutorial"},
]


class FakeEmbedder:
    """Bag-of-concepts vectors: one dimension per concept group (all zeros = no known meaning)."""

    name = "fake"

    def __init__(self) -> None:
        self.calls = 0

    def embed(self, texts: list[str]) -> list[list[float]]:
        self.calls += len(texts)
        out = []
        for text in texts:
            text = text.removeprefix(DOC_PREFIX).removeprefix(QUERY_PREFIX)
            words = {w.strip(".,?:!()").lower() for w in text.split()}
            out.append([float(len(words & group)) for group in CONCEPTS])
        return out


class BrokenEmbedder:
    name = "broken"

    def embed(self, texts: list[str]) -> list[list[float]]:
        raise EmbeddingUnavailableError("Ollama isn't reachable (ConnectError).")


# --- the maths -------------------------------------------------------------------------------


def test_cosine_by_hand() -> None:
    assert cosine([1, 0], [1, 0]) == pytest.approx(1.0)  # same direction
    assert cosine([1, 0], [0, 1]) == pytest.approx(0.0)  # unrelated
    assert cosine([1, 0], [-1, 0]) == pytest.approx(-1.0)  # opposite
    # (1,1)·(1,0) = 1;  |(1,1)| = √2, |(1,0)| = 1  ->  1/√2 ≈ 0.7071 (a 45° angle)
    assert cosine([1, 1], [1, 0]) == pytest.approx(1 / math.sqrt(2))
    # Length doesn't matter, only direction: a long note can match a short question.
    assert cosine([10, 10], [1, 1]) == pytest.approx(1.0)
    assert cosine([0, 0], [1, 1]) == 0.0


def test_meaning_search_finds_synonyms_that_keyword_search_cannot() -> None:
    texts = ["Gap: Kubernetes is missing for the Backend job.", "Skill: Python, verified."]

    best, _ = VectorIndex(texts, FakeEmbedder()).search("container orchestration", top_k=2)

    assert best[0] == 0  # meaning found it...
    from app.rag.bm25 import BM25Index

    assert BM25Index(texts).search("container orchestration") == []  # ...words alone couldn't


def test_rrf_by_hand() -> None:
    """BM25 ranks [A, B, C]; meaning ranks [B, D]. With k = 60:
    A = 1/61 = 0.016393     B = 1/62 + 1/61 = 0.032522
    C = 1/63 = 0.015873     D = 1/62 = 0.016129
    B is decent in both lists, so it wins; then A, D, C."""
    A, B, C, D = 0, 1, 2, 3

    fused = reciprocal_rank_fusion([[A, B, C], [B, D]])

    assert [i for i, _ in fused] == [B, A, D, C]
    assert dict(fused)[B] == pytest.approx(1 / 62 + 1 / 61)


# --- caching ------------------------------------------------------------------------------------


def test_each_text_is_embedded_once() -> None:
    inner = FakeEmbedder()
    cached = CachedEmbedder(inner)

    first = cached.embed(["python job", "kubernetes"])
    again = cached.embed(["kubernetes", "python job", "kubernetes"])

    assert inner.calls == 2  # the repeat call cost nothing
    assert again == [first[1], first[0], first[1]]


# --- the Ollama client (faked HTTP) -----------------------------------------------------------


def _ollama(handler) -> OllamaEmbedder:
    return OllamaEmbedder(transport=httpx.MockTransport(handler))


def test_ollama_embedder_sends_one_batch_and_reads_the_vectors() -> None:
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return httpx.Response(200, json={"embeddings": [[0.1, 0.2], [0.3, 0.4]]})

    vectors = _ollama(handler).embed(["a", "b"])

    assert vectors == [[0.1, 0.2], [0.3, 0.4]]
    assert seen == [{"model": "nomic-embed-text", "input": ["a", "b"], "keep_alive": "30m"}]


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(404, json={"error": "model not found"}),
        httpx.Response(200, json={"wrong": "shape"}),
        httpx.Response(200, json={"embeddings": [[0.1]]}),  # 1 vector for 2 texts
    ],
)
def test_bad_ollama_answers_are_unavailable(response: httpx.Response) -> None:
    with pytest.raises(EmbeddingUnavailableError):
        _ollama(lambda request: response).embed(["a", "b"])


def test_unreachable_ollama_is_unavailable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    with pytest.raises(EmbeddingUnavailableError, match="isn't reachable"):
        _ollama(handler).embed(["a"])


# --- retrieval modes in the assistant ---------------------------------------------------------


CHUNKS = [
    Chunk("gap:1:Kubernetes", "gap", "Kubernetes gap", "Gap: Kubernetes is missing for the job Backend.", "/x"),
    Chunk("skill:1", "skill", "Python", "Skill: Python. Your status: verified, proven by evidence: Repo.", "/y"),
    Chunk("project:1", "project", "Garden", "Project: Garden planner app with a calendar.", "/z"),
]


def test_hybrid_finds_a_synonym_question() -> None:
    found = retrieve(CHUNKS, "Do I know container orchestration?", embedder=FakeEmbedder())

    assert found.mode == "hybrid"
    assert found.hits[0][0] == 0


def test_bm25_mode_is_used_without_an_embedder() -> None:
    found = retrieve(CHUNKS, "container orchestration")

    assert (found.mode, found.hits) == ("bm25", [])


def test_meaning_hits_below_the_threshold_dont_count() -> None:
    """Unrelated questions still get SOME cosine; MIN_COSINE keeps "not found" possible."""
    found = retrieve(CHUNKS, "astronaut spaceship", embedder=FakeEmbedder())

    assert found.hits == []


def test_an_unavailable_embedder_falls_back_to_keywords_and_says_so() -> None:
    found = retrieve(CHUNKS, "Python", embedder=BrokenEmbedder())

    assert found.mode == "bm25"
    assert found.hits[0][0] == 1
    assert found.note.startswith("Meaning search is unavailable, so keyword search was used.")


def test_the_api_reports_the_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    from collections.abc import Iterator

    from fastapi.testclient import TestClient
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from sqlalchemy.pool import StaticPool

    from app.dependencies import get_db
    from app.main import app
    from database import Base

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)

    def override_get_db() -> Iterator[Session]:
        db = Session(engine, autoflush=False)
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    try:
        client = TestClient(app)
        # No OLLAMA_EMBED_MODEL (conftest unsets it): keyword search, no note.
        body = client.post("/assistant/ask", json={"question": "overview"}).json()
        assert (body["retrieval"], body["note"]) == ("bm25", None)

        # Set, but nothing listens on port 9: falls back with a note instead of failing.
        monkeypatch.setenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")
        monkeypatch.setenv("OLLAMA_BASE_URL", "http://127.0.0.1:9")
        body = client.post("/assistant/ask", json={"question": "overview"}).json()
        assert body["retrieval"] == "bm25"
        assert body["note"].startswith("Meaning search is unavailable")
        assert body["sources"]  # still answered
        assert NOT_FOUND not in body["answer"]
    finally:
        app.dependency_overrides.clear()
        engine.dispose()
