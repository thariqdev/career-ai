from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base


class User(Base):
    """The single career profile this system stores verified data for."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    full_name: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    projects: Mapped[list["Project"]] = relationship("Project", back_populates="user")
    work_experiences: Mapped[list["WorkExperience"]] = relationship(
        "WorkExperience", back_populates="user"
    )
    educations: Mapped[list["Education"]] = relationship("Education", back_populates="user")
    evidence_records: Mapped[list["Evidence"]] = relationship("Evidence", back_populates="user")
    user_skills: Mapped[list["UserSkill"]] = relationship("UserSkill", back_populates="user")
    job_descriptions: Mapped[list["JobDescription"]] = relationship(
        "JobDescription", back_populates="user"
    )
