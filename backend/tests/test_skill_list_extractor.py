"""Tests for the deterministic skill-list extractor and its default wiring."""

from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.ai.providers.skill_list_extractor import SkillListExtractor
from app.core.services import skill_service
from app.dependencies import get_requirement_extractor
from database import Base


def _texts(terms_by_skill: dict[str, list[str]], raw_text: str) -> list[str]:
    result = SkillListExtractor(terms_by_skill).extract_requirements(raw_text)
    for item in result.requirements:
        assert item.text in raw_text  # always copied verbatim, so grounding must pass
        assert item.skill_mention == item.text
        assert item.is_required is True
    return [item.text for item in result.requirements]


def test_finds_a_known_skill_case_insensitively_using_the_texts_own_words() -> None:
    assert _texts({"Python": ["Python"]}, "Strong python skills.") == ["python"]


def test_no_skills_means_no_proposals() -> None:
    assert _texts({}, "Need Python, Docker and PostgreSQL.") == []


def test_matches_whole_terms_only() -> None:
    assert _texts({"Java": ["Java"]}, "JavaScript developer") == []
    assert _texts({"Java": ["Java"]}, "Java and JavaScript") == ["Java"]


def test_c_is_not_found_inside_c_plus_plus_or_c_sharp() -> None:
    terms = {"C": ["C"], "C++": ["C++"], "C#": ["C#"]}

    assert _texts(terms, "Experience with C++ and C# required.") == ["C++", "C#"]


def test_terms_with_dots_match_even_at_the_end_of_a_sentence() -> None:
    assert _texts({"Node.js": ["Node.js"]}, "Our backend runs on Node.js.") == ["Node.js"]


def test_short_terms_must_match_case_exactly() -> None:
    assert _texts({"Go": ["Go"]}, "You will go on-site twice a week.") == []
    assert _texts({"Go": ["Go"]}, "Services written in Go and Python.") == ["Go"]


def test_multi_word_terms_match_across_irregular_whitespace() -> None:
    assert _texts({"Machine Learning": ["Machine Learning"]}, "Some machine\n  learning.") == [
        "machine\n  learning"
    ]


def test_aliases_collapse_to_one_proposal_using_the_earliest_match() -> None:
    terms = {"PostgreSQL": ["PostgreSQL", "Postgres"]}

    assert _texts(terms, "Postgres, ideally PostgreSQL 16.") == ["Postgres"]


def test_proposals_come_back_in_text_order() -> None:
    terms = {"Docker": ["Docker"], "Python": ["Python"]}

    assert _texts(terms, "Python first, then Docker.") == ["Python", "Docker"]


# --- default wiring ------------------------------------------------------------


@pytest.fixture()
def db() -> Iterator[Session]:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine, autoflush=False) as session:
        yield session
    engine.dispose()


def test_no_key_uses_the_skill_list_extractor_with_the_real_taxonomy(
    monkeypatch, db: Session
) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    postgres = skill_service.create_skill(db, "PostgreSQL")
    skill_service.add_alias(db, postgres, "Postgres")

    extractor = get_requirement_extractor(db)

    assert isinstance(extractor, SkillListExtractor)
    found = extractor.extract_requirements("Need Postgres experience.")
    assert [item.text for item in found.requirements] == ["Postgres"]
