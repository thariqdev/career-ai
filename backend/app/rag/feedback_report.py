"""Turn 👎 answers into test cases: the feedback loop (RAG stage 77).

Run from backend/:   .venv/Scripts/python -m app.rag.feedback_report

Every test set so far was written by hand. Real failures are better: each 👎 in the chat
is stored with what the assistant did (question, answer, sources, search used, who
wrote it, your comment). This report lists them with a draft test case for each:
decide what the right answer must say, then add it to ANSWERS in app/rag/answer_eval.py
(or a question set for retrieval or routing), and the scorecard will guard it from then on.

Read-only: it never changes the database.
"""

import sys
from collections import Counter

from app.db.models import AssistantFeedback
from app.db.models.enums import FeedbackRating


def summary(items: list[AssistantFeedback]) -> str:
    ratings = Counter(f.rating for f in items)
    down = [f for f in items if f.rating == FeedbackRating.DOWN]
    by_writer = Counter(f.written_by or "?" for f in down)
    by_search = Counter(f.retrieval or "?" for f in down)
    return (
        f"{ratings[FeedbackRating.UP]} 👍, {ratings[FeedbackRating.DOWN]} 👎"
        + (f"   👎 by writer: {dict(by_writer)}   by search: {dict(by_search)}" if down else "")
    )


def draft_case(f: AssistantFeedback) -> str:
    """One 👎 as a reviewable draft for app/rag/answer_eval.py."""
    sources = ", ".join(f"[{s.get('number')}] {s.get('kind')}: {s.get('title')}" for s in f.sources) or "none"
    answer = " ".join(f.answer.split())
    return "\n".join(
        [
            f"👎 #{f.id}  {f.created_at:%Y-%m-%d %H:%M}  written by {f.written_by or '?'}, {f.retrieval or '?'} search",
            f"   question: {f.question}",
            f"   answer:   {answer[:300]}{'…' if len(answer) > 300 else ''}",
            f"   sources:  {sources}",
            f"   comment:  {f.comment or '(none)'}",
            "   draft test case (replace TODO with what a right answer must mention):",
            f"     _c({f.question!r}, [\"TODO\"]),",
        ]
    )


def report(items: list[AssistantFeedback]) -> str:
    down = [f for f in items if f.rating == FeedbackRating.DOWN]
    lines = [summary(items), ""]
    if not down:
        lines.append("No 👎 yet: nothing to turn into a test case.")
    lines += [draft_case(f) + "\n" for f in down]
    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    from app.core.services import feedback_service
    from app.core.services.user_service import get_or_create_default_user
    from database import SessionLocal

    with SessionLocal() as db:
        try:
            items = feedback_service.list_feedback(db, get_or_create_default_user(db))
            sys.stdout.write(report(items))
        finally:
            db.rollback()  # read-only
    return 0


if __name__ == "__main__":
    sys.exit(main())
