"""Production RAG step 5: the evals can measure the hosted models. No real API is called."""

from collections.abc import Iterator

import pytest

from app.rag import vector_store
from app.rag.embeddings import CachedEmbedder, GeminiEmbedder
from app.rag.evaluate import PatientChat, _ollama_embedder, eval_chat
from app.rag.generate import GeminiChat, GenerationUnavailableError, GroqChat, OllamaChat


class RateLimitedTwice:
    name = "busy-model"

    def __init__(self) -> None:
        self.calls = 0

    def stream(self, messages) -> Iterator[str]:
        self.calls += 1
        if self.calls <= 2:
            raise GenerationUnavailableError("Groq answered 429.")
        yield "answer [1]"


def test_a_rate_limited_writer_is_retried_so_the_score_measures_the_model() -> None:
    waits: list[float] = []
    chat = PatientChat(RateLimitedTwice(), sleep=waits.append)

    assert "".join(chat.stream([])) == "answer [1]"
    assert waits == [10.0, 20.0] and chat.retries == 2


def test_a_writer_that_never_recovers_still_fails_in_the_end() -> None:
    class AlwaysBusy:
        name = "down"

        def stream(self, messages) -> Iterator[str]:
            raise GenerationUnavailableError("Groq answered 429.")
            yield ""

    with pytest.raises(GenerationUnavailableError):
        list(PatientChat(AlwaysBusy(), sleep=lambda s: None).stream([]))


def test_evals_pick_the_production_models_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    assert isinstance(eval_chat(), OllamaChat)  # default: local

    monkeypatch.setenv("CHAT_PROVIDER", "groq")
    monkeypatch.setenv("GROQ_API_KEY", "g")
    chat = eval_chat(0.0, 7)
    assert isinstance(chat.inner, GroqChat) and chat.inner.temperature == 0.0 and chat.inner.seed == 7

    monkeypatch.setenv("EVAL_WRITER", "gemini")
    assert isinstance(eval_chat().inner, GeminiChat)


def test_the_eval_embedder_uses_gemini_and_never_stores_vectors(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EMBED_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    monkeypatch.setattr(GeminiEmbedder, "embed", lambda self, texts: [[1.0] * 768 for _ in texts])
    monkeypatch.setattr(vector_store, "session_factory_override", object())  # as if a real DB were configured

    embedder, info = _ollama_embedder()

    assert isinstance(embedder, CachedEmbedder) and isinstance(embedder.inner, GeminiEmbedder)
    assert info == "gemini-embedding-2" and vector_store.session_factory_override is None
