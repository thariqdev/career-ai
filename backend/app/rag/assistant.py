"""The assistant: question -> retrieve the best chunks -> answer with numbered sources.

The full RAG loop is CHUNK -> RETRIEVE -> GENERATE.

RETRIEVE (stages 65-66) has two engines:
- "bm25": keyword search (app/rag/bm25.py). Always available.
- "hybrid": keyword search AND meaning search (embeddings, app/rag/embeddings.py),
  merged with Reciprocal Rank Fusion. Used when OLLAMA_EMBED_MODEL is set (e.g.
  nomic-embed-text) and Ollama answers; if it doesn't, the assistant falls back to bm25
  and says so in `note`, so a missing Ollama never breaks the assistant.

Meaning search always returns SOMETHING (every note has some cosine to any question), so
in hybrid mode a note found only by meaning must reach MIN_COSINE to count. That keeps
"I couldn't find that" possible for questions your data says nothing about.

GENERATE is still "extractive" (stage 65): the answer IS the retrieved notes, numbered
[1], [2]..., so it can never say anything your data doesn't. Stage 67 replaces `_compose`
with a language model that is given only these same notes.
"""

import os
from dataclasses import dataclass
from typing import Literal

from sqlalchemy.orm import Session

from app.core.exceptions import EmptyQuestionError
from app.db.models import User
from app.rag.bm25 import BM25Index
from app.rag.chunker import Chunk, build_chunks
from app.rag.embeddings import (
    DEFAULT_BASE_URL,
    CachedEmbedder,
    Embedder,
    EmbeddingUnavailableError,
    OllamaEmbedder,
    VectorIndex,
    reciprocal_rank_fusion,
)

TOP_K = 4
# Stemming measured worse on our notes (app/rag/evaluate.py), so it's off.
USE_STEMMING = False
# How many candidates each engine contributes before fusion.
CANDIDATES = 20
# A note found ONLY by meaning must be at least this similar to the question. A first
# guess for nomic-embed-text, to be calibrated with app/rag/evaluate.py on real Ollama.
MIN_COSINE = 0.5
MAX_QUESTION_CHARS = 500
NOT_FOUND = (
    "I couldn't find anything about that in your Career AI data. Try asking about a skill, "
    "a job, your proof, or what to learn next."
)

Mode = Literal["bm25", "vector", "hybrid"]


@dataclass(frozen=True)
class Source:
    number: int  # [1], [2]... as cited in the answer
    chunk: Chunk
    score: float


@dataclass(frozen=True)
class Retrieval:
    hits: list[tuple[int, float]]  # (chunk index, score), best first
    mode: Mode  # what was actually used
    note: str | None = None  # e.g. why meaning search wasn't used


@dataclass(frozen=True)
class AssistantAnswer:
    answer: str
    sources: list[Source]
    searched: int  # how many chunks were searched
    retrieval: Mode
    note: str | None


_embedder: CachedEmbedder | None = None


def configured_embedder() -> Embedder | None:
    """The cached Ollama embedder when OLLAMA_EMBED_MODEL is set, else None (keyword only).

    One instance per process, so its cache survives between questions.
    """
    global _embedder
    model = (os.getenv("OLLAMA_EMBED_MODEL") or "").strip()
    if not model:
        return None
    if _embedder is None or _embedder.name != model:
        base_url = os.getenv("OLLAMA_BASE_URL") or DEFAULT_BASE_URL
        _embedder = CachedEmbedder(OllamaEmbedder(model, base_url=base_url))
    return _embedder


def retrieve(
    chunks: list[Chunk],
    question: str,
    top_k: int = TOP_K,
    embedder: Embedder | None = None,
    mode: Mode | None = None,
) -> Retrieval:
    """Find the best chunks. mode=None picks hybrid when an embedder is given, else bm25."""
    texts = [f"{c.title}. {c.text}" for c in chunks]
    mode = mode or ("hybrid" if embedder is not None else "bm25")
    bm25 = BM25Index(texts, stem=USE_STEMMING).search(question, CANDIDATES)
    if mode == "bm25" or embedder is None:
        return Retrieval([(h.index, round(h.score, 3)) for h in bm25[:top_k]], "bm25")

    try:
        meaning = VectorIndex(texts, embedder).search(question, CANDIDATES)
    except EmbeddingUnavailableError as error:
        note = f"Meaning search is unavailable, so keyword search was used. {error}"
        return Retrieval([(h.index, round(h.score, 3)) for h in bm25[:top_k]], "bm25", note)

    meaning = [(i, score) for i, score in meaning if score >= MIN_COSINE]
    if mode == "vector":
        return Retrieval([(i, round(score, 3)) for i, score in meaning[:top_k]], "vector")
    fused = reciprocal_rank_fusion([[h.index for h in bm25], [i for i, _ in meaning]])
    return Retrieval([(i, round(points, 4)) for i, points in fused[:top_k]], "hybrid")


def _compose(sources: list[Source]) -> str:
    """Extractive answer: the retrieved notes themselves, each tagged with its number."""
    if not sources:
        return NOT_FOUND
    lines = ["Here's what I found in your data:"]
    lines += [f"[{s.number}] {s.chunk.text}" for s in sources]
    return "\n\n".join(lines)


def ask(
    db: Session,
    user: User,
    question: str,
    top_k: int = TOP_K,
    embedder: Embedder | None = None,
) -> AssistantAnswer:
    question = question.strip()
    if not question:
        raise EmptyQuestionError()
    question = question[:MAX_QUESTION_CHARS]

    chunks = build_chunks(db, user)  # 1. CHUNK (fresh from PostgreSQL)
    found = retrieve(chunks, question, top_k, embedder if embedder is not None else configured_embedder())  # 2.
    sources = [Source(n, chunks[i], score) for n, (i, score) in enumerate(found.hits, start=1)]
    return AssistantAnswer(_compose(sources), sources, len(chunks), found.mode, found.note)  # 3. (extractive)
