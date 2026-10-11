"""Tests for stage 74: exact lists written by code, with the model's one-sentence intro."""

from collections.abc import Iterator

import pytest

from app.rag.answer_eval import ANSWERS, facts_found
from app.rag.assistant import DEFAULT_INTRO, Prepared, Source, answer_events
from app.rag.chunker import Chunk
from app.rag.generate import GenerationUnavailableError

TOOL = Chunk(
    "tool:skills_without_proof",
    "tool",
    "Skills with no proof yet",
    "Skills with no proof yet: 2. Claimed but no proof linked: Docker, Git.",
    "/skills",
    ("Skills with no proof yet: 2.", "Claimed but no proof linked: Docker, Git."),
)
SEARCH = Chunk("skill:1", "skill", "Docker", "Skill: Docker. Your status: provisional, no proof.", "/skills/1")


class Reply:
    name = "fake"

    def __init__(self, text: str | None) -> None:
        self.text = text
        self.calls: list[list[dict[str, str]]] = []

    def stream(self, messages: list[dict[str, str]]) -> Iterator[str]:
        self.calls.append(messages)
        if self.text is None:
            raise GenerationUnavailableError("down")
        yield self.text


def _run(chunks: list[Chunk], chat: Reply, exact: bool) -> tuple[str, dict]:
    prepared = Prepared("Which skills have no proof yet?", [Source(i + 1, c, 1.0) for i, c in enumerate(chunks)], 9, "bm25", None)
    text, done = "", {}
    for event in answer_events(prepared, [], chat, exact_lists=exact):
        if event["type"] == "delta":
            text += event["text"]
        elif event["type"] == "replace":
            text = event["text"]
        elif event["type"] == "done":
            done = event
    return text, done


def test_an_exact_list_is_written_by_code_with_the_models_intro() -> None:
    chat = Reply("Here are the skills you still need to prove.")

    text, done = _run([TOOL, SEARCH], chat, exact=True)

    assert text == (
        "Here are the skills you still need to prove.\n\n"
        "Skills with no proof yet: 2. [1]\n"
        "Claimed but no proof linked: Docker, Git."
    )
    assert done["written_by"] == "notes"  # the substance is the data, word for word
    assert "Skills with no proof yet" in chat.calls[0][-1]["content"]  # the model only saw the title


@pytest.mark.parametrize(
    "intro",
    [
        None,  # model unavailable
        "",
        "Here they are:\nDocker and Git.",  # more than one line
        "You need proof for Docker [1].",  # a citation: it's listing, not introducing
        "Start with Kubernetes, then the rest.",  # names a skill the list doesn't have
        "x" * 201,
    ],
)
def test_a_misbehaving_intro_is_replaced_but_the_list_stays(intro: str | None) -> None:
    text, _ = _run([TOOL], Reply(intro), exact=True)

    assert text.startswith(DEFAULT_INTRO + "\n\n")
    assert text.endswith("Claimed but no proof linked: Docker, Git.")


def test_search_answers_are_still_written_by_the_model() -> None:
    text, done = _run([SEARCH], Reply("Docker has no proof yet [1]."), exact=True)

    assert text == "Docker has no proof yet [1]."
    assert done["written_by"] == "ai"


def test_with_exact_lists_off_the_model_writes_tool_answers_too() -> None:
    text, done = _run([TOOL], Reply("You haven't proven Docker or Git yet [1]."), exact=False)

    assert text == "You haven't proven Docker or Git yet [1]."
    assert done["written_by"] == "ai"


def test_facts_are_found_case_insensitively_with_alternatives() -> None:
    case = next(c for c in ANSWERS if c.question == "Is Docker verified?")

    found, bad = facts_found("No, docker has NO PROOF yet.", case)

    assert found == frozenset({0, 1}) and bad == []
