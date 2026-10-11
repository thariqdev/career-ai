"""Stage 77: 👍 / 👎 on assistant answers, and the report that turns 👎 into test cases."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.models import AssistantFeedback, User
from app.dependencies import get_db
from app.main import app
from app.rag.feedback_report import report
from database import Base


@pytest.fixture()
def engine() -> Iterator[Engine]:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture()
def client(engine: Engine) -> Iterator[TestClient]:
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


def _rating(**changes) -> dict:
    body = {
        "message_id": "m-1",
        "rating": "down",
        "question": "What am I missing for my jobs?",
        "answer": "You're missing Provisional proof for Problem Solving [1].",
        "sources": [{"number": 1, "kind": "tool", "title": "Missing skills per job"}],
        "retrieval": "hybrid",
        "written_by": "ai",
        "comment": "  garbled, and it left out most gaps  ",
    }
    return {**body, **changes}


def test_a_rating_is_saved_with_what_the_assistant_did(client: TestClient) -> None:
    saved = client.post("/assistant/feedback", json=_rating())

    assert saved.status_code == 200
    body = saved.json()
    assert body["rating"] == "down" and body["comment"] == "garbled, and it left out most gaps"
    assert body["sources"] == [{"number": 1, "kind": "tool", "title": "Missing skills per job"}]
    assert client.get("/assistant/feedback").json()[0]["question"] == "What am I missing for my jobs?"


def test_rating_the_same_answer_again_replaces_it(client: TestClient, engine: Engine) -> None:
    client.post("/assistant/feedback", json=_rating())
    client.post("/assistant/feedback", json=_rating(rating="up", comment="   "))

    listed = client.get("/assistant/feedback").json()
    assert [(f["rating"], f["comment"]) for f in listed] == [("up", None)]  # one row, changed
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(AssistantFeedback)) == 1


def test_the_list_can_show_only_thumbs_down(client: TestClient) -> None:
    client.post("/assistant/feedback", json=_rating(message_id="a", rating="up"))
    client.post("/assistant/feedback", json=_rating(message_id="b", rating="down"))

    down = client.get("/assistant/feedback", params={"rating": "down"}).json()

    assert [f["message_id"] for f in down] == ["b"]


@pytest.mark.parametrize(
    "change",
    [
        {"rating": "meh"},
        {"message_id": ""},
        {"answer": ""},
        {"comment": "x" * 1001},
        {"written_by": "robot"},
        {"sources": [{"number": 1, "kind": "skill", "title": "t"}] * 11},
    ],
)
def test_bad_ratings_are_refused(client: TestClient, change: dict) -> None:
    assert client.post("/assistant/feedback", json=_rating(**change)).status_code == 422


def test_the_report_turns_thumbs_down_into_draft_test_cases(client: TestClient, engine: Engine) -> None:
    client.post("/assistant/feedback", json=_rating(message_id="a", rating="up", question="Is Python verified?"))
    client.post("/assistant/feedback", json=_rating(message_id="b"))

    with Session(engine) as db:
        text = report(list(db.scalars(select(AssistantFeedback).order_by(AssistantFeedback.id))))

    assert text.startswith("1 👍, 1 👎   👎 by writer: {'ai': 1}   by search: {'hybrid': 1}")
    assert "question: What am I missing for my jobs?" in text
    assert "[1] tool: Missing skills per job" in text
    assert "_c('What am I missing for my jobs?', [\"TODO\"])," in text
    assert "Is Python verified?" not in text  # 👍 aren't test-case material


def test_the_report_says_when_there_is_nothing_to_learn_from() -> None:
    assert report([]) == "0 👍, 0 👎\n\nNo 👎 yet: nothing to turn into a test case.\n"


def test_ratings_belong_to_their_user(client: TestClient, engine: Engine) -> None:
    client.post("/assistant/feedback", json=_rating())
    with Session(engine) as db:
        other = User(email="other@example.com")
        db.add(other)
        db.flush()
        db.add(AssistantFeedback(user_id=other.id, message_id="m-1", rating="down", question="q", answer="a", sources=[]))
        db.commit()

    assert len(client.get("/assistant/feedback").json()) == 1  # only mine, though the message id is the same
