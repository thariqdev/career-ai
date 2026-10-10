"""POST /assistant/ask and /assistant/ask/stream: the Career AI assistant (RAG over your data).

/ask returns the whole answer at once. /ask/stream sends the same answer as NDJSON (one
JSON object per line) so the chat can show it appearing word by word:
    {"type": "meta", "sources": [...], "retrieval": ..., "note": ..., "searched": N}
    {"type": "delta", "text": "Here's "}      <- many of these; joined, they are the answer
    {"type": "done"}
All database work happens BEFORE streaming starts, so the stream only sends prepared text.

Read-only: it searches chunks built from your current data and answers with numbered
sources. Retrieval is keyword search, or hybrid keyword + meaning search when
OLLAMA_EMBED_MODEL is set. Answers are extractive (no language model writes them yet, so
nothing can be made up).
"""

import json
from collections.abc import Iterator

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.models import User
from app.dependencies import get_current_user, get_db
from app.rag import assistant
from app.rag.assistant import MAX_QUESTION_CHARS

router = APIRouter(prefix="/assistant", tags=["assistant"])


class AskRequest(BaseModel):
    question: str = Field(max_length=MAX_QUESTION_CHARS)


class SourceResponse(BaseModel):
    number: int
    kind: str
    title: str
    text: str
    link: str
    score: float


class AskResponse(BaseModel):
    answer: str
    sources: list[SourceResponse]
    searched: int
    retrieval: str  # "bm25" (keyword) or "hybrid" (keyword + meaning)
    note: str | None  # e.g. why meaning search wasn't used


@router.post("/ask", response_model=AskResponse)
def ask(
    payload: AskRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AskResponse:
    result = assistant.ask(db, user, payload.question)
    return AskResponse(
        answer=result.answer,
        sources=[
            SourceResponse(
                number=s.number,
                kind=s.chunk.kind,
                title=s.chunk.title,
                text=s.chunk.text,
                link=s.chunk.link,
                score=s.score,
            )
            for s in result.sources
        ],
        searched=result.searched,
        retrieval=result.retrieval,
        note=result.note,
    )


@router.post("/ask/stream")
def ask_stream(
    payload: AskRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    """The same answer as /ask, streamed as NDJSON (see the module docstring)."""
    result = ask(payload, user, db)  # validation (422) and all DB work happen here, first

    def events() -> Iterator[str]:
        meta = {"type": "meta", **result.model_dump(exclude={"answer"})}
        yield json.dumps(meta) + "\n"
        for piece in assistant.stream_pieces(result.answer):
            yield json.dumps({"type": "delta", "text": piece}) + "\n"
        yield json.dumps({"type": "done"}) + "\n"

    return StreamingResponse(events(), media_type="application/x-ndjson")
