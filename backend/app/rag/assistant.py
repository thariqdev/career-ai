"""The assistant: question -> retrieve the best chunks -> answer with numbered sources.

The full RAG loop is CHUNK -> RETRIEVE -> GENERATE. Stage 65 (this file) does the first
two for real and keeps GENERATE "extractive": the answer IS the retrieved notes, numbered
[1], [2]... like citations. That means it can never say anything your data doesn't say,
and it shows exactly what the retriever found, which is the part to get right first.
Stage 67 replaces `_compose` with a language model that is given only these same notes.

When nothing scores above zero, the assistant says so instead of guessing: an honest
"I couldn't find that" is part of RAG, not a failure of it.
"""

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.exceptions import EmptyQuestionError
from app.db.models import User
from app.rag.bm25 import BM25Index
from app.rag.chunker import Chunk, build_chunks

TOP_K = 4
# Stemming measured worse on our notes (app/rag/evaluate.py), so it's off.
USE_STEMMING = False
MAX_QUESTION_CHARS = 500
NOT_FOUND = (
    "I couldn't find anything about that in your Career AI data. Try asking about a skill, "
    "a job, your proof, or what to learn next."
)


@dataclass(frozen=True)
class Source:
    number: int  # [1], [2]... as cited in the answer
    chunk: Chunk
    score: float


@dataclass(frozen=True)
class AssistantAnswer:
    answer: str
    sources: list[Source]
    searched: int  # how many chunks were searched


def _compose(sources: list[Source]) -> str:
    """Extractive answer: the retrieved notes themselves, each tagged with its number."""
    if not sources:
        return NOT_FOUND
    lines = ["Here's what I found in your data:"]
    lines += [f"[{s.number}] {s.chunk.text}" for s in sources]
    return "\n\n".join(lines)


def ask(db: Session, user: User, question: str, top_k: int = TOP_K) -> AssistantAnswer:
    question = question.strip()
    if not question:
        raise EmptyQuestionError()
    question = question[:MAX_QUESTION_CHARS]

    chunks = build_chunks(db, user)  # 1. CHUNK (fresh from PostgreSQL)
    index = BM25Index([f"{c.title}. {c.text}" for c in chunks], stem=USE_STEMMING)  # 2. RETRIEVE...
    hits = index.search(question, top_k)
    sources = [Source(n, chunks[hit.index], round(hit.score, 3)) for n, hit in enumerate(hits, start=1)]
    return AssistantAnswer(_compose(sources), sources, len(chunks))  # 3. GENERATE (extractive)
