"""Enforces the evidence rules on UserSkill (PROJECT_RULES.md sections 3, 4, 8, 12).

This module is the ONLY place that should write UserSkill.status or create or remove
UserSkillEvidence links. PostgreSQL cannot cheaply enforce "VERIFIED requires
linked evidence" (a column constraint cannot count rows in another table
without a trigger), so the rule lives here and every caller must go through it.

The rule has to survive removals too, not just additions: unlink_evidence refuses to
remove the last link of a VERIFIED/PARTIAL claim (LastEvidenceError), because that
would leave a "verified" skill with no proof. It never lowers the status itself; the
user does that explicitly via set_status, then unlinks.

Conventions:
- Plain functions taking a SQLAlchemy Session; no HTTP or FastAPI knowledge.
- Functions flush but never commit: the caller owns the transaction.
- Linking or unlinking evidence never changes status. Status only changes through an
  explicit set_status call.
"""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.exceptions import (
    EvidenceAlreadyLinkedError,
    EvidenceNotLinkedError,
    EvidenceOwnershipError,
    InsufficientEvidenceError,
    LastEvidenceError,
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


def unlink_evidence(db: Session, user_skill: UserSkill, evidence_id: int) -> None:
    """Detach one Evidence from a UserSkill; the Evidence itself is kept.

    Refused if it isn't linked (EvidenceNotLinkedError), or if it's the claim's last
    evidence while the claim is VERIFIED/PARTIAL (LastEvidenceError). The count comes
    from the database, not the possibly stale user_skill.evidence_links collection.
    """
    db.flush()

    link = db.scalar(
        select(UserSkillEvidence).where(
            UserSkillEvidence.user_skill_id == user_skill.id,
            UserSkillEvidence.evidence_id == evidence_id,
        )
    )
    if link is None:
        raise EvidenceNotLinkedError(user_skill.id, evidence_id)

    if user_skill.status in _STATUSES_REQUIRING_EVIDENCE and _linked_evidence_count(db, user_skill) <= 1:
        raise LastEvidenceError(user_skill.skill.name, user_skill.status.name)

    db.delete(link)
    db.flush()
    db.expire(user_skill, ["evidence_links"])  # so the response reflects the removal


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
