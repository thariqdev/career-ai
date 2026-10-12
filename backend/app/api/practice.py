"""GET /practice/rag-questions: interview flashcards from docs/RAG_GUIDE.md (stage 85).

Read-only and not career data: the cards come from the guide, and practice progress is
kept in the browser (frontend lib/leitner.ts), never in the database.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.models import User
from app.dependencies import get_current_user, get_db
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


@router.get("/job-questions", response_model=list[CardResponse])
def job_questions(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[practice.Card]:
    """Flashcards from each job's interview prep sheet (stage 86): stage = the job's id,
    stage_title = its name. Read-only."""
    return practice.job_cards(db, user)
