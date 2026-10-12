"""Stage 91: the assistant answers small talk like an assistant, not like a search."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.dependencies import get_db
from app.main import app
from app.rag.smalltalk import display_name, kind_of, strip_greeting
from database import Base


@pytest.mark.parametrize(
    ("message", "kind"),
    [
        ("hi", "greeting"), ("Hello there!", "greeting"), ("hey assistant", "greeting"), ("Good morning", "greeting"),
        ("how are you?", "how_are_you"), ("hi, how are you", "how_are_you"),
        ("thanks!", "thanks"), ("Thank you so much", "thanks"),
        ("bye", "bye"), ("see you later", "bye"),
        ("who are you?", "about"), ("What can you do", "about"), ("help", "about"),
        # real questions are never small talk
        ("hi what am I missing for my jobs?", None), ("Help me learn Docker", None),
        ("history of my jobs", None), ("high priority skills", None), ("What is FundsApp?", None),
    ],
)
def test_kind_of(message: str, kind: str | None) -> None:
    assert kind_of(message) == kind


def test_a_greeting_in_front_of_a_question_is_set_aside() -> None:
    assert strip_greeting("Hi, what am I missing for my jobs?") == "what am I missing for my jobs?"
    assert strip_greeting("history of my jobs") == "history of my jobs"


def test_the_name_drops_initials() -> None:
    assert display_name("B Mohammed Thariq") == "Mohammed Thariq"
    assert display_name("B. Thariq") == "Thariq"
    assert display_name(None) is None


@pytest.fixture()
def client() -> Iterator[TestClient]:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)

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
        engine.dispose()


def test_hi_gets_a_greeting_with_your_name(client: TestClient) -> None:
    client.patch("/me", json={"full_name": "B Mohammed Thariq"})

    body = client.post("/assistant/ask", json={"question": "hi"}).json()

    assert body["answer"].startswith("Hi Mohammed Thariq! 👋 I'm your Career AI assistant.")
    assert "How can I help you today?" in body["answer"]
    assert body["sources"] == [] and body["action"] is None


def test_without_a_name_it_still_greets(client: TestClient) -> None:
    assert client.post("/assistant/ask", json={"question": "Hello!"}).json()["answer"].startswith("Hi there!")


def test_hi_plus_a_question_answers_the_question(client: TestClient) -> None:
    client.post("/cv/add-all", data={"text": "Python."})
    client.post("/job-descriptions", json={"raw_text": "Backend: Python and AWS.", "title": "Backend", "company": "Acme"})

    body = client.post("/assistant/ask", json={"question": "hi, what am I missing for the Acme job?"}).json()

    assert body["sources"][0]["kind"] == "tool"  # routed like the question alone
    assert "AWS" in body["answer"]
