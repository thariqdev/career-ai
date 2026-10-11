"""Tests for RAG stage 73: rewriting follow-ups into standalone questions for search."""

from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.models import User
from app.rag import assistant
from app.rag.evaluate import fill_fixture
from app.rag.generate import GenerationUnavailableError, Turn
from app.rag.rewrite import MAX_REWRITE_CHARS, standalone_question
from database import Base

HISTORY = [
    Turn("user", "What am I missing for the Acme job?"),
    Turn("assistant", "You're missing Kubernetes [1] and AWS [2]."),
]


class FakeRewriter:
    name = "fake"

    def __init__(self, reply: str | None) -> None:
        self.reply = reply
        self.calls: list[list[dict[str, str]]] = []

    def stream(self, messages: list[dict[str, str]]) -> Iterator[str]:
        self.calls.append(messages)
        if self.reply is None:
            raise GenerationUnavailableError("down")
        yield self.reply


def test_a_first_question_is_never_rewritten() -> None:
    model = FakeRewriter("anything")

    assert standalone_question("What is FundsApp?", [], model) is None
    assert model.calls == []


def test_the_model_sees_the_last_turn_and_the_follow_up() -> None:
    model = FakeRewriter("What am I missing for the Globex job?")

    assert standalone_question("And for Globex?", HISTORY, model) == "What am I missing for the Globex job?"
    prompt = model.calls[0][-1]["content"]
    assert "User: What am I missing for the Acme job?" in prompt
    assert "Assistant: You're missing Kubernetes" in prompt
    assert "Last question: And for Globex?" in prompt


@pytest.mark.parametrize(
    ("reply", "result"),
    [
        ('Rewritten question: "What am I missing for the Globex job?"', "What am I missing for the Globex job?"),
        ("", None),
        ("What am I missing?\nI rewrote it because...", None),  # an explanation, not one question
        ("x" * (MAX_REWRITE_CHARS + 1), None),
        (None, None),  # the model is unavailable
    ],
)
def test_unusable_rewrites_are_dropped(reply: str | None, result: str | None) -> None:
    assert standalone_question("And for Globex?", HISTORY, FakeRewriter(reply)) == result


@pytest.fixture()
def fixture_db() -> Iterator[tuple[Session, User]]:
    engine = create_engine("sqlite://", poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine, autoflush=False) as db:
        yield db, fill_fixture(db)
    engine.dispose()


def test_search_and_routing_use_the_rewrite_but_the_answer_keeps_the_real_question(fixture_db) -> None:
    db, user = fixture_db

    prepared = assistant.prepare(
        db, user, "And for Globex?", history=HISTORY, rewriter=FakeRewriter("What am I missing for the Globex job?")
    )

    first = prepared.sources[0].chunk
    assert first.kind == "tool" and first.title == "Missing skills for Frontend Developer at Globex"
    assert prepared.question == "And for Globex?"  # what the answer-writing model will see


def test_without_a_usable_rewrite_the_previous_question_is_glued_on(fixture_db) -> None:
    db, user = fixture_db

    prepared = assistant.prepare(db, user, "And for Globex?", history=HISTORY, rewriter=FakeRewriter(None))

    assert all(s.chunk.kind != "tool" for s in prepared.sources)  # "And for Globex?" alone routes nowhere
    assert any("Acme" in s.chunk.text for s in prepared.sources)  # the glued Acme question still finds notes
