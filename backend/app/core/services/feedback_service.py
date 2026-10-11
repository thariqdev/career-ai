"""Ratings on assistant answers (RAG stage 77): save (or change) one, list them.

Same conventions as the other services: flush, never commit (the route owns the
transaction). One row per answer: rating an answer again replaces the earlier rating.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AssistantFeedback, User
from app.db.models.enums import FeedbackRating


def save_feedback(
    db: Session,
    user: User,
    *,
    message_id: str,
    rating: FeedbackRating,
    question: str,
    answer: str,
    sources: list[dict],
    retrieval: str | None,
    written_by: str | None,
    comment: str | None,
) -> AssistantFeedback:
    """Create the rating, or replace this answer's earlier one. A blank comment is None."""
    comment = (comment or "").strip() or None
    feedback = db.scalar(
        select(AssistantFeedback).where(AssistantFeedback.user_id == user.id, AssistantFeedback.message_id == message_id)
    )
    if feedback is None:
        feedback = AssistantFeedback(user_id=user.id, message_id=message_id)
        db.add(feedback)
    feedback.rating = rating
    feedback.comment = comment
    feedback.question = question
    feedback.answer = answer
    feedback.sources = sources
    feedback.retrieval = retrieval
    feedback.written_by = written_by
    db.flush()
    return feedback


def list_feedback(db: Session, user: User, rating: FeedbackRating | None = None) -> list[AssistantFeedback]:
    """Newest first; only one rating if asked."""
    query = select(AssistantFeedback).where(AssistantFeedback.user_id == user.id)
    if rating is not None:
        query = query.where(AssistantFeedback.rating == rating)
    return list(db.scalars(query.order_by(AssistantFeedback.created_at.desc(), AssistantFeedback.id.desc())))
