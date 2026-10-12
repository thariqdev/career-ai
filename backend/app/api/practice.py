"""GET /practice/rag-questions: interview flashcards from docs/RAG_GUIDE.md (stage 85).

Read-only and not career data: the cards come from the guide, and practice progress is
kept in the browser (frontend lib/leitner.ts), never in the database.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.rag import practice

router = APIRouter(prefix="/practice", tags=["practice"])


class CardResponse(BaseModel):
    id: str
    stage: str
    stage_title: str
    question: str
    answer: str


@router.get("/rag-questions", response_model=list[CardResponse])
def rag_questions() -> list[practice.Card]:
    try:
        return practice.cards()
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail="The RAG guide (docs/RAG_GUIDE.md) isn't available.") from error
