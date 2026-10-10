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
from typing import Literal

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.models import User
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
