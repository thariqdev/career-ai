"""Stage 85: interview flashcards parsed from the real RAG guide."""

import re

from fastapi.testclient import TestClient

from app.main import app
from app.rag import practice
from app.rag.practice import GUIDE, SECTION, parse


def _bullets_in_sections(text: str) -> int:
    """An independent count of question bullets inside the interview sections."""
    count, inside = 0, False
    for line in text.splitlines():
        if line.startswith("#"):
            inside = line.strip() == SECTION
        elif inside and line.startswith("- *"):
            count += 1
    return count


def test_every_question_in_the_guide_becomes_a_card() -> None:
    text = GUIDE.read_text(encoding="utf-8")
    cards = practice.cards()

    assert len(cards) == _bullets_in_sections(text) >= 50  # none silently dropped
    assert all(c.question and c.answer and c.stage for c in cards)
    assert len({c.id for c in cards}) == len(cards)


def test_a_card_keeps_its_stage_and_multi_line_answer() -> None:
    text = """## Stage 79: red-teaming prompt injection ✅

Some prose with - *not a card* in it.

### Interview questions you can now answer

- *What is it?* Instructions hidden in data,
  not typed by the user.
- *How do you defend?* Layers:
  - sanitize
  - confirm actions

## Stage 80: an allow-list ✅
- *Outside the section*: not a card.
"""
    cards = parse(text)

    assert [(c.stage, c.stage_title, c.question) for c in cards] == [
        ("79", "red-teaming prompt injection", "What is it?"),
        ("79", "red-teaming prompt injection", "How do you defend?"),
    ]
    assert cards[0].answer == "Instructions hidden in data,\nnot typed by the user."
    assert cards[1].answer == "Layers:\n- sanitize\n- confirm actions"


def test_ids_depend_on_the_question_only_so_progress_survives_reordering() -> None:
    a = parse("## Stage 1: x\n### Interview questions you can now answer\n- *Q one?* A.\n- *Q two?* B.\n")
    b = parse("## Stage 9: y\n### Interview questions you can now answer\n- *Q two?* B, reworded.\n- *Q one?* A.\n")

    assert {c.question: c.id for c in a} == {c.question: c.id for c in b}
    assert re.fullmatch(r"[0-9a-f]{10}", a[0].id)


def test_the_endpoint_serves_the_cards() -> None:
    body = TestClient(app).get("/practice/rag-questions").json()

    assert len(body) == len(practice.cards())
    assert set(body[0]) == {"id", "stage", "stage_title", "question", "answer"}
