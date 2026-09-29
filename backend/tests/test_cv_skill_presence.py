"""Relationship and constraint checks for CVSkillPresence.

Uses an in-memory SQLite database, same approach as test_user_skill.py. This only
exercises SQLAlchemy mappings — no service exists for this table yet.
"""

from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import CVSkillPresence, Skill, User
from app.db.models.enums import VerificationStatus
from app.db.models.user_skill import UserSkill
from database import Base


@pytest.fixture()
def session() -> Iterator[Session]:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        yield db
    engine.dispose()


def test_a_presence_record_links_to_its_user_and_skill(session: Session) -> None:
    user = User(email="dev@example.com")
    skill = Skill(name="Python")
    presence = CVSkillPresence(user=user, skill=skill, present=True)

    session.add_all([user, skill, presence])
    session.commit()

    assert presence.user is user
    assert presence.skill is skill
    assert presence in user.cv_skill_presences
    assert presence in skill.cv_skill_presences


@pytest.mark.parametrize("value", [True, False])
def test_present_true_and_false_both_persist(session: Session, value: bool) -> None:
    user = User(email="dev@example.com")
    skill = Skill(name="Python")
    presence = CVSkillPresence(user=user, skill=skill, present=value)

    session.add_all([user, skill, presence])
    session.commit()
    session.refresh(presence)

    assert presence.present is value


def test_a_user_cannot_have_two_presence_rows_for_the_same_skill(session: Session) -> None:
    user = User(email="dev@example.com")
    skill = Skill(name="Python")
    session.add_all([user, skill, CVSkillPresence(user=user, skill=skill, present=True)])
    session.commit()

    session.add(CVSkillPresence(user=user, skill=skill, present=False))
    with pytest.raises(IntegrityError):
        session.commit()


def test_cv_presence_is_independent_of_user_skill_status(session: Session) -> None:
    """A skill's CV presence coexists with no UserSkill row, or any status, without conflict."""
    user = User(email="dev@example.com")
    no_claim_skill = Skill(name="AWS")  # on the CV, but no UserSkill row at all
    verified_skill = Skill(name="PostgreSQL")  # verified, but NOT on the CV
    not_verified_skill = Skill(name="Rust")  # on the CV, but NOT_VERIFIED

    verified_claim = UserSkill(user=user, skill=verified_skill, status=VerificationStatus.VERIFIED)
    not_verified_claim = UserSkill(
        user=user, skill=not_verified_skill, status=VerificationStatus.NOT_VERIFIED
    )

    presences = [
        CVSkillPresence(user=user, skill=no_claim_skill, present=True),
        CVSkillPresence(user=user, skill=verified_skill, present=False),
        CVSkillPresence(user=user, skill=not_verified_skill, present=True),
    ]

    session.add_all(
        [user, no_claim_skill, verified_skill, not_verified_skill, verified_claim, not_verified_claim]
        + presences
    )
    session.commit()

    assert session.query(UserSkill).filter_by(skill_id=no_claim_skill.id).first() is None
    assert presences[0].present is True  # on the CV, despite no claim existing at all

    assert verified_claim.status is VerificationStatus.VERIFIED
    assert presences[1].present is False  # verified, but not on the CV

    assert not_verified_claim.status is VerificationStatus.NOT_VERIFIED
    assert presences[2].present is True  # not verified, but on the CV anyway
