from datetime import datetime

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base


class User(Base):
    """One person's account and the career profile stored for them (stage 97: accounts).

    password_hash is None for an account that can't log in yet (the old built-in user
    before it is claimed). failed_logins / locked_until slow down password guessing.
    """

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    full_name: Mapped[str | None] = mapped_column(String, nullable=True)
    password_hash: Mapped[str | None] = mapped_column(String, nullable=True)
    failed_logins: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
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
    cv_skill_presences: Mapped[list["CVSkillPresence"]] = relationship(
        "CVSkillPresence", back_populates="user"
    )
    learning_progress: Mapped[list["LearningProgress"]] = relationship(
        "LearningProgress", back_populates="user"
    )
