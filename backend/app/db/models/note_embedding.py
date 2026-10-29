import json
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import TypeDecorator, UserDefinedType

from database import Base


class _UncastText(UserDefinedType):
    """Text sent WITHOUT a type cast. SQLAlchemy's pg8000 driver normally writes text
    parameters as `$1::VARCHAR`, and PostgreSQL refuses a VARCHAR in a `vector` column
    (found on Neon: "is of type vector but expression is of type character varying").
    Sent untyped, PostgreSQL converts the text to the column's own type, vector or text."""

    cache_ok = True

    def get_col_spec(self, **kw) -> str:
        return "TEXT"


class VectorText(TypeDecorator):
    """A list of floats, written as "[0.1,0.2,...]".

    That text is pgvector's own input and output format, so the same column type works
    whether the database column is pgvector's `vector` (Neon, where the migration enables
    the extension) or plain `text` (a local PostgreSQL without pgvector, and SQLite in
    tests). PostgreSQL casts the text into `vector` itself; no extra library is needed.
    """

    impl = Text
    cache_ok = True

    def load_dialect_impl(self, dialect):
        return dialect.type_descriptor(_UncastText() if dialect.name == "postgresql" else Text())

    def process_bind_param(self, value, dialect):
        return None if value is None else "[" + ",".join(repr(float(x)) for x in value) + "]"

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        items = value if isinstance(value, list) else json.loads(value)  # a driver may already parse it
        return [float(x) for x in items]


class NoteEmbedding(Base):
    """A stored embedding of one note's text (production RAG step 4).

    Replaces the in-memory cache: vectors survive restarts, so a sleeping free server
    doesn't re-embed every note on its first question. One row per (text, model, size):
    vectors from different models (local Ollama vs production Gemini) are kept apart and
    never compared. note_key is a SHA-256 of the exact text that was embedded.
    """

    __tablename__ = "note_embeddings"
    __table_args__ = (UniqueConstraint("note_key", "model_name", "dims", name="uq_note_embeddings_key_model_dims"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    note_key: Mapped[str] = mapped_column(String(64), nullable=False)
    model_name: Mapped[str] = mapped_column(String(100), nullable=False)
    dims: Mapped[int] = mapped_column(Integer, nullable=False)
    vector: Mapped[list[float]] = mapped_column(VectorText, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
