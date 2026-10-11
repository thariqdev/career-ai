"""Stage 78: the chat proposes changes; only your confirmation (the normal endpoint) makes them."""

import json
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.dependencies import get_db
from app.main import app
from app.rag.actions import detect_action
from app.rag.actions_eval import ACTION_CASES, score
from database import Base


def test_the_frozen_set_with_no_wrong_actions() -> None:
    right, wrong, missed, mistakes = score()

    assert wrong == 0, mistakes  # proposing a change nobody asked for is never acceptable
    assert right == len(ACTION_CASES), mistakes


SKILLS = {1: ("React", ["React", "React.js"]), 2: ("Docker", ["Docker"])}


@pytest.mark.parametrize(
    ("message", "kind"),
    [
        ("I'm studying React.js now", "progress"),  # a nickname counts
        ("Save https://docker.example/react-tips as a Docker tutorial", "link"),  # a link's words never name a skill
        ("Please remove React", "refused"),
        ("Does Docker need proof?", None),
    ],
)
def test_detector_examples(message: str, kind: str | None) -> None:
    action = detect_action(message, SKILLS)

    assert (action.kind if action else None) == kind


def test_a_link_proposal_is_the_exact_request_to_make() -> None:
    action = detect_action("Save https://youtu.be/abc. as a Docker tutorial", SKILLS)

    assert (action.method, action.path) == ("POST", "/skills/2/learning-resources")
    assert action.body == {"mode": "technical_practical", "title": "Docker tutorial link", "url": "https://youtu.be/abc"}


@pytest.fixture()
def engine() -> Iterator[Engine]:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture()
def client(engine: Engine, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    def override_get_db() -> Iterator[Session]:
        db = Session(engine, autoflush=False)
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    try:
        test_client = TestClient(app)
        test_client.post("/cv/add-all", data={"text": "Python and Docker."})
        yield test_client
    finally:
        app.dependency_overrides.clear()


def _progress(client: TestClient) -> list[dict]:
    return client.get("/learning-progress").json()


def test_asking_proposes_but_changes_nothing_and_confirming_changes_it(client: TestClient) -> None:
    body = client.post("/assistant/ask", json={"question": "Mark Python as studying"}).json()

    action = body["action"]
    assert action["kind"] == "progress" and action["summary"] == "Mark Python as Studying?"
    assert body["sources"] == [] and "Nothing changes until you click Confirm" in body["answer"]
    assert _progress(client) == []  # the assistant never writes

    confirmed = client.request(action["method"], action["path"], json=action["body"])  # what Confirm does

    assert confirmed.status_code == 200
    assert [(p["skill_name"], p["status"]) for p in _progress(client)] == [("Python", "studying")]


def test_a_refusal_has_no_request_and_explains_why(client: TestClient) -> None:
    body = client.post("/assistant/ask", json={"question": "Verify my Python skill"}).json()

    assert body["action"]["kind"] == "refused" and body["action"]["method"] is None
    assert "real evidence" in body["answer"]
    assert body["action"]["link"].startswith("/skills/")


def test_the_stream_sends_the_proposal_in_meta(client: TestClient) -> None:
    response = client.post("/assistant/ask/stream", json={"question": "I finished learning Docker"})

    events = [json.loads(line) for line in response.text.splitlines()]
    assert events[0]["type"] == "meta" and events[0]["action"]["body"] == {"status": "finished"}
    assert events[-1] == {"type": "done", "written_by": "notes", "note": None}


def test_ordinary_questions_have_no_action(client: TestClient) -> None:
    assert client.post("/assistant/ask", json={"question": "Tell me about Python"}).json()["action"] is None
