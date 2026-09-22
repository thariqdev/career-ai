from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

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

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    user: Mapped["User"] = relationship("User", back_populates="job_descriptions")
