"""Production RAG step 4: note embeddings stored in the note_embeddings table.
Every test uses a throwaway in-memory SQLite database, never a real one."""

from collections.abc import Iterator

import pytest
from sqlalchemy import Engine, create_engine, func, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.models import NoteEmbedding, User
from app.rag import note_cache, vector_store
from app.rag.embeddings import DOC_PREFIX, QUERY_PREFIX
from app.rag.vector_store import PersistentEmbedder, note_key
from database import Base


class CountingEmbedder:
    """A fake model: a text's vector is its length, repeated. Counts what it's asked."""

    def __init__(self, name: str = "fake-model", dims: int = 4, scale: float = 1.0) -> None:
        self.name = name
        self.dims = dims
        self.scale = scale
        self.seen: list[str] = []

    def embed(self, texts: list[str]) -> list[list[float]]:
        self.seen += texts
        return [[len(t) * self.scale] * self.dims for t in texts]


@pytest.fixture()
def engine() -> Iterator[Engine]:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


def _rows(engine: Engine) -> list[NoteEmbedding]:
    with Session(engine) as db:
        return list(db.scalars(select(NoteEmbedding)))


def test_note_vectors_are_stored_once_and_reused_after_a_restart(engine: Engine) -> None:
    factory = sessionmaker(bind=engine)
    notes = [DOC_PREFIX + "Python is verified.", DOC_PREFIX + "Docker is provisional."]

    first = CountingEmbedder()
    vectors = PersistentEmbedder(first, factory).embed(notes)
    restarted = CountingEmbedder()  # a new process: nothing in memory
    again = PersistentEmbedder(restarted, factory).embed(notes)

    assert again == vectors and len(first.seen) == 2 and restarted.seen == []
    rows = _rows(engine)
    assert {r.note_key for r in rows} == {note_key(t) for t in notes}
    assert {(r.model_name, r.dims) for r in rows} == {("fake-model", 4)}
    assert rows[0].vector == vectors[notes.index(next(t for t in notes if note_key(t) == rows[0].note_key))]


def test_questions_are_embedded_but_never_stored(engine: Engine) -> None:
    embedder = PersistentEmbedder(CountingEmbedder(), sessionmaker(bind=engine))

    embedder.embed([QUERY_PREFIX + "what am I missing?"])

    assert _rows(engine) == []


def test_vectors_from_different_models_are_never_mixed(engine: Engine) -> None:
    factory = sessionmaker(bind=engine)
    text = DOC_PREFIX + "Kubernetes is a gap."

    local = PersistentEmbedder(CountingEmbedder("nomic-embed-text", scale=1.0), factory).embed([text])
    production = PersistentEmbedder(CountingEmbedder("gemini-embedding-2", scale=2.0), factory).embed([text])

    assert local != production  # Gemini didn't get Ollama's stored vector
    assert sorted(r.model_name for r in _rows(engine)) == ["gemini-embedding-2", "nomic-embed-text"]


def test_a_different_size_of_the_same_model_gets_its_own_row(engine: Engine) -> None:
    factory = sessionmaker(bind=engine)
    text = DOC_PREFIX + "note"

    class Sized(CountingEmbedder):
        def __init__(self, dims: int) -> None:
            super().__init__("gemini-embedding-2", dims)
            self.dimensions = dims

    PersistentEmbedder(Sized(768), factory).embed([text])
    bigger = Sized(1536)
    vector = PersistentEmbedder(bigger, factory).embed([text])[0]

    assert len(vector) == 1536 and bigger.seen == [text]
    assert sorted(r.dims for r in _rows(engine)) == [768, 1536]


def test_a_broken_database_never_breaks_embedding() -> None:
    def broken() -> Session:
        raise OperationalError("SELECT 1", {}, Exception("database is down"))

    embedder = PersistentEmbedder(CountingEmbedder(), broken)

    assert embedder.embed([DOC_PREFIX + "a note"]) == [[float(len(DOC_PREFIX + "a note"))] * 4]


def test_stored_embeddings_dont_change_the_notes_fingerprint(engine: Engine) -> None:
    with Session(engine) as db:
        db.add(User(email="me@career-ai.local"))
        db.commit()
        before = note_cache.fingerprint(db)
        db.add(NoteEmbedding(note_key="k", model_name="m", dims=2, vector=[0.5, 0.25]))
        db.commit()
        assert note_cache.fingerprint(db) == before  # saving a vector must not force a rebuild


def test_the_test_suite_never_stores_vectors_by_default() -> None:
    embedder = CountingEmbedder()

    PersistentEmbedder(embedder).embed([DOC_PREFIX + "x"])  # conftest: session_factory_override = None

    assert vector_store._session_factory() is None and embedder.seen == [DOC_PREFIX + "x"]


def test_on_postgresql_the_vector_is_sent_without_a_varchar_cast() -> None:
    """Regression (found on Neon): pg8000 wrote `$1::VARCHAR`, which a pgvector column rejects."""
    from sqlalchemy import insert
    from sqlalchemy.dialects.postgresql import pg8000

    statement = insert(NoteEmbedding).values(note_key="k", model_name="m", dims=2, vector=[0.5, 1.0])
    sql = str(statement.compile(dialect=pg8000.dialect()))

    # The driver casts ordinary text (note_key, model_name) but the vector goes in untyped.
    assert "VALUES (%s::VARCHAR, %s::VARCHAR, %s::INTEGER, %s)" in sql


def test_several_notes_are_saved_with_one_plain_insert(engine: Engine) -> None:
    """Regression (found on Neon): the ORM's batch insert (INSERT ... RETURNING, or SELECT
    FROM VALUES on PostgreSQL) typed vectors as text, which a pgvector column refuses."""
    from sqlalchemy import event

    inserts: list[str] = []
    event.listen(engine, "before_cursor_execute", lambda c, cur, sql, *a: sql.startswith("INSERT") and inserts.append(sql))

    PersistentEmbedder(CountingEmbedder(), sessionmaker(bind=engine)).embed([DOC_PREFIX + f"note {i}" for i in range(5)])

    assert len(_rows(engine)) == 5
    assert inserts and all("RETURNING" not in sql and "SELECT" not in sql for sql in inserts)


def test_vectors_round_trip_through_the_column_type(engine: Engine) -> None:
    with Session(engine) as db:
        db.add(NoteEmbedding(note_key="k", model_name="m", dims=3, vector=[0.1, -2.5, 3e-05]))
        db.commit()
        stored = db.scalar(select(NoteEmbedding.vector))
        raw = db.execute(select(func.cast(NoteEmbedding.vector, Base.metadata.tables["note_embeddings"].c.vector.type.impl))).scalar()

    assert stored == [0.1, -2.5, 3e-05]
    assert raw == "[0.1,-2.5,3e-05]"  # pgvector's own text format
