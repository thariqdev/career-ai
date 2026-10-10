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
