from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base


class JobRequirement(Base):
    """One requirement extracted from a JobDescription.

    `requirement_text` keeps the extracted phrase verbatim. `skill_id` is the
    canonical-taxonomy mapping and is nullable on purpose: a requirement that
    doesn't match a known Skill stays unmapped rather than causing a new Skill
    to be invented (PROJECT_RULES.md section 2.3). Verification status is NOT
    stored here — that belongs to the comparison step.
    """

    __tablename__ = "job_requirements"

    id: Mapped[int] = mapped_column(primary_key=True)
    job_description_id: Mapped[int] = mapped_column(
        ForeignKey("job_descriptions.id"), nullable=False
    )
    skill_id: Mapped[int | None] = mapped_column(ForeignKey("skills.id"), nullable=True)

    requirement_text: Mapped[str] = mapped_column(Text, nullable=False)
    is_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    job_description: Mapped["JobDescription"] = relationship(
        "JobDescription", back_populates="requirements"
    )
    skill: Mapped["Skill | None"] = relationship("Skill", back_populates="job_requirements")
    comparison_results: Mapped[list["ComparisonResult"]] = relationship(
        "ComparisonResult", back_populates="job_requirement"
    )
