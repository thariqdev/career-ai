"""Stage 93: the reader evaluation's scoring, and the matcher baseline (no AI, no live data)."""

from app.rag.reader_eval import POSTINGS, _hit, run


def test_an_expected_skill_matches_any_of_its_names_case_insensitively() -> None:
    expected = ["Python", ("Node.js", "Node")]

    assert _hit("python", expected) == 0
    assert _hit("node", expected) == 1
    assert _hit("React and TypeScript frontend", expected) is None  # a phrase isn't a skill


def test_the_matcher_alone_never_needs_the_ai_and_invents_nothing_on_a_no_skill_posting() -> None:
    text, expected = POSTINGS[-1]
    asked, rejected, _ = run(text, [], with_ai=False, model="unused")

    assert expected == [] and asked == [] and rejected == 0
