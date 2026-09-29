"""Combines UserSkill.status and CVSkillPresence.present into one read-only view.

READ-ONLY, same reasoning as comparison_service.skill_gaps: this derives a view from
two facts that change independently (knowledge status and CV presence) without storing
anything new. Nothing here writes a CVSkillPresence — creating/updating one is a
separate, later task; this module only reads.

Recommendations are fixed templates, never LLM-generated or free-form.

Inputs per (user, skill) (PROJECT_RULES.md section 5):
- knowledge_status: the UserSkill.status for this pair if a UserSkill row exists,
  else None. None ("never claimed") is kept distinct from NOT_VERIFIED ("an explicit
  claim exists and isn't backed by evidence") — they are NOT the same thing and must
  not be collapsed.
- cv_present: True only if a CVSkillPresence row exists for this pair with
  present=True. A missing row and a present=False row are treated identically (both
  mean "not present").

Decision table (exact; generalizes PROJECT_RULES.md section 5's two worked examples
to every combination — implemented once, in _derive, below):

cv_status:
    cv_present is True                                            -> PRESENT
    cv_present is False and knowledge_status in {VERIFIED, PARTIAL}       -> MISSING_FROM_CV
    cv_present is False and knowledge_status in {PROVISIONAL, NOT_VERIFIED, None} -> NOT_PRESENT

recommendation:
    knowledge_status in {VERIFIED, PARTIAL} and cv_status == MISSING_FROM_CV
        -> "Consider adding {skill} to your CV — you have {status} evidence for it."
    cv_status == PRESENT and knowledge_status in {None, NOT_VERIFIED, PROVISIONAL}
        -> "{skill} is listed on your CV without verified evidence. Add evidence
            before claiming it, or remove it from your CV."
    anything else (VERIFIED+PRESENT, PARTIAL+PRESENT, NOT_PRESENT+anything not
    covered above) -> None (nothing actionable to say)

Conventions (same as the other services): plain functions taking a Session, no HTTP
knowledge, flush before reading because SessionLocal uses autoflush=False, no writes.
"""

import enum
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import CVSkillPresence, Skill, User, UserSkill
from app.db.models.enums import VerificationStatus

_CLAIMS_NEEDING_EVIDENCE = {VerificationStatus.VERIFIED, VerificationStatus.PARTIAL}
_UNPROVEN_STATUSES = {VerificationStatus.PROVISIONAL, VerificationStatus.NOT_VERIFIED, None}


class CVStatus(str, enum.Enum):
    """Whether a skill is present on the CV. Plain Python only — never a DB column."""

    PRESENT = "present"
    MISSING_FROM_CV = "missing_from_cv"
    NOT_PRESENT = "not_present"


@dataclass(frozen=True)
class CombinedSkillStatus:
    """One skill's knowledge status and CV status side by side, plus any recommendation."""

    skill: Skill
    knowledge_status: VerificationStatus | None
    cv_status: CVStatus
    recommendation: str | None


def _derive(
    skill: Skill, knowledge_status: VerificationStatus | None, cv_present: bool
) -> CombinedSkillStatus:
    """Apply the decision table from the module docstring. The one place it's implemented."""
    if cv_present:
        cv_status = CVStatus.PRESENT
    elif knowledge_status in _CLAIMS_NEEDING_EVIDENCE:
        cv_status = CVStatus.MISSING_FROM_CV
    else:
        cv_status = CVStatus.NOT_PRESENT

    recommendation: str | None = None
    if knowledge_status in _CLAIMS_NEEDING_EVIDENCE and cv_status is CVStatus.MISSING_FROM_CV:
        recommendation = (
            f"Consider adding {skill.name} to your CV — "
            f"you have {knowledge_status.name.lower()} evidence for it."
        )
    elif cv_status is CVStatus.PRESENT and knowledge_status in _UNPROVEN_STATUSES:
        recommendation = (
            f"{skill.name} is listed on your CV without verified evidence. "
            "Add evidence before claiming it, or remove it from your CV."
        )

    return CombinedSkillStatus(
        skill=skill,
        knowledge_status=knowledge_status,
        cv_status=cv_status,
        recommendation=recommendation,
    )


def combined_status(db: Session, user: User, skill: Skill) -> CombinedSkillStatus:
    """The combined knowledge/CV view for one (user, skill) pair."""
    db.flush()  # autoflush=False: make pending state visible before reading

    user_skill = db.scalar(
        select(UserSkill).where(UserSkill.user_id == user.id, UserSkill.skill_id == skill.id)
    )
    cv_presence = db.scalar(
        select(CVSkillPresence).where(
            CVSkillPresence.user_id == user.id, CVSkillPresence.skill_id == skill.id
        )
    )
    knowledge_status = user_skill.status if user_skill is not None else None
    cv_present = cv_presence is not None and cv_presence.present
    return _derive(skill, knowledge_status, cv_present)


def combined_status_for_all(db: Session, user: User) -> list[CombinedSkillStatus]:
    """The combined view for every skill with a UserSkill or CVSkillPresence row.

    A skill with neither is excluded — there is nothing to say about it. Three queries
    total (this user's UserSkills, this user's CVSkillPresences, the relevant Skills),
    joined in Python — not one query per skill.
    """
    db.flush()

    user_skills = list(db.scalars(select(UserSkill).where(UserSkill.user_id == user.id)))
    cv_presences = list(
        db.scalars(select(CVSkillPresence).where(CVSkillPresence.user_id == user.id))
    )
    user_skill_by_skill_id = {row.skill_id: row for row in user_skills}
    cv_presence_by_skill_id = {row.skill_id: row for row in cv_presences}

    relevant_skill_ids = user_skill_by_skill_id.keys() | cv_presence_by_skill_id.keys()
    if not relevant_skill_ids:
        return []

    skills = db.scalars(
        select(Skill).where(Skill.id.in_(relevant_skill_ids)).order_by(Skill.name, Skill.id)
    )

    results = []
    for skill in skills:
        user_skill = user_skill_by_skill_id.get(skill.id)
        cv_presence = cv_presence_by_skill_id.get(skill.id)
        knowledge_status = user_skill.status if user_skill is not None else None
        cv_present = cv_presence is not None and cv_presence.present
        results.append(_derive(skill, knowledge_status, cv_present))
    return results
