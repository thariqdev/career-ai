from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base



class Skill(Base):
    __tablename__ = "skills"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    category: Mapped[str | None] = mapped_column(String, nullable=True)

    aliases: Mapped[list["SkillAlias"]] = relationship(
        "SkillAlias", back_populates="skill"
    )
    user_skills: Mapped[list["UserSkill"]] = relationship("UserSkill", back_populates="skill")
    job_requirements: Mapped[list["JobRequirement"]] = relationship(
        "JobRequirement", back_populates="skill"
    )
    cv_skill_presences: Mapped[list["CVSkillPresence"]] = relationship(
        "CVSkillPresence", back_populates="skill"
    )
    learning_resources: Mapped[list["LearningResource"]] = relationship(
        "LearningResource", back_populates="skill"
    )

