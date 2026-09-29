from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base


class CVSkillPresence(Base):
    """Whether a skill is currently listed on the user's CV — a fact only the user supplies.

    This is never inferred by any service: not by verification_service (which decides
    knowledge status), not by comparison_service, not by skill_service. Nothing writes to
    this table automatically.

    It is deliberately INDEPENDENT of UserSkill.status (PROJECT_RULES.md section 5): a
    skill can be VERIFIED and not on the CV, or on the CV and NOT_VERIFIED — this table
    doesn't reference UserSkill, Evidence, or ComparisonResult at all, and nothing here
    changes what those tables say. A skill with no row here simply has never had its CV
    presence stated, rather than being recorded as some third "unknown" value.

    Building a combined "knowledge + CV" view is a later, separate task — out of scope here.
    """

    __tablename__ = "cv_skill_presences"
    __table_args__ = (UniqueConstraint("user_id", "skill_id", name="uq_cv_skill_presence"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    skill_id: Mapped[int] = mapped_column(ForeignKey("skills.id"), nullable=False)

    present: Mapped[bool] = mapped_column(Boolean, nullable=False)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    user: Mapped["User"] = relationship("User", back_populates="cv_skill_presences")
    skill: Mapped["Skill"] = relationship("Skill", back_populates="cv_skill_presences")
