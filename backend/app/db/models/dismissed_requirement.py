from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class DismissedRequirement(Base):
    """A "not for this job" note: the user removed this skill's requirement from this job.

    Written only when the user removes a requirement (job_description_service), and read
    by requirement extraction so re-reading the posting doesn't add it back. Keyed on the
    skill, not the wording, so "Postgres" and "PostgreSQL" count as one. Deleting the note
    ("Allow again") only lets a later re-read find the skill; it re-adds nothing itself.

    Job-side bookkeeping, not user data about skills: it goes with its job, follows a skill
    merge, and is dropped when its skill is deleted.
    """

    __tablename__ = "dismissed_requirements"
    __table_args__ = (
        UniqueConstraint("job_description_id", "skill_id", name="uq_dismissed_requirement"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    job_description_id: Mapped[int] = mapped_column(
        ForeignKey("job_descriptions.id"), nullable=False
    )
    skill_id: Mapped[int] = mapped_column(ForeignKey("skills.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
