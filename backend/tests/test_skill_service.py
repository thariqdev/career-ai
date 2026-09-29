"""Tests for skill_service (canonical skill resolution and safe taxonomy maintenance).

Uses an in-memory SQLite database, same approach as the other tests. The session
uses autoflush=False to match SessionLocal in database.py.
"""

from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.core.exceptions import (
    AmbiguousSkillMatchError,
    DomainError,
    EmptySkillTextError,
    SkillNameCollisionError,
)
from app.core.services import skill_service
from app.db.models import Skill, SkillAlias
from database import Base


@pytest.fixture()
def session() -> Iterator[Session]:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine, autoflush=False) as db:
        yield db
    engine.dispose()


def _counts(db: Session) -> tuple[int, int]:
    return (
        db.scalar(select(func.count()).select_from(Skill)),
        db.scalar(select(func.count()).select_from(SkillAlias)),
    )


@pytest.fixture()
def postgres(session: Session) -> Skill:
    skill = skill_service.create_skill(session, "PostgreSQL", category="Database")
    skill_service.add_alias(session, skill, "Postgres")
    return skill


# --- resolve_skill -----------------------------------------------------------


@pytest.mark.parametrize("text", ["PostgreSQL", "  postgresql ", "POSTGRESQL"])
def test_resolve_by_name_ignores_case_and_surrounding_whitespace(
    session: Session, postgres: Skill, text: str
) -> None:
    assert skill_service.resolve_skill(session, text) is postgres


def test_resolve_collapses_internal_whitespace(session: Session) -> None:
    rest = skill_service.create_skill(session, "REST API")

    assert skill_service.resolve_skill(session, "  rest    api ") is rest


def test_resolve_by_alias(session: Session, postgres: Skill) -> None:
    assert skill_service.resolve_skill(session, "Postgres") is postgres
    assert skill_service.resolve_skill(session, " POSTGRES ") is postgres


def test_unknown_text_returns_none_and_creates_nothing(
    session: Session, postgres: Skill
) -> None:
    before = _counts(session)

    assert skill_service.resolve_skill(session, "Zorblax") is None

    assert _counts(session) == before


@pytest.mark.parametrize(
    ("existing_name", "query"),
    [("PostgreSQL", "SQL"), ("Node.js", "NodeJS"), ("React.js", "React Native")],
)
def test_related_but_different_text_does_not_resolve(
    session: Session, existing_name: str, query: str
) -> None:
    skill_service.create_skill(session, existing_name)

    assert skill_service.resolve_skill(session, query) is None


@pytest.mark.parametrize("text", ["", "   ", "\t\n"])
def test_blank_text_resolves_to_none(session: Session, postgres: Skill, text: str) -> None:
    assert skill_service.resolve_skill(session, text) is None


def test_ambiguous_alias_on_two_skills_raises_instead_of_picking_one(session: Session) -> None:
    """Bypass the service to create the bad data the DB itself does not forbid."""
    first = Skill(name="React.js")
    second = Skill(name="React Native")
    session.add_all(
        [first, second, SkillAlias(skill=first, alias="React"), SkillAlias(skill=second, alias="react")]
    )
    session.commit()

    with pytest.raises(AmbiguousSkillMatchError):
        skill_service.resolve_skill(session, "React")


def test_name_match_and_alias_match_to_the_same_skill_is_not_ambiguous(
    session: Session,
) -> None:
    skill = Skill(name="PostgreSQL")
    session.add_all([skill, SkillAlias(skill=skill, alias="postgresql")])
    session.commit()

    assert skill_service.resolve_skill(session, "PostgreSQL") is skill


# --- create_skill ------------------------------------------------------------


def test_create_skill_stores_stripped_display_name_as_typed(session: Session) -> None:
    skill = skill_service.create_skill(session, "  FastAPI  ", category="Framework")

    assert skill.name == "FastAPI"
    assert skill.category == "Framework"
    assert skill.id is not None
    assert skill_service.resolve_skill(session, "fastapi") is skill


@pytest.mark.parametrize("name", ["", "   "])
def test_create_skill_rejects_blank_name(session: Session, name: str) -> None:
    with pytest.raises(EmptySkillTextError):
        skill_service.create_skill(session, name)

    assert _counts(session) == (0, 0)


def test_create_skill_rejects_collision_with_existing_name_in_different_case(
    session: Session, postgres: Skill
) -> None:
    with pytest.raises(SkillNameCollisionError) as excinfo:
        skill_service.create_skill(session, "postgresql")

    assert "PostgreSQL" in str(excinfo.value)
    assert _counts(session) == (1, 1)


def test_create_skill_rejects_collision_with_an_existing_alias(
    session: Session, postgres: Skill
) -> None:
    with pytest.raises(SkillNameCollisionError):
        skill_service.create_skill(session, "postgres")

    assert _counts(session) == (1, 1)


# --- add_alias ---------------------------------------------------------------


@pytest.mark.parametrize("alias", ["", "  "])
def test_add_alias_rejects_blank(session: Session, postgres: Skill, alias: str) -> None:
    with pytest.raises(EmptySkillTextError):
        skill_service.add_alias(session, postgres, alias)


def test_add_alias_rejects_another_skills_name(session: Session, postgres: Skill) -> None:
    mysql = skill_service.create_skill(session, "MySQL")

    with pytest.raises(SkillNameCollisionError):
        skill_service.add_alias(session, mysql, "postgresql")


def test_add_alias_rejects_another_skills_alias(session: Session, postgres: Skill) -> None:
    mysql = skill_service.create_skill(session, "MySQL")

    with pytest.raises(SkillNameCollisionError):
        skill_service.add_alias(session, mysql, "POSTGRES")


def test_add_alias_rejects_its_own_skills_name_and_alias_as_redundant(
    session: Session, postgres: Skill
) -> None:
    with pytest.raises(SkillNameCollisionError):
        skill_service.add_alias(session, postgres, "postgresql")
    with pytest.raises(SkillNameCollisionError):
        skill_service.add_alias(session, postgres, "Postgres")

    assert _counts(session) == (1, 1)


def test_add_alias_happy_path_stores_display_text_and_then_resolves(
    session: Session, postgres: Skill
) -> None:
    alias = skill_service.add_alias(session, postgres, "  PG  ")

    assert alias.alias == "PG"
    assert alias.skill is postgres
    assert alias in postgres.aliases
    assert skill_service.resolve_skill(session, "pg") is postgres


# --- list_skills / get_skill (read-only helpers used by the API) ---------------


def test_list_skills_is_ordered_by_name_and_sees_unflushed_skills(session: Session) -> None:
    skill_service.create_skill(session, "Python")
    skill_service.create_skill(session, "Docker")
    session.add(Skill(name="PostgreSQL"))  # pending, never flushed by the caller

    assert [s.name for s in skill_service.list_skills(session)] == ["Docker", "PostgreSQL", "Python"]


def test_get_skill_returns_the_skill_or_none_and_creates_nothing(session: Session) -> None:
    skill = skill_service.create_skill(session, "Python")
    before = _counts(session)

    assert skill_service.get_skill(session, skill.id) is skill
    assert skill_service.get_skill(session, 9999) is None
    assert _counts(session) == before


def test_errors_share_the_domain_error_base() -> None:
    assert issubclass(EmptySkillTextError, DomainError)
    assert issubclass(SkillNameCollisionError, DomainError)
    assert issubclass(AmbiguousSkillMatchError, DomainError)
