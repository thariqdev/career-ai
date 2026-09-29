"""Compares a JobDescription's requirements against the user's verified knowledge.

Design rules (PROJECT_RULES.md sections 3, 4, 8, 12, 13; ARCHITECTURE.md section 10):
- Deterministic: the same data always produces the same statuses and reasoning.
  No LLM, no free-form text generation, no keyword guessing.
- Reports, never promotes. It reads UserSkill.status, which only verification_service
  may set, and it never modifies UserSkill, Evidence or their links. Where a stored
  VERIFIED/PARTIAL status has no linked evidence (data written around
  verification_service), the result is capped to PROVISIONAL instead of repeating it.
- Append-only snapshots: every run creates NEW ComparisonResult rows and never
  updates or deletes earlier ones. Picking the "latest" result is the read side's job (below).
- JobRequirement.is_required does not influence the status.
- cv_status is deferred until CVSkillPresence exists.
- Extracting requirements from job description text is a separate, later step; this
  module only compares requirements that already exist.
- Read side: latest_results returns the latest (highest-id) result per requirement and
  skill_gaps derives gaps from it. A skill gap is a derived view, never a stored row:
  storing it would duplicate ComparisonResult and go stale when evidence is added. These
  functions only read and never trigger a comparison, so a requirement that has never
  been compared has no result and is absent (never guessed). An unmapped requirement
  appears as a gap whose skill is None.

Conventions (same as the other services): plain functions taking a Session, no HTTP
knowledge, flush but never commit, and flush before reading because SessionLocal uses
autoflush=False.
"""

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import (
    ComparisonResult,
    ComparisonResultEvidence,
    Evidence,
    JobDescription,
    JobRequirement,
    Skill,
    UserSkill,
    UserSkillEvidence,
)
from app.db.models.enums import VerificationStatus

_NOT_ENOUGH = "Not enough verified information."
_CLAIMS_NEEDING_EVIDENCE = {VerificationStatus.VERIFIED, VerificationStatus.PARTIAL}


def _linked_evidence(db: Session, user_skill: UserSkill) -> list[Evidence]:
    """Evidence currently linked to the UserSkill, read fresh from the database, by id."""
    return list(
        db.scalars(
            select(Evidence)
            .join(UserSkillEvidence, UserSkillEvidence.evidence_id == Evidence.id)
            .where(UserSkillEvidence.user_skill_id == user_skill.id)
            .order_by(Evidence.id)
        )
    )


def _evidence_summary(evidence: list[Evidence]) -> str:
    return ", ".join(f"#{item.id} '{item.title}'" for item in evidence)


def _reasoning_unmapped(requirement: JobRequirement) -> str:
    return f"Requirement #{requirement.id} is not mapped to a canonical skill. {_NOT_ENOUGH}"


def _reasoning_no_claim(requirement: JobRequirement) -> str:
    skill = requirement.skill
    return (
        f"No skill claim is recorded for this user for skill #{skill.id} '{skill.name}'. "
        f"{_NOT_ENOUGH}"
    )


def _reasoning_capped(user_skill: UserSkill) -> str:
    return (
        f"UserSkill #{user_skill.id} is recorded as {user_skill.status.name} but has no linked "
        "evidence, so that claim was not backed by evidence; reported as PROVISIONAL."
    )


def _reasoning_from_user_skill(
    user_skill: UserSkill, status: VerificationStatus, evidence: list[Evidence]
) -> str:
    if not evidence:
        return f"UserSkill #{user_skill.id} is {status.name}; no linked evidence."
    verb = "supported by" if status in _CLAIMS_NEEDING_EVIDENCE else "has"
    return (
        f"UserSkill #{user_skill.id} is {status.name}; {verb} {len(evidence)} evidence "
        f"record(s): {_evidence_summary(evidence)}."
    )


def _compare_requirement(
    db: Session, user_id: int, requirement: JobRequirement
) -> ComparisonResult:
    """Apply the decision rules to one requirement and return the (unsaved) result."""
    if requirement.skill_id is None:
        return ComparisonResult(
            job_requirement=requirement,
            knowledge_status=VerificationStatus.NOT_VERIFIED,
            reasoning=_reasoning_unmapped(requirement),
        )

    user_skill = db.scalar(
        select(UserSkill).where(
            UserSkill.user_id == user_id, UserSkill.skill_id == requirement.skill_id
        )
    )
    if user_skill is None:
        return ComparisonResult(
            job_requirement=requirement,
            knowledge_status=VerificationStatus.NOT_VERIFIED,
            reasoning=_reasoning_no_claim(requirement),
        )

    evidence = _linked_evidence(db, user_skill)
    if user_skill.status in _CLAIMS_NEEDING_EVIDENCE and not evidence:
        return ComparisonResult(
            job_requirement=requirement,
            user_skill=user_skill,
            knowledge_status=VerificationStatus.PROVISIONAL,
            reasoning=_reasoning_capped(user_skill),
        )

    result = ComparisonResult(
        job_requirement=requirement,
        user_skill=user_skill,
        knowledge_status=user_skill.status,
        reasoning=_reasoning_from_user_skill(user_skill, user_skill.status, evidence),
    )
    for item in evidence:
        result.evidence_links.append(ComparisonResultEvidence(evidence=item))
    return result


def compare_job_description(db: Session, job_description: JobDescription) -> list[ComparisonResult]:
    """Store one new ComparisonResult per requirement, in requirement-id order, and return them."""
    db.flush()  # autoflush=False: make pending requirements/skills visible first

    requirements = db.scalars(
        select(JobRequirement)
        .where(JobRequirement.job_description_id == job_description.id)
        .order_by(JobRequirement.id)
    ).all()

    results: list[ComparisonResult] = []
    for requirement in requirements:
        result = _compare_requirement(db, job_description.user_id, requirement)
        db.add(result)
        db.flush()
        results.append(result)
    return results


@dataclass(frozen=True)
class RequirementGap:
    """A requirement the user is not yet VERIFIED for, paired with its latest result.

    Plain Python, not an ORM model and never persisted: gaps are derived on demand.
    (Named RequirementGap on purpose, so it is not mistaken for a SkillGap table.)
    """

    requirement: JobRequirement
    result: ComparisonResult

    @property
    def skill(self) -> Skill | None:
        """The canonical skill, or None if the requirement was never mapped to one."""
        return self.requirement.skill


def latest_results(db: Session, job_description: JobDescription) -> list[ComparisonResult]:
    """The latest (highest-id) ComparisonResult for each requirement, in requirement-id order.

    Read-only. A requirement that has never been compared has no result and is absent.
    """
    db.flush()  # autoflush=False: make pending state visible before reading

    latest_ids = (
        select(func.max(ComparisonResult.id))
        .join(JobRequirement, ComparisonResult.job_requirement_id == JobRequirement.id)
        .where(JobRequirement.job_description_id == job_description.id)
        .group_by(ComparisonResult.job_requirement_id)
    )
    return list(
        db.scalars(
            select(ComparisonResult)
            .where(ComparisonResult.id.in_(latest_ids))
            .order_by(ComparisonResult.job_requirement_id)
        )
    )


def skill_gaps(db: Session, job_description: JobDescription) -> list[RequirementGap]:
    """Requirements whose latest result is not VERIFIED, required ones first, then by id.

    Read-only and derived from latest_results; it never runs a comparison. `is_required`
    affects only the ordering, never inclusion or status.
    """
    gaps = [
        RequirementGap(requirement=result.job_requirement, result=result)
        for result in latest_results(db, job_description)
        if result.knowledge_status is not VerificationStatus.VERIFIED
    ]
    return sorted(gaps, key=lambda gap: (not gap.requirement.is_required, gap.requirement.id))
