"""Tests for stage 65 of RAG: chunking, BM25 retrieval, and the extractive assistant.

Same TestClient + StaticPool in-memory SQLite pattern as the other API tests.
"""

import math
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.models import Project, User
from app.dependencies import get_db
from app.main import app
from app.rag.assistant import NOT_FOUND
from app.rag.bm25 import BM25Index, tokenize
from app.rag.chunker import build_chunks
from database import Base


# --- BM25, by hand ------------------------------------------------------------------------


def test_tokenize_keeps_tech_words_and_drops_stop_words() -> None:
    assert tokenize("What skills am I MISSING for Node.js and C++?") == ["skills", "am", "missing", "node.js", "c++"]


def test_bm25_matches_a_hand_worked_example() -> None:
    """Three chunks: "python docker", "python", "kubernetes". Query: "kubernetes".

    N = 3, "kubernetes" is in n = 1 chunk:
        idf = ln((3 - 1 + 0.5) / (1 + 0.5) + 1) = ln(2.6667) = 0.98083
    Chunk 3 has 1 word; average length = (2 + 1 + 1) / 3 = 1.3333:
        norm = 1 - 0.75 + 0.75 * (1 / 1.3333) = 0.8125
        tf   = 1 * (1.5 + 1) / (1 + 1.5 * 0.8125) = 2.5 / 2.21875 = 1.12676
        score = 0.98083 * 1.12676 = 1.10516
    """
    index = BM25Index(["python docker", "python", "kubernetes"])

    assert index.idf("kubernetes") == pytest.approx(math.log(2.5 / 1.5 + 1))
    assert index.score("kubernetes", 2) == pytest.approx(1.10516, abs=1e-4)
    assert [h.index for h in index.search("kubernetes")] == [2]  # zero-score chunks aren't returned


def test_rare_words_count_more_than_common_ones() -> None:
    index = BM25Index(["python docker", "python", "python flask"])

    # "python" is in all 3 chunks (weak signal); "docker" in 1 (strong): chunk 0 wins.
    assert index.search("python docker")[0].index == 0
    assert index.idf("docker") > index.idf("python")


def test_repeating_a_word_has_diminishing_returns() -> None:
    once, ten = BM25Index(["kubernetes guide", " ".join(["kubernetes"] * 10)]).search("kubernetes")
    # Ten mentions score more than one, but nowhere near ten times as much.
    assert ten.score / once.score < 2


def test_an_empty_index_finds_nothing() -> None:
    assert BM25Index([]).search("python") == []


# --- through the API ----------------------------------------------------------------------


@pytest.fixture()
def engine() -> Iterator[Engine]:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture()
def client(engine: Engine, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)  # use the free skill-list reader

    def override_get_db() -> Iterator[Session]:
        db = Session(engine, autoflush=False)
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


@pytest.fixture()
def filled(client: TestClient) -> None:
    """A CV, one proven skill, a project, and a job with gaps."""
    client.post("/cv/add-all", data={"text": "Python, FastAPI, PostgreSQL and Docker. Git daily."})
    skills = {s["name"]: s["id"] for s in client.get("/skills").json()}
    claim_by_skill = {c["skill_id"]: c["id"] for c in client.get("/user-skills").json()}
    project_id = client.post("/projects", json={"name": "FundsApp", "description": "Budgeting API in FastAPI."}).json()["id"]
    evidence_id = client.post(
        "/evidence", json={"evidence_type": "project", "title": "FundsApp repo", "project_id": project_id}
    ).json()["id"]
    python_claim = claim_by_skill[skills["Python"]]
    client.post(f"/user-skills/{python_claim}/evidence-links", json={"evidence_id": evidence_id})
    client.post(f"/user-skills/{python_claim}/status", json={"status": "verified"})
    job_id = client.post(
        "/job-descriptions",
        json={"raw_text": "Backend role: Python, PostgreSQL, Kubernetes and AWS.", "title": "Backend", "company": "Acme"},
    ).json()["id"]
    client.post(f"/job-descriptions/{job_id}/extract")


def _ask(client: TestClient, question: str) -> dict:
    response = client.post("/assistant/ask", json={"question": question})
    assert response.status_code == 200, response.json()
    return response.json()


def test_chunks_cover_every_kind_of_data_and_only_this_user(client: TestClient, engine: Engine, filled: None) -> None:
    with Session(engine, autoflush=False) as db:
        db.add(Project(user=User(email="other@example.com"), name="Secret project"))
        db.commit()
        me = db.query(User).filter_by(email="me@career-ai.local").one()
        chunks = build_chunks(db, me)

    kinds = {c.kind for c in chunks}
    assert kinds >= {"overview", "skill", "job", "gap", "evidence", "project"}
    assert len({c.id for c in chunks}) == len(chunks)  # ids are unique
    assert not any("Secret project" in c.text for c in chunks)
    python = next(c for c in chunks if c.id.startswith("skill:") and c.title == "Python")
    assert "verified, proven by evidence: FundsApp repo" in python.text
    assert python.link.startswith("/skills/")


def test_a_question_about_a_jobs_gaps_finds_them(client: TestClient, filled: None) -> None:
    body = _ask(client, "What am I missing for the Acme backend job? Kubernetes?")

    kinds = [s["kind"] for s in body["sources"]]
    assert kinds[0] in {"gap", "job"}
    assert any(s["kind"] == "gap" and "Kubernetes" in s["text"] for s in body["sources"])
    assert body["answer"].startswith("Here's what I found in your data:")
    assert "[1]" in body["answer"]
    assert [s["number"] for s in body["sources"]] == list(range(1, len(body["sources"]) + 1))


def test_a_question_about_proof_finds_the_evidence(client: TestClient, filled: None) -> None:
    body = _ask(client, "Which evidence proves my Python skill?")

    assert any("FundsApp repo" in s["text"] for s in body["sources"][:2])


def test_the_answer_only_contains_retrieved_text(client: TestClient, filled: None) -> None:
    body = _ask(client, "Tell me about Docker")

    for line in body["answer"].split("\n\n")[1:]:
        number, text = line.split("] ", 1)
        assert text == body["sources"][int(number.lstrip("[")) - 1]["text"]


def test_no_match_says_so_instead_of_guessing(client: TestClient, filled: None) -> None:
    body = _ask(client, "astronaut spaceship")

    assert body["answer"] == NOT_FOUND
    assert body["sources"] == []
    assert body["searched"] > 0


def test_an_empty_app_still_answers_honestly(client: TestClient) -> None:
    body = _ask(client, "What skills do I have?")

    assert [s["kind"] for s in body["sources"]] == ["overview"]
    assert "0 skills saved" in body["sources"][0]["text"]


@pytest.mark.parametrize(("question", "status"), [("   ", 422), ("x" * 501, 422)])
def test_bad_questions_are_refused(client: TestClient, question: str, status: int) -> None:
    assert client.post("/assistant/ask", json={"question": question}).status_code == status


# --- stage 66a: stemming and evaluation -------------------------------------------------------

from app.rag import evaluate as rag_eval  # noqa: E402
from app.rag.bm25 import stem  # noqa: E402


@pytest.mark.parametrize(
    ("word", "root"),
    [
        ("jobs", "job"), ("skills", "skill"), ("learning", "learn"), ("studies", "study"),
        ("verified", "verifi"), ("class", "class"), ("aws", "aws"), ("node.js", "node.js"),
        ("c++", "c++"), ("k8s", "k8s"), ("go", "go"),
    ],
)
def test_stem_cuts_suffixes_but_never_touches_tech_names(word: str, root: str) -> None:
    assert stem(word) == root


def test_stemming_is_off_by_default_and_on_when_asked() -> None:
    assert tokenize("Missing jobs") == ["missing", "jobs"]
    assert tokenize("Missing jobs", stem_words=True) == ["miss", "job"]
    assert BM25Index(["job"], stem=True).search("jobs")  # the forms meet when stemming
    assert BM25Index(["job"]).search("jobs") == []  # ...and don't by default


def test_recall_and_mrr_by_hand() -> None:
    retrieved = [("gap", "A"), ("job", "X"), ("skill", "B"), ("overview", "Y")]

    assert rag_eval.recall_at_k(retrieved, {("gap", "A"), ("skill", "B")}) == 1.0
    assert rag_eval.recall_at_k(retrieved, {("gap", "A"), ("skill", "Z")}) == 0.5
    assert rag_eval.reciprocal_rank(retrieved, {("skill", "B")}) == pytest.approx(1 / 3)
    assert rag_eval.reciprocal_rank(retrieved, {("skill", "Z")}) == 0.0
    assert rag_eval.reciprocal_rank(retrieved, {("overview", "Y")}, k=3) == 0.0  # outside the top k


def test_retrieval_quality_does_not_regress() -> None:
    """The golden-set score of the assistant's search, locked in (measured 2026-10-10).

    If a change lowers these, it made retrieval worse: look at the per-question table from
    `python -m app.rag.evaluate` before accepting it.
    """
    scores = rag_eval.evaluate(rag_eval.build_fixture_chunks())
    recall, mrr = rag_eval.summary(scores)

    assert recall >= 0.99
    assert mrr >= 0.88


# --- stage 67a: streaming -------------------------------------------------------------------

import json  # noqa: E402

from app.rag.assistant import stream_pieces  # noqa: E402


def test_stream_pieces_join_back_to_the_answer() -> None:
    answer = "Here's what I found:\n\n[1] Gap: Kubernetes  is missing."
    pieces = list(stream_pieces(answer))

    assert "".join(pieces) == answer
    assert len(pieces) > 5


def test_the_stream_sends_meta_then_deltas_then_done(client: TestClient, filled: None) -> None:
    question = {"question": "What am I missing for the Acme backend job? Kubernetes?"}
    whole = client.post("/assistant/ask", json=question).json()

    response = client.post("/assistant/ask/stream", json=question)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/x-ndjson")
    events = [json.loads(line) for line in response.text.splitlines()]
    assert events[0]["type"] == "meta"
    assert events[-1] == {"type": "done", "written_by": "notes", "note": None}  # no chat model set
    assert events[0]["sources"] == whole["sources"]
    assert (events[0]["retrieval"], events[0]["searched"]) == (whole["retrieval"], whole["searched"])
    deltas = [e["text"] for e in events if e["type"] == "delta"]
    assert "".join(deltas) == whole["answer"]


def test_a_bad_question_fails_before_streaming(client: TestClient) -> None:
    response = client.post("/assistant/ask/stream", json={"question": "  "})

    assert response.status_code == 422
    assert response.json()["detail"] == "Type a question first."
