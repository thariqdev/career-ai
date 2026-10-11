"""POST /assistant/ask and /assistant/ask/stream: the Career AI assistant (RAG over your data).

/ask returns the whole answer at once. /ask/stream sends it as NDJSON (one JSON object per
line) so the chat can show it appearing word by word:
    {"type": "meta", "sources": [...], "retrieval": ..., "note": ..., "searched": N}
    {"type": "delta", "text": "You're "}      <- many; joined, they are the answer...
    {"type": "replace", "text": "..."}        <- ...unless the checks changed it (optional)
    {"type": "done", "written_by": "ai" | "notes", "note": ...}

`history` carries the last few chat turns so follow-ups ("and how do I learn it?") work.
All database work (retrieval) happens BEFORE streaming starts; only the model (or the
notes) is streamed. The model is the local Ollama one named by OLLAMA_CHAT_MODEL; without
it the answer is the notes themselves.
"""

import json
from collections.abc import Iterator
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.core.services import feedback_service
from app.db.models import User
from app.db.models.enums import FeedbackRating
from app.dependencies import get_current_user, get_db
from app.rag import assistant
from app.rag.assistant import MAX_QUESTION_CHARS, Source
from app.rag.generate import Turn

router = APIRouter(prefix="/assistant", tags=["assistant"])


class TurnIn(BaseModel):
    role: Literal["user", "assistant"]
    text: str = Field(max_length=4000)


class AskRequest(BaseModel):
    question: str = Field(max_length=MAX_QUESTION_CHARS)
    history: list[TurnIn] = Field(default_factory=list, max_length=20)


class SourceResponse(BaseModel):
    number: int
    kind: str
    title: str
    text: str
    link: str
    score: float

    @classmethod
    def from_source(cls, source: Source) -> "SourceResponse":
        c = source.chunk
        return cls(number=source.number, kind=c.kind, title=c.title, text=c.text, link=c.link, score=source.score)


class AskResponse(BaseModel):
    answer: str
    sources: list[SourceResponse]
    searched: int
    retrieval: str  # "bm25" (keyword) or "hybrid" (keyword + meaning)
    note: str | None  # e.g. why meaning search or the AI writer wasn't used
    written_by: Literal["ai", "notes"]  # an AI wrote it from the notes, or it IS the notes
    action: dict | None = None  # stage 78: a change to confirm (kind, summary, method, path, body)


def _history(payload: AskRequest) -> list[Turn]:
    return [Turn(t.role, t.text) for t in payload.history]


@router.post("/ask", response_model=AskResponse)
def ask(
    payload: AskRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AskResponse:
    result = assistant.ask(db, user, payload.question, history=_history(payload))
    return AskResponse(
        answer=result.answer,
        sources=[SourceResponse.from_source(s) for s in result.sources],
        searched=result.searched,
        retrieval=result.retrieval,
        note=result.note,
        written_by=result.written_by,
        action=result.action.to_dict() if result.action else None,
    )


@router.post("/ask/stream")
def ask_stream(
    payload: AskRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    """The same answer as /ask, streamed as NDJSON (see the module docstring)."""
    history = _history(payload)
    # Validation (422) and all database work happen here, before streaming starts.
    prepared = assistant.prepare(db, user, payload.question, history=history)
    chat = assistant.configured_chat()

    def events() -> Iterator[str]:
        for event in assistant.answer_events(prepared, history, chat):
            if event["type"] == "meta":
                event = {**event, "sources": [SourceResponse.from_source(s).model_dump() for s in event["sources"]]}
            yield json.dumps(event) + "\n"

    return StreamingResponse(events(), media_type="application/x-ndjson")


# --- stage 77: 👍 / 👎 on answers ------------------------------------------------------------


class FeedbackSourceIn(BaseModel):
    number: int
    kind: str = Field(max_length=32)
    title: str = Field(max_length=300)


class FeedbackIn(BaseModel):
    message_id: str = Field(min_length=1, max_length=64)  # the chat's id for the answer
    rating: FeedbackRating
    question: str = Field(min_length=1, max_length=4000)
    answer: str = Field(min_length=1, max_length=20000)
    sources: list[FeedbackSourceIn] = Field(default_factory=list, max_length=10)
    retrieval: Literal["bm25", "vector", "hybrid"] | None = None
    written_by: Literal["ai", "notes"] | None = None
    comment: str | None = Field(default=None, max_length=1000)


class FeedbackOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    message_id: str
    rating: FeedbackRating
    comment: str | None
    question: str
    answer: str
    sources: list[dict]
    retrieval: str | None
    written_by: str | None
    created_at: datetime


@router.post("/feedback", response_model=FeedbackOut)
def rate_answer(
    payload: FeedbackIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Save a 👍 / 👎 on one answer (rating it again replaces the earlier rating)."""
    feedback = feedback_service.save_feedback(
        db,
        user,
        message_id=payload.message_id,
        rating=payload.rating,
        question=payload.question,
        answer=payload.answer,
        sources=[s.model_dump() for s in payload.sources],
        retrieval=payload.retrieval,
        written_by=payload.written_by,
        comment=payload.comment,
    )
    db.commit()
    return feedback


@router.get("/feedback", response_model=list[FeedbackOut])
def list_feedback(
    rating: FeedbackRating | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Your ratings, newest first (?rating=down for the ones to learn from)."""
    return feedback_service.list_feedback(db, user, rating)
