from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Text, UniqueConstraint, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.models.enums import VerificationStatus
from database import Base


class UserSkill(Base):
    """A user's claim to a skill, and its verification status.

    This is the association *object* (not a bare join table) linking User and
    Skill, because the link itself carries data: status and notes. A user may
    have at most one UserSkill row per Skill (enforced by the unique constraint
    below) — the row's status changes over time as evidence is linked, rather
    than new rows being created.
    """

    __tablename__ = "user_skills"
    __table_args__ = (UniqueConstraint("user_id", "skill_id", name="uq_user_skill"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    skill_id: Mapped[int] = mapped_column(ForeignKey("skills.id"), nullable=False)

    status: Mapped[VerificationStatus] = mapped_column(
        SAEnum(VerificationStatus, name="verification_status"),
        nullable=False,
        default=VerificationStatus.PROVISIONAL,
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    user: Mapped["User"] = relationship("User", back_populates="user_skills")
    skill: Mapped["Skill"] = relationship("Skill", back_populates="user_skills")
    evidence_links: Mapped[list["UserSkillEvidence"]] = relationship(
        "UserSkillEvidence", back_populates="user_skill"
    )
    comparison_results: Mapped[list["ComparisonResult"]] = relationship(
        "ComparisonResult", back_populates="user_skill"
    )


class UserSkillEvidence(Base):
    """Plain many-to-many join table: which Evidence rows back a UserSkill claim.

    No extra columns are needed on the link itself (unlike UserSkill), so this
    uses a composite primary key of the two foreign keys instead of a surrogate
    id — there's no reason for anything else to reference a row in this table.
    """

    __tablename__ = "user_skill_evidence"

    user_skill_id: Mapped[int] = mapped_column(
        ForeignKey("user_skills.id"), primary_key=True
    )
    evidence_id: Mapped[int] = mapped_column(ForeignKey("evidence.id"), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    user_skill: Mapped["UserSkill"] = relationship("UserSkill", back_populates="evidence_links")
    evidence: Mapped["Evidence"] = relationship("Evidence", back_populates="user_skill_links")
