"""Production writers: GroqChat, GeminiChat and FallbackChat (Groq, then Gemini, then the
notes). Fake servers stand in for both (httpx.MockTransport); no key is real and nothing
leaves the machine."""

import json
from collections.abc import Iterator

import httpx
import pytest

from app.rag.assistant import configured_chat, configured_rewriter
from app.rag.generate import (
    FallbackChat,
    GeminiChat,
    GenerationUnavailableError,
    GroqChat,
    OllamaChat,
)

MESSAGES = [
    {"role": "system", "content": "Use only the notes."},
    {"role": "user", "content": "earlier question"},
    {"role": "assistant", "content": "earlier answer"},
    {"role": "user", "content": "What am I missing?"},
]


def _sse(*payloads: str) -> bytes:
    return "".join(f"data: {p}\n\n" for p in payloads).encode()


def _groq_ok(request: httpx.Request) -> httpx.Response:
    chunks = [json.dumps({"choices": [{"delta": {"content": t}}]}) for t in ("You need ", "Docker [1].")]
    return httpx.Response(200, content=_sse(json.dumps({"choices": [{"delta": {"role": "assistant"}}]}), *chunks, "[DONE]"))


def _gemini_ok(request: httpx.Request) -> httpx.Response:
    thought = {"candidates": [{"content": {"parts": [{"text": "thinking...", "thought": True}]}}]}
    answer = {"candidates": [{"content": {"parts": [{"text": "From Gemini [1]."}]}}]}
    return httpx.Response(200, content=_sse(json.dumps(thought), json.dumps(answer)))


def test_groq_streams_only_the_answer_with_the_key_in_a_header() -> None:
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return _groq_ok(request)

    pieces = list(GroqChat("groq-key", transport=httpx.MockTransport(handler)).stream(MESSAGES))

    assert pieces == ["You need ", "Docker [1]."]
    body = json.loads(seen[0].content)
    assert seen[0].url.path.endswith("/chat/completions") and seen[0].headers["authorization"] == "Bearer groq-key"
    assert body["model"] == "openai/gpt-oss-20b" and body["stream"] is True and body["messages"] == MESSAGES
    assert body["include_reasoning"] is False and body["reasoning_effort"] == "low"


def test_gemini_maps_roles_skips_thoughts_and_keeps_the_key_out_of_the_url() -> None:
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return _gemini_ok(request)

    pieces = list(GeminiChat("gem-key", transport=httpx.MockTransport(handler)).stream(MESSAGES))

    assert pieces == ["From Gemini [1]."]
    request = seen[0]
    body = json.loads(request.content)
    assert request.url.path.endswith("/models/gemini-3.5-flash-lite:streamGenerateContent")
    assert request.url.params["alt"] == "sse" and "gem-key" not in str(request.url)
    assert request.headers["x-goog-api-key"] == "gem-key"
    assert body["systemInstruction"] == {"parts": [{"text": "Use only the notes."}]}
    assert [c["role"] for c in body["contents"]] == ["user", "model", "user"]


@pytest.mark.parametrize("status", [429, 500, 503])
def test_busy_or_broken_providers_raise_the_usual_error(status: int) -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(status))
    for chat in (GroqChat("k", transport=transport), GeminiChat("k", transport=transport)):
        with pytest.raises(GenerationUnavailableError, match=str(status)):
            list(chat.stream(MESSAGES))


def test_a_timeout_raises_the_usual_error_without_the_key() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow")

    with pytest.raises(GenerationUnavailableError, match="isn't reachable") as error:
        list(GroqChat("secret-key", transport=httpx.MockTransport(handler)).stream(MESSAGES))
    assert "secret-key" not in str(error.value)


def test_when_groq_is_busy_gemini_answers() -> None:
    chat = FallbackChat([
        GroqChat("k", transport=httpx.MockTransport(lambda r: httpx.Response(429))),
        GeminiChat("k", transport=httpx.MockTransport(_gemini_ok)),
    ])

    assert "".join(chat.stream(MESSAGES)) == "From Gemini [1]."
    assert chat.last_used == "gemini-3.5-flash-lite"


def test_when_both_fail_the_error_goes_up_so_the_assistant_shows_the_notes() -> None:
    down = httpx.MockTransport(lambda r: httpx.Response(503))
    chat = FallbackChat([GroqChat("k", transport=down), GeminiChat("k", transport=down)])

    with pytest.raises(GenerationUnavailableError, match="No AI writer answered"):
        list(chat.stream(MESSAGES))


class _BreaksHalfway:
    name = "breaks"

    def stream(self, messages) -> Iterator[str]:
        yield "half an answer"
        raise GenerationUnavailableError("connection dropped")


class _NeverCalled:
    name = "never"

    def stream(self, messages) -> Iterator[str]:
        raise AssertionError("must not repeat the answer with another writer")


def test_a_writer_that_fails_halfway_is_not_swapped_mid_answer() -> None:
    chat = FallbackChat([_BreaksHalfway(), _NeverCalled()])
    pieces = []

    with pytest.raises(GenerationUnavailableError, match="connection dropped"):
        for piece in chat.stream(MESSAGES):
            pieces.append(piece)
    assert pieces == ["half an answer"]


def test_the_writer_is_chosen_by_env_and_local_stays_on_ollama(monkeypatch: pytest.MonkeyPatch) -> None:
    assert configured_chat() is None

    monkeypatch.setenv("OLLAMA_CHAT_MODEL", "llama3.2")
    assert isinstance(configured_chat(), OllamaChat)

    monkeypatch.setenv("CHAT_PROVIDER", "groq")
    assert configured_chat() is None  # hosted without keys: notes only, never a crash
    monkeypatch.setenv("GROQ_API_KEY", "g")
    monkeypatch.setenv("GEMINI_API_KEY", "m")
    chat = configured_chat()
    assert isinstance(chat, FallbackChat) and [type(c) for c in chat.chats] == [GroqChat, GeminiChat]
    rewriter = configured_rewriter()
    assert rewriter.chats[0].temperature == 0.0 and rewriter.chats[0].seed is not None
