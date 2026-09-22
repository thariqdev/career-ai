"""Relationship and constraint checks for UserSkill / UserSkillEvidence.

Uses an in-memory SQLite database, same approach as test_profile_models.py.
This only exercises SQLAlchemy mappings — not the (not-yet-built)
verification_service that will decide when a status may become VERIFIED.
"""

from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import Evidence, Project, Skill, User
from app.db.models.enums import EvidenceType, VerificationStatus
from app.db.models.user_skill import UserSkill, UserSkillEvidence
from database import Base


@pytest.fixture()
def session() -> Iterator[Session]:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        yield db
    engine.dispose()


def test_user_skill_defaults_to_provisional(session: Session) -> None:
    user = User(email="dev@example.com")
    skill = Skill(name="Python")
    user_skill = UserSkill(user=user, skill=skill)

    session.add_all([user, skill, user_skill])
    session.commit()

    assert user_skill.status is VerificationStatus.PROVISIONAL
    assert user_skill in user.user_skills
    assert user_skill in skill.user_skills


def test_a_user_cannot_have_two_rows_for_the_same_skill(session: Session) -> None:
    user = User(email="dev@example.com")
    skill = Skill(name="Python")
    session.add_all(
        [user, skill, UserSkill(user=user, skill=skill)]
    )
    session.commit()

    session.add(UserSkill(user=user, skill=skill))
    with pytest.raises(IntegrityError):
        session.commit()


def test_one_evidence_record_can_back_multiple_skill_claims(session: Session) -> None:
    """E.g. a single FundsApp project backs both the Python and FastAPI claims."""
    user = User(email="dev@example.com")
    project = Project(user=user, name="FundsApp")
    evidence = Evidence(
        user=user, project=project, evidence_type=EvidenceType.PROJECT, title="FundsApp repo"
    )

    python_skill = UserSkill(
        user=user, skill=Skill(name="Python"), status=VerificationStatus.VERIFIED
    )
    fastapi_skill = UserSkill(
        user=user, skill=Skill(name="FastAPI"), status=VerificationStatus.VERIFIED
    )

    session.add_all(
        [
            user,
            project,
            evidence,
            python_skill,
            fastapi_skill,
            UserSkillEvidence(user_skill=python_skill, evidence=evidence),
            UserSkillEvidence(user_skill=fastapi_skill, evidence=evidence),
        ]
    )
    session.commit()

    assert len(python_skill.evidence_links) == 1
    assert len(fastapi_skill.evidence_links) == 1
    assert python_skill.evidence_links[0].evidence is evidence
    assert len(evidence.user_skill_links) == 2
