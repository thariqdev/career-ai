from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, String, Text, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.models.enums import ApplicationStatus
from database import Base


class JobDescription(Base):
    """A pasted job posting, stored verbatim.

    This is the raw-capture point for the job-analysis flow. It intentionally
    holds only the original text plus optional user-supplied labels — no
    extraction or requirement parsing happens here. Structured requirements
    (JobRequirement, not yet built) will later FK back to this record, keeping
    the traceable original separate from anything derived from it.
    """

    __tablename__ = "job_descriptions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)

    title: Mapped[str | None] = mapped_column(String, nullable=True)
    company: Mapped[str | None] = mapped_column(String, nullable=True)
    source_url: Mapped[str | None] = mapped_column(String, nullable=True)
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)

    # The user's own application tracking (task 58). Never inferred: only the user sets it.
    application_status: Mapped[ApplicationStatus] = mapped_column(
        SAEnum(ApplicationStatus, name="application_status"),
        nullable=False,
        default=ApplicationStatus.SAVED,
        server_default=ApplicationStatus.SAVED.name,
    )
    applied_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    application_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    # The next interview (task 60): only while applied or interviewing; set by the user.
    next_interview_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    user: Mapped["User"] = relationship("User", back_populates="job_descriptions")
    requirements: Mapped[list["JobRequirement"]] = relationship(
        "JobRequirement", back_populates="job_description"
    )
