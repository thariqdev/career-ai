from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base


class Education(Base):
    """A degree, certification, or formal training record."""

    __tablename__ = "educations"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)

    institution: Mapped[str] = mapped_column(String, nullable=False)
    degree: Mapped[str | None] = mapped_column(String, nullable=True)
    field_of_study: Mapped[str | None] = mapped_column(String, nullable=True)
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    user: Mapped["User"] = relationship("User", back_populates="educations")
    evidence_records: Mapped[list["Evidence"]] = relationship(
        "Evidence", back_populates="education"
    )
