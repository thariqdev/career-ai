"""The user's own record of how far they are in studying a skill.

PROJECT_RULES.md sections 14 and 16: progress is stored only when the user states it,
and mastery is never inferred from it. This service reads and writes LearningProgress
ONLY: it never touches UserSkill, Evidence, or verification status, so "finished
studying" can never turn into "verified".

"Not started" is represented by having no row (status None here), so there is only one
way to say it: setting it deletes the row if one exists.

Same conventions as the other services: plain functions taking a Session, no HTTP
knowledge, flush but never commit, and flush before reading (autoflush=False).
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import LearningProgress, Skill, User
from app.db.models.enums import LearningStatus


def get_progress(db: Session, user: User, skill: Skill) -> LearningProgress | None:
    db.flush()
    return db.scalar(
        select(LearningProgress).where(
            LearningProgress.user_id == user.id, LearningProgress.skill_id == skill.id
        )
    )


def list_progress(db: Session, user: User) -> list[LearningProgress]:
    """Every skill the user has started or finished studying, ordered by skill name."""
    db.flush()
    return list(
        db.scalars(
            select(LearningProgress)
            .join(Skill, LearningProgress.skill_id == Skill.id)
            .where(LearningProgress.user_id == user.id)
            .order_by(Skill.name, Skill.id)
        )
    )


def set_progress(
    db: Session, user: User, skill: Skill, status: LearningStatus | None
) -> LearningProgress | None:
    """Set the user's progress on a skill; None means "not started" and removes the row."""
    existing = get_progress(db, user, skill)

    if status is None:
        if existing is not None:
            db.delete(existing)
            db.flush()
        return None

    if existing is None:
        existing = LearningProgress(user=user, skill=skill, status=status)
        db.add(existing)
    else:
        existing.status = status
    db.flush()
    return existing
