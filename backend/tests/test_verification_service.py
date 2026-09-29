"""Tests for verification_service (the evidence rules on UserSkill).

Uses an in-memory SQLite database, same approach as the other tests. The session
uses autoflush=False to match SessionLocal in database.py, so these tests run
under the same conditions the service sees in the real app.
"""

from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.exceptions import (
    DomainError,
    EvidenceAlreadyLinkedError,
    EvidenceOwnershipError,
    InsufficientEvidenceError,
)
from app.core.services import verification_service
from app.db.models import Evidence, Skill, User, UserSkill
from app.db.models.enums import EvidenceType, VerificationStatus
from database import Base


@pytest.fixture()
def session() -> Iterator[Session]:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine, autoflush=False) as db:
        yield db
    engine.dispose()


def _make_evidence(user: User, title: str = "FundsApp repo") -> Evidence:
    return Evidence(user=user, evidence_type=EvidenceType.PROJECT, title=title)


@pytest.fixture()
def user_skill(session: Session) -> UserSkill:
    user = User(email="dev@example.com")
    us = UserSkill(user=user, skill=Skill(name="Python"))
    session.add_all([user, us])
    session.commit()
    return us


def test_link_evidence_creates_link_and_does_not_change_status(
    session: Session, user_skill: UserSkill
) -> None:
    evidence = _make_evidence(user_skill.user)
    session.add(evidence)
    session.commit()

    link = verification_service.link_evidence(session, user_skill, evidence)

    assert link.user_skill_id == user_skill.id
    assert link.evidence_id == evidence.id
    assert user_skill.status is VerificationStatus.PROVISIONAL


def test_link_evidence_rejects_evidence_owned_by_another_user(
    session: Session, user_skill: UserSkill
) -> None:
    other_user = User(email="other@example.com")
    foreign_evidence = _make_evidence(other_user)
    session.add_all([other_user, foreign_evidence])
    session.commit()

    with pytest.raises(EvidenceOwnershipError):
        verification_service.link_evidence(session, user_skill, foreign_evidence)

    assert user_skill.evidence_links == []


def test_link_evidence_rejects_duplicate_link(session: Session, user_skill: UserSkill) -> None:
    evidence = _make_evidence(user_skill.user)
    session.add(evidence)
    session.commit()
    verification_service.link_evidence(session, user_skill, evidence)

    with pytest.raises(EvidenceAlreadyLinkedError):
        verification_service.link_evidence(session, user_skill, evidence)


def test_link_evidence_works_with_pending_objects_under_autoflush_false(
    session: Session,
) -> None:
    """Freshly added, never-flushed objects have no ids yet; the service must cope."""
    user = User(email="dev@example.com")
    us = UserSkill(user=user, skill=Skill(name="Python"))
    evidence = _make_evidence(user)
    session.add_all([user, us, evidence])

    link = verification_service.link_evidence(session, us, evidence)

    assert link.user_skill_id == us.id
    assert link.evidence_id == evidence.id


def test_set_verified_without_evidence_raises_and_leaves_status_unchanged(
    session: Session, user_skill: UserSkill
) -> None:
    with pytest.raises(InsufficientEvidenceError):
        verification_service.set_status(session, user_skill, VerificationStatus.VERIFIED)

    assert user_skill.status is VerificationStatus.PROVISIONAL


def test_set_partial_without_evidence_raises(session: Session, user_skill: UserSkill) -> None:
    with pytest.raises(InsufficientEvidenceError):
        verification_service.set_status(session, user_skill, VerificationStatus.PARTIAL)

    assert user_skill.status is VerificationStatus.PROVISIONAL


def test_set_verified_succeeds_after_linking_evidence_in_the_same_session(
    session: Session, user_skill: UserSkill
) -> None:
    evidence = _make_evidence(user_skill.user)
    session.add(evidence)
    session.commit()

    verification_service.link_evidence(session, user_skill, evidence)
    result = verification_service.set_status(session, user_skill, VerificationStatus.VERIFIED)

    assert result is user_skill
    assert user_skill.status is VerificationStatus.VERIFIED


@pytest.mark.parametrize(
    "status", [VerificationStatus.PROVISIONAL, VerificationStatus.NOT_VERIFIED]
)
def test_conservative_statuses_are_allowed_without_evidence(
    session: Session, user_skill: UserSkill, status: VerificationStatus
) -> None:
    verification_service.set_status(session, user_skill, status)

    assert user_skill.status is status


def test_a_verified_skill_can_be_downgraded_to_provisional(
    session: Session, user_skill: UserSkill
) -> None:
    evidence = _make_evidence(user_skill.user)
    session.add(evidence)
    session.commit()
    verification_service.link_evidence(session, user_skill, evidence)
    verification_service.set_status(session, user_skill, VerificationStatus.VERIFIED)

    verification_service.set_status(session, user_skill, VerificationStatus.PROVISIONAL)

    assert user_skill.status is VerificationStatus.PROVISIONAL


def test_service_errors_share_a_common_base_class() -> None:
    assert issubclass(EvidenceOwnershipError, DomainError)
    assert issubclass(EvidenceAlreadyLinkedError, DomainError)
    assert issubclass(InsufficientEvidenceError, DomainError)
