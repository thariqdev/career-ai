"""POST /assistant/ask: the Career AI assistant (RAG over your own data; see app/rag).

Read-only: it searches chunks built from your current data and answers with numbered
sources. Retrieval is keyword search, or hybrid keyword + meaning search when
OLLAMA_EMBED_MODEL is set. Answers are extractive (no language model writes them yet, so
nothing can be made up).
"""

from fastapi import APIRouter, Depends
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
