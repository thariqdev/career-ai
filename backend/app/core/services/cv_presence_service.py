"""The single place that writes CVSkillPresence ("is this skill on my CV?").

Used by both the per-skill badge toggle and the CV upload's confirm step, so the two
can't drift. Kept separate from cv_service, which is read-only by design.

It's an UPSERT, not check-then-409: restating a fact about your own CV isn't a conflict
the way a duplicate skill claim is, and CVSkillPresence allows one row per (user, skill).
It never touches UserSkill or Evidence: being on the CV is a claim, not proof.

Same conventions as the other services: plain functions taking a Session, no HTTP
knowledge, flush but never commit.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import CVSkillPresence, Skill, User


def set_cv_presence(db: Session, user: User, skill: Skill, present: bool) -> CVSkillPresence:
    db.flush()
    presence = db.scalar(
        select(CVSkillPresence).where(
            CVSkillPresence.user_id == user.id, CVSkillPresence.skill_id == skill.id
        )
    )
    if presence is None:
        presence = CVSkillPresence(user=user, skill=skill, present=present)
        db.add(presence)
    else:
        presence.present = present
    db.flush()
    return presence
