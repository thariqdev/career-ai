from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.enums import FeedbackRating
from database import Base


class AssistantFeedback(Base):
    """A 👍 or 👎 on one assistant answer, with what the assistant did (RAG stage 77).

    The feedback loop: a 👎 is reviewed and turned into a test case
    (app/rag/feedback_report.py), so real failures become part of the evaluation. Stored
    only in this database; nothing is sent anywhere.

    message_id is the chat's own id for the answer, so rating the same answer again
    replaces the earlier rating instead of adding a row.
    """

    __tablename__ = "assistant_feedback"
    __table_args__ = (UniqueConstraint("user_id", "message_id", name="uq_assistant_feedback_message"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    message_id: Mapped[str] = mapped_column(String(64), nullable=False)
    rating: Mapped[FeedbackRating] = mapped_column(SAEnum(FeedbackRating, name="feedback_rating"), nullable=False)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    answer: Mapped[str] = mapped_column(Text, nullable=False)
    # What the assistant used: [{"number": 1, "kind": "skill", "title": "Python"}, ...]
    sources: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    retrieval: Mapped[str | None] = mapped_column(String(16), nullable=True)  # bm25 | vector | hybrid
    written_by: Mapped[str | None] = mapped_column(String(16), nullable=True)  # ai | notes

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
