"""Tests for cv_service (the read-only knowledge + CV combined view).

Uses an in-memory SQLite database, same approach as test_comparison_service.py. The
session uses autoflush=False to match SessionLocal in database.py.
"""

from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.core.services import cv_service, skill_service
from app.core.services.cv_service import CVStatus
from app.db.models import CVSkillPresence, Skill, User, UserSkill
from app.db.models.enums import VerificationStatus
from database import Base


@pytest.fixture()
def session() -> Iterator[Session]:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine, autoflush=False) as db:
        yield db
    engine.dispose()


def _user(db: Session, email: str = "dev@example.com") -> User:
    user = User(email=email)
    db.add(user)
    db.flush()
    return user


def _skill(db: Session, name: str = "Docker") -> Skill:
    skill = skill_service.create_skill(db, name)
    return skill


def _claim(db: Session, user: User, skill: Skill, status: VerificationStatus) -> UserSkill:
    user_skill = UserSkill(user=user, skill=skill, status=status)
    db.add(user_skill)
    db.flush()
    return user_skill


def _presence(db: Session, user: User, skill: Skill, present: bool) -> CVSkillPresence:
    presence = CVSkillPresence(user=user, skill=skill, present=present)
    db.add(presence)
    db.flush()
    return presence


# --- the full 10-combination decision table -----------------------------------

_KNOWLEDGE_STATUSES = [
    None,
    VerificationStatus.NOT_VERIFIED,
    VerificationStatus.PROVISIONAL,
    VerificationStatus.PARTIAL,
    VerificationStatus.VERIFIED,
]

_EXPECTED = {
    (None, True): (CVStatus.PRESENT, "listed on your CV without verified evidence"),
    (None, False): (CVStatus.NOT_PRESENT, None),
    (VerificationStatus.NOT_VERIFIED, True): (
        CVStatus.PRESENT,
        "listed on your CV without verified evidence",
    ),
    (VerificationStatus.NOT_VERIFIED, False): (CVStatus.NOT_PRESENT, None),
    (VerificationStatus.PROVISIONAL, True): (
        CVStatus.PRESENT,
        "listed on your CV without verified evidence",
    ),
    (VerificationStatus.PROVISIONAL, False): (CVStatus.NOT_PRESENT, None),
    (VerificationStatus.PARTIAL, True): (CVStatus.PRESENT, None),
    (VerificationStatus.PARTIAL, False): (CVStatus.MISSING_FROM_CV, "you have partial evidence"),
    (VerificationStatus.VERIFIED, True): (CVStatus.PRESENT, None),
    (VerificationStatus.VERIFIED, False): (
        CVStatus.MISSING_FROM_CV,
        "you have verified evidence",
    ),
}


@pytest.mark.parametrize("knowledge_status", _KNOWLEDGE_STATUSES)
@pytest.mark.parametrize("cv_present", [True, False])
def test_every_combination_of_the_decision_table(
    session: Session, knowledge_status: VerificationStatus | None, cv_present: bool
) -> None:
    user = _user(session)
    skill = _skill(session)
    if knowledge_status is not None:
        _claim(session, user, skill, knowledge_status)
    _presence(session, user, skill, cv_present)

    result = cv_service.combined_status(session, user, skill)

    expected_status, expected_fragment = _EXPECTED[(knowledge_status, cv_present)]
    assert result.knowledge_status is knowledge_status
    assert result.cv_status is expected_status
    if expected_fragment is None:
        assert result.recommendation is None
    else:
        assert expected_fragment in result.recommendation
        assert skill.name in result.recommendation


def test_no_user_skill_and_no_cv_presence_row_at_all(session: Session) -> None:
    """The tenth "row" isn't in the table above: no CVSkillPresence row exists either."""
    user = _user(session)
    skill = _skill(session)

    result = cv_service.combined_status(session, user, skill)

    assert result.knowledge_status is None
    assert result.cv_status is CVStatus.NOT_PRESENT
    assert result.recommendation is None


# --- combined_status_for_all ---------------------------------------------------


def test_for_all_includes_only_skills_with_at_least_one_row_and_is_ordered_by_name(
    session: Session,
) -> None:
    user = _user(session)
    python = _skill(session, "Python")
    docker = _skill(session, "Docker")
    rust = _skill(session, "Rust")  # neither row -> excluded
    _claim(session, user, python, VerificationStatus.VERIFIED)
    _presence(session, user, docker, True)

    results = cv_service.combined_status_for_all(session, user)

    assert [r.skill.name for r in results] == ["Docker", "Python"]
    assert rust.name not in [r.skill.name for r in results]


def test_for_all_scopes_to_the_given_user(session: Session) -> None:
    user_a = _user(session, "a@example.com")
    user_b = _user(session, "b@example.com")
    shared_skill = _skill(session, "Python")
    _claim(session, user_b, shared_skill, VerificationStatus.VERIFIED)
    _presence(session, user_b, shared_skill, True)

    results = cv_service.combined_status_for_all(session, user_a)

    assert results == []


def test_for_all_combines_correctly_for_a_realistic_mixed_set(session: Session) -> None:
    user = _user(session)
    docker = _skill(session, "Docker")  # verified, not on CV
    aws = _skill(session, "AWS")  # on CV, no claim at all
    react = _skill(session, "React")  # provisional, on CV
    _claim(session, user, docker, VerificationStatus.VERIFIED)
    _presence(session, user, aws, True)
    _claim(session, user, react, VerificationStatus.PROVISIONAL)
    _presence(session, user, react, True)

    results = {r.skill.name: r for r in cv_service.combined_status_for_all(session, user)}

    assert results["Docker"].cv_status is CVStatus.MISSING_FROM_CV
    assert results["AWS"].cv_status is CVStatus.PRESENT
    assert results["AWS"].knowledge_status is None
    assert results["React"].cv_status is CVStatus.PRESENT
    assert "without verified evidence" in results["React"].recommendation


def test_neither_function_writes_anything(session: Session) -> None:
    user = _user(session)
    skill = _skill(session)
    _claim(session, user, skill, VerificationStatus.VERIFIED)
    _presence(session, user, skill, False)
    session.commit()

    def counts() -> tuple[int, int]:
        return (
            session.scalar(select(func.count()).select_from(UserSkill)),
            session.scalar(select(func.count()).select_from(CVSkillPresence)),
        )

    before = counts()
    cv_service.combined_status(session, user, skill)
    cv_service.combined_status_for_all(session, user)

    assert counts() == before
