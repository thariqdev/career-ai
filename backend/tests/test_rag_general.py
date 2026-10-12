"""Stage 92: general-knowledge questions get a labelled general answer; questions about the
user never do (they stay data-only), and a general answer may not talk about the user."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.dependencies import get_db
from app.main import app
from app.rag import assistant, general
from app.rag.assistant import NOT_FOUND
from app.rag.general_eval import QUESTIONS, score
from database import Base


def test_the_frozen_set_never_sends_a_personal_question_to_general() -> None:
    right, leaked, missed, mistakes = score()

    assert leaked == 0, mistakes  # a question about the user must never be answered from imagination
    assert right == len(QUESTIONS), mistakes


@pytest.mark.parametrize(
    ("answer", "ok"),
    [
        ("Docker packages an app and its dependencies into a container.", True),
        ("Since your skills include Python, Docker will be easy.", False),
        ("You are already experienced and ready for this.", False),
        ("NOT_GENERAL", False),
        ("   ", False),
    ],
)
def test_a_general_answer_may_not_talk_about_the_user(answer: str, ok: bool) -> None:
    assert general.acceptable(answer) is ok


class FakeChat:
    name = "fake"

    def __init__(self, reply: str) -> None:
        self.reply = reply
        self.calls: list[list[dict[str, str]]] = []

    def stream(self, messages):
        self.calls.append(messages)
        yield self.reply


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
        test_client = TestClient(app)
        test_client.post("/cv/add-all", data={"text": "Python and Docker."})
        yield test_client
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def _ask(client: TestClient, monkeypatch, question: str, reply: str) -> tuple[dict, FakeChat]:
    chat = FakeChat(reply)
    monkeypatch.setattr(assistant, "configured_chat", lambda: chat)
    return client.post("/assistant/ask", json={"question": question}).json(), chat


def test_a_general_question_gets_a_labelled_general_answer(client: TestClient, monkeypatch) -> None:
    body, chat = _ask(client, monkeypatch, "What is Docker?", "Docker runs apps in containers.")

    assert body["answer"] == "Docker runs apps in containers."
    assert body["written_by"] == "general" and body["note"] == general.LABEL
    assert body["sources"] == []
    assert chat.calls[0][0]["content"] == general.SYSTEM  # the general prompt, not the notes prompt


def test_a_general_answer_about_the_user_is_replaced(client: TestClient, monkeypatch) -> None:
    body, _ = _ask(client, monkeypatch, "What is Docker?", "Your skills already include Docker!")

    assert body["answer"] == NOT_FOUND and body["written_by"] == "notes"


def test_a_question_about_the_user_never_takes_the_general_path(client: TestClient, monkeypatch) -> None:
    body, chat = _ask(client, monkeypatch, "Do I know Docker?", "Docker [1] is on your CV.")

    assert body["written_by"] != "general"
    assert all(call[0]["content"] != general.SYSTEM for call in chat.calls)


def test_without_the_ai_a_general_question_says_so(client: TestClient) -> None:
    body = client.post("/assistant/ask", json={"question": "What are microservices?"}).json()

    assert body["answer"] == general.NO_MODEL


def test_nothing_found_and_not_personal_falls_back_to_general(client: TestClient, monkeypatch) -> None:
    body, _ = _ask(client, monkeypatch, "astronaut spaceship", "Astronauts travel in spacecraft.")

    assert body["written_by"] == "general" and body["answer"] == "Astronauts travel in spacecraft."


def test_a_general_answer_can_be_rated(client: TestClient) -> None:
    rated = client.post("/assistant/feedback", json={
        "message_id": "g1", "rating": "up", "question": "What is Docker?",
        "answer": "Docker runs apps in containers.", "sources": [], "written_by": "general",
    })

    assert rated.status_code == 200 and rated.json()["written_by"] == "general"
