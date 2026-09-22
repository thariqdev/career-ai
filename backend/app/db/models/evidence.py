from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.models.enums import EvidenceType
from database import Base


class Evidence(Base):
    """A concrete, reviewable record backing a VERIFIED claim.

    Per PROJECT_RULES.md sections 4 and 8, every VERIFIED skill must trace back to
    at least one Evidence record. Each record optionally links to the underlying
    WorkExperience/Project/Education it was drawn from so the claim stays
    traceable to something reviewable, not just an assertion.
    """

    __tablename__ = "evidence"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)

    evidence_type: Mapped[EvidenceType] = mapped_column(
        SAEnum(EvidenceType, name="evidence_type"), nullable=False
    )
    title: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    url: Mapped[str | None] = mapped_column(String, nullable=True)

    work_experience_id: Mapped[int | None] = mapped_column(
        ForeignKey("work_experiences.id"), nullable=True
    )
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id"), nullable=True)
    education_id: Mapped[int | None] = mapped_column(ForeignKey("educations.id"), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    user: Mapped["User"] = relationship("User", back_populates="evidence_records")
    work_experience: Mapped["WorkExperience | None"] = relationship(
        "WorkExperience", back_populates="evidence_records"
    )
    project: Mapped["Project | None"] = relationship(
        "Project", back_populates="evidence_records"
    )
    education: Mapped["Education | None"] = relationship(
        "Education", back_populates="evidence_records"
    )
    user_skill_links: Mapped[list["UserSkillEvidence"]] = relationship(
        "UserSkillEvidence", back_populates="evidence"
    )
