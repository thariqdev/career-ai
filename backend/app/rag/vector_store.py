"""Note embeddings stored in PostgreSQL (production RAG step 4), replacing the in-memory cache.

Why: the free server sleeps and restarts often, and an in-memory cache empties every
time, so the first question re-embedded every note (slow, and it spends the hosted
model's free per-minute budget). Stored vectors survive restarts.

What is stored: only NOTE texts (the ones search embeds with DOC_PREFIX). Questions are
never stored: they're embedded once per question anyway, and keeping them would pile up
what the user typed.

Rows are looked up by (text hash, model name, size), so vectors from different models
(local Ollama vs production Gemini) are never mixed or compared. Search itself is
unchanged: cosine in Python over the user's notes (dozens of them).

If the database can't be used, embedding still works, just without storing: a cache
must never break the assistant.
"""

import hashlib
import logging
import threading
from collections.abc import Callable

from sqlalchemy import insert, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.models import NoteEmbedding
from app.rag.embeddings import DOC_PREFIX, Embedder

log = logging.getLogger(__name__)

# Where vectors are stored. None = don't store (the test suite sets this, so no test can
# write to a real database); unset = the app's own database.
SessionFactory = Callable[[], Session]
_DEFAULT = object()
session_factory_override: object = _DEFAULT


def _session_factory() -> SessionFactory | None:
    if session_factory_override is _DEFAULT:
        from database import SessionLocal  # imported late: tests never touch it

        return SessionLocal
    return session_factory_override  # type: ignore[return-value]


def note_key(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


class PersistentEmbedder:
    """Wraps an embedder; note vectors are read from and saved to the note_embeddings table."""

    def __init__(self, inner: Embedder, session_factory: SessionFactory | None | object = _DEFAULT) -> None:
        self.inner = inner
        self.name = inner.name
        self._factory = session_factory
        self.calls = 0  # texts actually sent to the model (for tests and curiosity)
        # The startup warm-up embeds from a background thread while requests may too.
        self._lock = threading.Lock()

    def _sessions(self) -> SessionFactory | None:
        return _session_factory() if self._factory is _DEFAULT else self._factory  # type: ignore[return-value]

    def _dims_filter(self):
        dims = getattr(self.inner, "dimensions", None)  # Gemini's size is configurable
        return [] if dims is None else [NoteEmbedding.dims == dims]

    def embed(self, texts: list[str]) -> list[list[float]]:
        with self._lock:
            return self._embed(texts)

    def _embed(self, texts: list[str]) -> list[list[float]]:
        factory = self._sessions()
        notes = {note_key(t): t for t in texts if t.startswith(DOC_PREFIX)}
        found: dict[str, list[float]] = {}
        if factory is not None and notes:
            found = self._load(factory, list(notes))

        todo = list(dict.fromkeys(t for t in texts if not (t.startswith(DOC_PREFIX) and note_key(t) in found)))
        fresh = dict(zip(todo, self.inner.embed(todo))) if todo else {}
        self.calls += len(todo)

        new_rows = {note_key(t): v for t, v in fresh.items() if t.startswith(DOC_PREFIX)}
        if factory is not None and new_rows:
            self._save(factory, new_rows)
        return [found[note_key(t)] if note_key(t) in found else fresh[t] for t in texts]

    def _load(self, factory: SessionFactory, keys: list[str]) -> dict[str, list[float]]:
        try:
            with factory() as db:
                rows = db.execute(
                    select(NoteEmbedding.note_key, NoteEmbedding.vector).where(
                        NoteEmbedding.model_name == self.name, NoteEmbedding.note_key.in_(keys), *self._dims_filter()
                    )
                ).all()
                return {key: vector for key, vector in rows}
        except SQLAlchemyError as error:
            log.warning("Stored embeddings couldn't be read, embedding afresh: %s", type(error).__name__)
            return {}

    def _save(self, factory: SessionFactory, rows: dict[str, list[float]]) -> None:
        try:
            with factory() as db:
                existing = set(
                    db.execute(
                        select(NoteEmbedding.note_key, NoteEmbedding.dims).where(
                            NoteEmbedding.model_name == self.name, NoteEmbedding.note_key.in_(list(rows))
                        )
                    ).tuples()
                )
                new = [
                    {"note_key": key, "model_name": self.name, "dims": len(vector), "vector": vector}
                    for key, vector in rows.items()
                    if (key, len(vector)) not in existing
                ]
                if new:
                    # A plain multi-row INSERT (no RETURNING): PostgreSQL then converts each value to
                    # the column's own type. The ORM's batch form (INSERT ... SELECT FROM VALUES)
                    # types them as text, which a pgvector column refuses (found on Neon).
                    db.execute(insert(NoteEmbedding), new)
                db.commit()
        except SQLAlchemyError as error:  # e.g. another process saved the same note first
            log.warning("Embeddings couldn't be stored (they still work this time): %s", type(error).__name__)
