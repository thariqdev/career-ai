from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Text, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.models.enums import VerificationStatus
from database import Base


class ComparisonResult(Base):
    """The recorded outcome of comparing one JobRequirement against the user's evidence.

    Rows are append-only snapshots: there is deliberately no unique constraint on
    job_requirement_id, so re-running a comparison later (e.g. after new evidence
    is added) creates a new row and keeps the history. `user_skill_id` is nullable:
    null means no UserSkill exists for the requirement (unmapped requirement, or a
    skill the user never claimed). `knowledge_status` has no default on purpose —
    the backend service that runs the comparison (not yet built) must decide it
    explicitly; this model only stores the decision. Every row cites the Evidence it
    relied on through ComparisonResultEvidence (PROJECT_RULES.md section 8).
    """

    __tablename__ = "comparison_results"

    id: Mapped[int] = mapped_column(primary_key=True)
    job_requirement_id: Mapped[int] = mapped_column(
        ForeignKey("job_requirements.id"), nullable=False
    )
    user_skill_id: Mapped[int | None] = mapped_column(
        ForeignKey("user_skills.id"), nullable=True
    )

    # The Postgres enum type is created and owned by the user_skills migration.
    knowledge_status: Mapped[VerificationStatus] = mapped_column(
        SAEnum(VerificationStatus, name="verification_status", create_type=False),
        nullable=False,
    )
    reasoning: Mapped[str] = mapped_column(Text, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    job_requirement: Mapped["JobRequirement"] = relationship(
        "JobRequirement", back_populates="comparison_results"
    )
    user_skill: Mapped["UserSkill | None"] = relationship(
        "UserSkill", back_populates="comparison_results"
    )
    evidence_links: Mapped[list["ComparisonResultEvidence"]] = relationship(
        "ComparisonResultEvidence", back_populates="comparison_result"
    )


class ComparisonResultEvidence(Base):
    """Plain many-to-many join table: which Evidence rows a ComparisonResult relied on.

    Same pattern as UserSkillEvidence: no extra columns, so the two foreign keys
    together form the primary key.
    """

    __tablename__ = "comparison_result_evidence"

    comparison_result_id: Mapped[int] = mapped_column(
        ForeignKey("comparison_results.id"), primary_key=True
    )
    evidence_id: Mapped[int] = mapped_column(ForeignKey("evidence.id"), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    comparison_result: Mapped["ComparisonResult"] = relationship(
        "ComparisonResult", back_populates="evidence_links"
    )
    evidence: Mapped["Evidence"] = relationship(
        "Evidence", back_populates="comparison_result_links"
    )
