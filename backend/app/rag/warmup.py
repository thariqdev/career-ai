"""Keep the local models ready, so answers don't wait for them to load (stage 72).

A model must be loaded into memory before it answers. Measured on this computer
(app/rag/latency_eval.py): the first word of an answer took 10 s with llama3.2 cold
(plus 8.7 s to load the embedder) but 0.4 s warm. Ollama unloads an idle model after
5 minutes by default, so every pause longer than that brought the wait back.

Two fixes:
- KEEP-ALIVE: every request to Ollama asks it to keep the model loaded for
  OLLAMA_KEEP_ALIVE (default 30m; "-1" = forever, "0" = unload at once). The cost is
  memory: about 2.9 GB for llama3.2 and 0.3 GB for nomic-embed-text while loaded.
- WARM-UP: when the backend starts with the AI switched on, both models are loaded in a
  background thread, and then your notes are embedded into the assistant's cache (the
  first question spent 8.7 s embedding 67 notes even with the models loaded). Startup
  isn't delayed, and if Ollama is off the warm-up just gives up (the assistant falls
  back as usual).
"""

import logging
import os
import threading

import httpx

DEFAULT_KEEP_ALIVE = "30m"
DEFAULT_BASE_URL = "http://127.0.0.1:11434"

log = logging.getLogger(__name__)


def keep_alive() -> str:
    """How long Ollama should keep a model loaded after each request."""
    return (os.getenv("OLLAMA_KEEP_ALIVE") or DEFAULT_KEEP_ALIVE).strip()


def warm_up(
    base_url: str,
    chat_model: str | None,
    embed_model: str | None,
    transport: httpx.BaseTransport | None = None,  # tests only
) -> list[str]:
    """Load the models now. Returns problems (empty when all loaded); never raises."""
    problems = []
    requests = []
    if chat_model:  # /api/generate with no prompt just loads the model
        requests.append((chat_model, "/api/generate", {"model": chat_model, "keep_alive": keep_alive()}))
    if embed_model:  # embedding models can't generate, so embed one word
        requests.append((embed_model, "/api/embed", {"model": embed_model, "input": ["warm up"], "keep_alive": keep_alive()}))
    with httpx.Client(transport=transport, timeout=httpx.Timeout(300.0, connect=5.0)) as client:
        for model, path, body in requests:
            try:
                response = client.post(f"{base_url.rstrip('/')}{path}", json=body)
                if response.status_code != 200:
                    problems.append(f"{model}: Ollama answered {response.status_code}")
            except httpx.HTTPError as error:
                problems.append(f"{model}: Ollama isn't reachable ({type(error).__name__})")
    return problems


def index_notes_now() -> int:
    """Embed the user's notes into the assistant's cache, in a short-lived session that
    changes nothing."""
    # Imported here: the assistant imports this module (keep_alive), not the other way round.
    from app.core.services.user_service import get_or_create_default_user
    from app.rag.assistant import index_notes
    from database import SessionLocal

    with SessionLocal() as db:
        try:
            return index_notes(db, get_or_create_default_user(db))
        finally:
            db.rollback()  # read-only: never keep anything


def start_warm_up() -> threading.Thread | None:
    """Warm the configured models in the background; None when the AI is switched off."""
    chat_model = (os.getenv("OLLAMA_CHAT_MODEL") or "").strip() or None
    embed_model = (os.getenv("OLLAMA_EMBED_MODEL") or "").strip() or None
    if not chat_model and not embed_model:
        return None
    base_url = os.getenv("OLLAMA_BASE_URL") or DEFAULT_BASE_URL

    def run() -> None:
        problems = warm_up(base_url, chat_model, embed_model)
        if problems:
            log.warning("Model warm-up skipped: %s", "; ".join(problems))
            return
        log.info("Models warmed up: %s", ", ".join(m for m in (chat_model, embed_model) if m))
        if embed_model:
            try:
                count = index_notes_now()
                log.info("Embedded %d notes for meaning search", count)
            except Exception:  # a warm-up must never take the backend down
                log.exception("Embedding the notes at startup failed; the first question will do it")

    thread = threading.Thread(target=run, name="ollama-warm-up", daemon=True)
    thread.start()
    return thread
