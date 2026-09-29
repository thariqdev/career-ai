"""Enforces the evidence rules on UserSkill (PROJECT_RULES.md sections 3, 4, 8, 12).

This module is the ONLY place that should write UserSkill.status or create
UserSkillEvidence links. PostgreSQL cannot cheaply enforce "VERIFIED requires
linked evidence" (a column constraint cannot count rows in another table
without a trigger), so the rule lives here and every caller must go through it.

Conventions:
- Plain functions taking a SQLAlchemy Session; no HTTP or FastAPI knowledge.
- Functions flush but never commit: the caller owns the transaction.
- Linking evidence never changes status. Promotion only happens through an
  explicit set_status call.
"""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.exceptions import (
    EvidenceAlreadyLinkedError,
    EvidenceOwnershipError,
    InsufficientEvidenceError,
)
from app.db.models import Evidence, UserSkill, UserSkillEvidence
from app.db.models.enums import VerificationStatus

# Statuses that make a claim about the user's background, so they need evidence.
_STATUSES_REQUIRING_EVIDENCE = {VerificationStatus.VERIFIED, VerificationStatus.PARTIAL}


def _linked_evidence_count(db: Session, user_skill: UserSkill) -> int:
    """Count links straight from the database rather than a possibly stale collection."""
    return db.scalar(
        select(func.count())
        .select_from(UserSkillEvidence)
        .where(UserSkillEvidence.user_skill_id == user_skill.id)
    )


def link_evidence(db: Session, user_skill: UserSkill, evidence: Evidence) -> UserSkillEvidence:
    """Attach an Evidence record to a UserSkill. Does not change the skill's status."""
    # Sessions here use autoflush=False, so pending objects have no id/user_id yet.
    db.flush()

    if evidence.user_id != user_skill.user_id:
        raise EvidenceOwnershipError(user_skill.id, evidence.id)

    already_linked = db.scalar(
        select(UserSkillEvidence).where(
            UserSkillEvidence.user_skill_id == user_skill.id,
            UserSkillEvidence.evidence_id == evidence.id,
        )
    )
    if already_linked is not None:
        raise EvidenceAlreadyLinkedError(user_skill.id, evidence.id)

    link = UserSkillEvidence(user_skill_id=user_skill.id, evidence_id=evidence.id)
    db.add(link)
    db.flush()
    return link


def set_status(db: Session, user_skill: UserSkill, new_status: VerificationStatus) -> UserSkill:
    """Explicitly set a UserSkill's status, enforcing the evidence requirement.

    VERIFIED and PARTIAL need at least one linked Evidence. PROVISIONAL and
    NOT_VERIFIED are always allowed, including downgrading a VERIFIED/PARTIAL skill.
    """
    db.flush()

    if new_status in _STATUSES_REQUIRING_EVIDENCE and _linked_evidence_count(db, user_skill) == 0:
        raise InsufficientEvidenceError(user_skill.id, new_status.name)

    user_skill.status = new_status
    db.flush()
    return user_skill
