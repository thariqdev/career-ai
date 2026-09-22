from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base


class SkillAlias(Base):
    __tablename__ = "skill_aliases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    skill_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("skills.id"), nullable=False
    )
    alias: Mapped[str] = mapped_column(String, nullable=False)

    skill: Mapped["Skill"] = relationship("Skill", back_populates="aliases")
