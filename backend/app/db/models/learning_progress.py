from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, UniqueConstraint, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.models.enums import LearningStatus
from database import Base


class LearningProgress(Base):
    """How far the user says they are in studying a skill — only ever set by the user.

    PROJECT_RULES.md section 14: mastery must never be inferred from studying. This
    table is deliberately INDEPENDENT of UserSkill/Evidence (no FK to either), and
    nothing here changes a skill's verification status: FINISHED means "I finished
    studying", never "I know this". No row means "not started".
    """

    __tablename__ = "learning_progress"
    __table_args__ = (UniqueConstraint("user_id", "skill_id", name="uq_learning_progress"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    skill_id: Mapped[int] = mapped_column(ForeignKey("skills.id"), nullable=False)

    status: Mapped[LearningStatus] = mapped_column(
        SAEnum(LearningStatus, name="learning_status"), nullable=False
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    user: Mapped["User"] = relationship("User", back_populates="learning_progress")
    skill: Mapped["Skill"] = relationship("Skill", back_populates="learning_progress")
