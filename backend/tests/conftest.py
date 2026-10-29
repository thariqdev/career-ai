"""Shared test setup.

database.py loads backend/.env, so a developer's own OLLAMA_MODEL would otherwise switch
every API test onto the local AI reader. Tests that want it set it themselves.
"""

import pytest


@pytest.fixture(autouse=True)
def _no_local_ai_reader(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OLLAMA_MODEL", raising=False)
    monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)
    monkeypatch.delenv("OLLAMA_EMBED_MODEL", raising=False)
    monkeypatch.delenv("OLLAMA_CHAT_MODEL", raising=False)
    monkeypatch.delenv("OLLAMA_KEEP_ALIVE", raising=False)
    for name in ("EMBED_PROVIDER", "CHAT_PROVIDER", "GEMINI_API_KEY", "GROQ_API_KEY", "GEMINI_EMBED_MODEL",
                 "GROQ_CHAT_MODEL", "GEMINI_CHAT_MODEL", "EVAL_WRITER"):
        monkeypatch.delenv(name, raising=False)  # tests never call a hosted AI API
    from app.rag import vector_store

    monkeypatch.setattr(vector_store, "session_factory_override", None)  # never store vectors in a real DB
    monkeypatch.delenv("DEMO_MODE", raising=False)  # the public demo is never on in tests
    monkeypatch.delenv("DEMO_RESET_TOKEN", raising=False)
