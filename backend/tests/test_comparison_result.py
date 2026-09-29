"""Relationship checks for ComparisonResult / ComparisonResultEvidence.

Uses an in-memory SQLite database, same approach as the other model tests.
No comparison logic exists yet — these tests only confirm that a stored result
is wired to its requirement, its (optional) UserSkill, and its evidence.
"""

from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.models import (
    ComparisonResult,
    ComparisonResultEvidence,
    Evidence,
    JobDescription,
    JobRequirement,
    Skill,
    User,
    UserSkill,
)
from app.db.models.enums import EvidenceType, VerificationStatus
from database import Base


@pytest.fixture()
def session() -> Iterator[Session]:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        yield db
    engine.dispose()


def _requirement(user: User, skill: Skill | None = None) -> JobRequirement:
    posting = JobDescription(user=user, raw_text="Need Python experience.")
    return JobRequirement(
        job_description=posting, skill=skill, requirement_text="Python experience"
    )


def test_result_links_to_requirement_user_skill_and_multiple_evidence(
    session: Session,
) -> None:
    user = User(email="dev@example.com")
    python = Skill(name="Python")
    requirement = _requirement(user, python)
    user_skill = UserSkill(user=user, skill=python, status=VerificationStatus.VERIFIED)
    first = Evidence(user=user, evidence_type=EvidenceType.PROJECT, title="FundsApp repo")
    second = Evidence(user=user, evidence_type=EvidenceType.CERTIFICATION, title="Py cert")

    result = ComparisonResult(
        job_requirement=requirement,
        user_skill=user_skill,
        knowledge_status=VerificationStatus.VERIFIED,
        reasoning="Verified via FundsApp project and a certification.",
    )

    session.add_all(
        [
            user,
            python,
            requirement,
            user_skill,
            first,
            second,
            result,
            ComparisonResultEvidence(comparison_result=result, evidence=first),
            ComparisonResultEvidence(comparison_result=result, evidence=second),
        ]
    )
    session.commit()

    assert result in requirement.comparison_results
    assert result in user_skill.comparison_results
    assert result.job_requirement is requirement
    assert result.user_skill is user_skill
    assert {link.evidence for link in result.evidence_links} == {first, second}
    assert len(first.comparison_result_links) == 1


def test_result_without_user_skill_records_not_verified(session: Session) -> None:
    """The "Not enough verified information" case: no claim exists to compare against."""
    user = User(email="dev@example.com")
    requirement = _requirement(user)
    result = ComparisonResult(
        job_requirement=requirement,
        knowledge_status=VerificationStatus.NOT_VERIFIED,
        reasoning="Not enough verified information.",
    )

    session.add_all([user, requirement, result])
    session.commit()

    assert result.user_skill is None
    assert result.knowledge_status is VerificationStatus.NOT_VERIFIED
    assert result.evidence_links == []


def test_multiple_results_for_the_same_requirement_can_coexist(session: Session) -> None:
    """Append-only snapshots: a later re-comparison adds a row instead of replacing one."""
    user = User(email="dev@example.com")
    requirement = _requirement(user)
    earlier = ComparisonResult(
        job_requirement=requirement,
        knowledge_status=VerificationStatus.NOT_VERIFIED,
        reasoning="Not enough verified information.",
    )
    later = ComparisonResult(
        job_requirement=requirement,
        knowledge_status=VerificationStatus.PROVISIONAL,
        reasoning="User has since added this skill, but no evidence is linked yet.",
    )

    session.add_all([user, requirement, earlier, later])
    session.commit()

    assert len(requirement.comparison_results) == 2
    assert {r.knowledge_status for r in requirement.comparison_results} == {
        VerificationStatus.NOT_VERIFIED,
        VerificationStatus.PROVISIONAL,
    }
