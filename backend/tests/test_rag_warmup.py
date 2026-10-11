"""Tests for stage 72: keep-alive on every Ollama request, and the background warm-up."""

import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.rag import warmup
from app.rag.generate import OllamaChat
from app.rag.warmup import keep_alive, start_warm_up, warm_up


def _recorder(status: int = 200) -> tuple[httpx.MockTransport, list[tuple[str, dict]]]:
    sent: list[tuple[str, dict]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append((request.url.path, json.loads(request.content)))
        if request.url.path == "/api/chat":
            return httpx.Response(200, content=b'{"message": {"content": "ok"}, "done": true}\n')
        return httpx.Response(status, json={})

    return httpx.MockTransport(handler), sent


def test_keep_alive_defaults_to_30_minutes_and_can_be_changed(monkeypatch: pytest.MonkeyPatch) -> None:
    assert keep_alive() == "30m"
    monkeypatch.setenv("OLLAMA_KEEP_ALIVE", " -1 ")
    assert keep_alive() == "-1"


def test_the_chat_model_is_asked_to_stay_loaded(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OLLAMA_KEEP_ALIVE", "1h")
    transport, sent = _recorder()

    list(OllamaChat(transport=transport).stream([{"role": "user", "content": "hi"}]))

    assert sent[0][1]["keep_alive"] == "1h"


def test_warm_up_loads_both_models_the_right_way() -> None:
    transport, sent = _recorder()

    problems = warm_up("http://ollama:11434", "llama3.2", "nomic-embed-text", transport)

    assert problems == []
    assert sent == [
        ("/api/generate", {"model": "llama3.2", "keep_alive": "30m"}),  # no prompt: just load
        ("/api/embed", {"model": "nomic-embed-text", "input": ["warm up"], "keep_alive": "30m"}),
    ]


def test_warm_up_never_raises_when_ollama_is_off_or_unhappy() -> None:
    def refused(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    off = warm_up("http://ollama:11434", "llama3.2", None, httpx.MockTransport(refused))
    unhappy = warm_up("http://ollama:11434", "llama3.2", None, _recorder(status=404)[0])

    assert off == ["llama3.2: Ollama isn't reachable (ConnectError)"]
    assert unhappy == ["llama3.2: Ollama answered 404"]


def test_no_warm_up_when_the_ai_is_switched_off() -> None:
    assert start_warm_up() is None  # conftest clears OLLAMA_CHAT_MODEL and OLLAMA_EMBED_MODEL


def test_warm_up_runs_in_the_background(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OLLAMA_CHAT_MODEL", "llama3.2")
    calls = []
    monkeypatch.setattr(warmup, "warm_up", lambda base_url, chat, embed: calls.append((base_url, chat, embed)) or [])

    thread = start_warm_up()

    assert thread is not None and thread.daemon
    thread.join(timeout=5)
    assert calls == [("http://127.0.0.1:11434", "llama3.2", None)]


def test_the_app_starts_the_warm_up(monkeypatch: pytest.MonkeyPatch) -> None:
    started = []
    monkeypatch.setattr("app.main.start_warm_up", lambda: started.append(True))

    with TestClient(app) as client:  # entering runs the startup (lifespan)
        assert client.get("/health").status_code == 200

    assert started == [True]


class CountingEmbedder:
    """Fake model: a tiny vector per text, counting how many texts it was asked for."""

    name = "fake-embed"

    def __init__(self) -> None:
        self.texts: list[str] = []

    def embed(self, texts: list[str]) -> list[list[float]]:
        self.texts += texts
        return [[float(len(t) % 7) + 1.0, float(sum(map(ord, t)) % 11) + 1.0] for t in texts]


def test_indexing_the_notes_means_a_question_only_embeds_itself(monkeypatch: pytest.MonkeyPatch) -> None:
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from sqlalchemy.pool import StaticPool

    from app.rag import assistant
    from app.rag.chunker import build_chunks
    from app.rag.embeddings import CachedEmbedder
    from app.rag.evaluate import fill_fixture
    from database import Base

    inner = CountingEmbedder()
    cached = CachedEmbedder(inner)
    monkeypatch.setattr(assistant, "configured_embedder", lambda: cached)
    engine = create_engine("sqlite://", poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine, autoflush=False) as db:
        user = fill_fixture(db)
        chunks = build_chunks(db, user)

        assert assistant.index_notes(db, user) == len(chunks)
        inner.texts.clear()
        assistant.retrieve(chunks, "Is Python verified?", embedder=cached)

    assert inner.texts == ["search_query: Is Python verified?"]  # every note was already embedded
    engine.dispose()


def test_warm_up_indexes_the_notes_after_loading_the_models(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")
    monkeypatch.setattr(warmup, "warm_up", lambda *args: [])
    indexed = []
    monkeypatch.setattr(warmup, "index_notes_now", lambda: indexed.append(True) or 3)

    start_warm_up().join(timeout=5)

    assert indexed == [True]


def test_a_failed_index_never_escapes_the_warm_up(monkeypatch: pytest.MonkeyPatch, caplog) -> None:
    monkeypatch.setenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")
    monkeypatch.setattr(warmup, "warm_up", lambda *args: [])

    def boom() -> int:
        raise RuntimeError("database is down")

    monkeypatch.setattr(warmup, "index_notes_now", boom)

    thread = start_warm_up()
    thread.join(timeout=5)

    assert not thread.is_alive()
    assert "Embedding the notes at startup failed" in caplog.text
