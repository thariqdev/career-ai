"""Tests for RAG stage 68: faithfulness rules, the judge's parsing, and the answer gate."""

from collections.abc import Iterator

import pytest

from app.core.services import suggestion_service
from app.rag.assistant import Prepared, Source, answer_events
from app.rag.chunker import Chunk
from app.rag.evaluate import build_fixture_chunks
from app.rag.faithfulness import check, judge, vocabulary
from app.rag.faithfulness_eval import LABELLED, _notes, score
from app.rag.generate import GenerationUnavailableError, Note


@pytest.fixture(scope="module")
def chunks() -> list[Chunk]:
    return build_fixture_chunks()


def test_the_rules_never_flag_a_faithful_labelled_answer(chunks: list[Chunk]) -> None:
    flags = [not check(c.answer, _notes(chunks, c.notes), vocabulary(chunks)).ok for c in LABELLED]

    caught, bad, alarms, good = score(flags)

    assert alarms == 0, "a rule check threw away a faithful answer"
    assert caught >= 3, "the rules should catch the extra skill and the false 'verified' claims"


def _note(text: str, title: str = "Docker") -> list[Note]:
    return [Note(1, "skill", title, text)]


PROVISIONAL = "Skill: Docker (DevOps). Your status: provisional: claimed but not proven yet, no proof."
VERIFIED = "Skill: Docker (DevOps). Your status: verified, proven by evidence: Repo."


@pytest.mark.parametrize(
    ("answer", "text", "ok"),
    [
        ("Docker is verified [1].", PROVISIONAL, False),
        ("Docker is verified [1].", VERIFIED, True),
        ("Docker isn't verified yet [1].", PROVISIONAL, True),
        ("You have 0 verified skills [1].", PROVISIONAL, True),
        ("No proof is linked for Docker [1].", PROVISIONAL, True),
        ("You use Docker and Kubernetes [1].", PROVISIONAL, False),  # Kubernetes is in no note
        ("You know JS [1].", "Skill: JavaScript. Your status: provisional.", True),  # an alias is the same skill
    ],
)
def test_rule_checks(answer: str, text: str, ok: bool) -> None:
    assert check(answer, _note(text)).ok is ok


def test_the_reason_names_the_problem() -> None:
    verdict = check("You need Terraform [1].", _note(PROVISIONAL))

    assert verdict.problems == ["it mentions Terraform, which isn't in your notes"]


def test_your_own_skill_names_count_too() -> None:
    notes = [Note(1, "skill", "Python", "Skill: Python.")]

    assert check("Learn Fooscript [1].", notes, ("Fooscript", "Python")).problems == [
        "it mentions Fooscript, which isn't in your notes"
    ]
    assert suggestion_service.mentioned("I use JS daily") == {"JavaScript"}


class Reply:
    name = "fake"

    def __init__(self, text: str | None) -> None:
        self.text = text

    def stream(self, messages: list[dict[str, str]]) -> Iterator[str]:
        if self.text is None:
            raise GenerationUnavailableError("down")
        yield self.text


@pytest.mark.parametrize(
    ("reply", "verdict"),
    [
        ("Docker is verified: UNSUPPORTED\nVERDICT: UNFAITHFUL", False),
        ("Docker is verified: SUPPORTED\nverdict: faithful", True),
        ("I think it is fine.", None),  # no verdict line
        (None, None),  # the model is unavailable
    ],
)
def test_the_judge_reads_the_verdict_line(reply: str | None, verdict: bool | None) -> None:
    assert judge("Docker is verified [1].", _note(PROVISIONAL), Reply(reply)) is verdict


def test_an_ai_answer_that_breaks_a_rule_falls_back_to_the_notes() -> None:
    chunk = Chunk("gap:1:Kubernetes", "gap", "Kubernetes gap", "Gap: Kubernetes is missing for the job Backend.", "/a")
    prepared = Prepared("What am I missing?", [Source(1, chunk, 1.0)], 5, "bm25", None, ("Kubernetes",))

    events = list(answer_events(prepared, [], Reply("You're missing Kubernetes [1] and Terraform [1].")))

    assert events[-2] == {"type": "replace", "text": "Here's what I found in your data:\n\n[1] " + chunk.text}
    assert events[-1]["written_by"] == "notes"
    assert "it mentions Terraform, which isn't in your notes" in events[-1]["note"]
