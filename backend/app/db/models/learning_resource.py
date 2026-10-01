from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.models.enums import LearningMode
from database import Base


class LearningResource(Base):
    """A link the user saved as a learning resource for a skill, under one learning mode.

    Only ever created by the user (PROJECT_RULES.md section 15: curated, reviewable,
    editable). Nothing writes here automatically, and the app never fetches the URL.
    Resources belong to the skill, not to a user, like the skill taxonomy itself.
    YouTube search links are NOT stored here: they're derived per request
    (learning_service.youtube_search_url).
    """

    __tablename__ = "learning_resources"
    __table_args__ = (
        UniqueConstraint("skill_id", "mode", "url", name="uq_learning_resource"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    skill_id: Mapped[int] = mapped_column(ForeignKey("skills.id"), nullable=False)
    mode: Mapped[LearningMode] = mapped_column(
        SAEnum(LearningMode, name="learning_mode"), nullable=False
    )
    title: Mapped[str] = mapped_column(String, nullable=False)
    url: Mapped[str] = mapped_column(String, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    skill: Mapped["Skill"] = relationship("Skill", back_populates="learning_resources")
