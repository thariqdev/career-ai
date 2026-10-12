"""The assistant: question -> retrieve the best chunks -> answer with numbered sources.

The full RAG loop is CHUNK -> RETRIEVE -> GENERATE, split into two phases:

prepare()        all database work: build chunks from PostgreSQL and RETRIEVE the best
                 ones. Done once, before any answer is streamed.
answer_events()  GENERATE, with no database access: either a local language model
                 writes the answer from the retrieved notes (stage 67, app/rag/generate.py),
                 or the answer IS the notes ("extractive", stage 65).

RETRIEVE has two engines (stages 65-66):
- "bm25": keyword search (app/rag/bm25.py). Always available.
- "hybrid": keyword AND meaning search (embeddings), merged with Reciprocal Rank Fusion.
  Used when OLLAMA_EMBED_MODEL is set and Ollama answers; otherwise bm25, with a note.
Meaning search always returns SOMETHING, so a note found only by meaning must reach
MIN_COSINE; that keeps "I couldn't find that" possible.

GENERATE uses the model named by OLLAMA_CHAT_MODEL (e.g. llama3.2) when set. The answer
streams as events (see app/api/assistant.py): meta (sources first), deltas (text), an
optional `replace` (the final text, when the checks changed it), then done (who wrote it).
Checks: invalid citations are removed; an answer citing nothing falls back to the notes;
an unavailable model falls back to the notes with a note. A question with no matching
notes never reaches the model. Stage 68 adds faithfulness rules (app/rag/faithfulness.py):
an answer naming a skill its notes don't, or calling something verified that isn't, also
falls back to the notes, with the reason.
"""

import os
import re
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import EmptyQuestionError
from app.db.models import Skill, User
from app.rag import note_cache, tools
from app.rag.actions import Action, detect_action, reply_for
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
from app.rag.faithfulness import check as check_faithfulness
from app.rag.faithfulness import vocabulary
from app.rag.generate import (
    ChatModel,
    GenerationUnavailableError,
    Note,
    OllamaChat,
    Turn,
    build_messages,
    cited_numbers,
    clean_citations,
    fit_notes,
)
from app.rag.rewrite import standalone_question
from app.rag.router import guarded_keyword_route

TOP_K = 4
# Stemming measured worse on our notes (app/rag/evaluate.py), so it's off.
USE_STEMMING = False
# How many candidates each engine contributes before fusion.
CANDIDATES = 20
# A note found ONLY by meaning must be at least this similar to the question. Calibrated
# for nomic-embed-text (2026-10-11): off-topic questions ("weather in Paris?") scored up to
# 0.535, right notes 0.52-0.76 (median 0.73). 0.50 let 4 of 6 off-topic questions through;
# 0.60 lets none through and gave the best hybrid MRR (0.933; recall@4 1.000).
MIN_COSINE = 0.6
MAX_QUESTION_CHARS = 500
NOT_FOUND = (
    "I couldn't find anything about that in your Career AI data. Try asking about a skill, "
    "a job, your proof, or what to learn next."
)
UNCITED_NOTE = "The AI's answer didn't cite your notes, so here are the notes themselves."
# Stage 74: for an exact-list question (a tool answered), code writes the list itself and
# the model writes only a one-sentence introduction. Measured (app/rag/answer_eval.py):
# completeness 1.000 vs 0.982, same facts every run 15/15 vs 13/15; on real data the AI
# alone mentioned 4, 25 and 24 of 28 missing skills in three runs, code-written all 28.
EXACT_LISTS = True
REWRITE_SEED = 42  # stage 76: makes the follow-up rewrite repeatable
# Stage 76: OFF. On a fresh set, seeded and reloaded 5 times (identical every run), the
# rewrite found notes worse than gluing on the previous question (recall@4 0.933 vs 0.967,
# MRR 0.644 vs 0.700), though it routed 2 more exact lists. app/rag/rewrite_eval.py --fresh
REWRITE_FOLLOW_UPS = False
DEFAULT_INTRO = "Here's the exact answer from your data:"
MAX_INTRO_CHARS = 200
INTRO_SYSTEM = (
    "Write one short, friendly sentence that introduces a list answering the person's "
    "question. Do not name or list any items, and add no numbers or citations. Reply with "
    "the sentence only."
)

Mode = Literal["bm25", "vector", "hybrid"]
WrittenBy = Literal["ai", "notes"]


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
class Prepared:
    question: str
    sources: list[Source]
    searched: int
    retrieval: Mode
    note: str | None
    known_names: tuple[str, ...] = ()  # this user's skill and gap names, for the faithfulness rules
    action: Action | None = None  # stage 78: a change the message asks for, to be confirmed


@dataclass(frozen=True)
class AssistantAnswer:
    answer: str
    sources: list[Source]
    searched: int  # how many chunks were searched
    retrieval: Mode
    note: str | None
    written_by: WrittenBy
    action: Action | None = None


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


def configured_chat() -> ChatModel | None:
    """The local Ollama chat model when OLLAMA_CHAT_MODEL is set, else None (notes only)."""
    model = (os.getenv("OLLAMA_CHAT_MODEL") or "").strip()
    if not model:
        return None
    return OllamaChat(model, base_url=os.getenv("OLLAMA_BASE_URL") or DEFAULT_BASE_URL)


def configured_rewriter() -> ChatModel | None:
    """The same local model, at temperature 0, for rewriting follow-ups (stage 73)."""
    model = (os.getenv("OLLAMA_CHAT_MODEL") or "").strip()
    if not model:
        return None
    return OllamaChat(
        model, base_url=os.getenv("OLLAMA_BASE_URL") or DEFAULT_BASE_URL, temperature=0.0, seed=REWRITE_SEED
    )


def _saved_skills(db: Session) -> dict[int, tuple[str, list[str]]]:
    """{skill_id: (name, [name, *aliases])} for the action detector."""
    return {s.id: (s.name, [s.name, *(a.alias for a in s.aliases)]) for s in db.scalars(select(Skill))}


def note_texts(chunks: list[Chunk]) -> list[str]:
    """The text each note is searched by (and embedded as). One place, so the startup
    warm-up fills the embedding cache with exactly what search will ask for."""
    return [f"{c.title}. {c.text}" for c in chunks]


def index_notes(db: Session, user: User) -> int:
    """Embed all of the user's notes now (into the cached embedder), so the first question
    doesn't wait for it. Returns how many notes; 0 when meaning search is off."""
    embedder = configured_embedder()
    if embedder is None:
        return 0
    chunks = note_cache.notes(db, user)
    VectorIndex(note_texts(chunks), embedder)
    return len(chunks)


def retrieve(
    chunks: list[Chunk],
    question: str,
    top_k: int = TOP_K,
    embedder: Embedder | None = None,
    mode: Mode | None = None,
) -> Retrieval:
    """Find the best chunks. mode=None picks hybrid when an embedder is given, else bm25."""
    texts = note_texts(chunks)
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


def stream_pieces(answer: str) -> Iterator[str]:
    """Split an answer into small pieces (a word plus its following spaces) for streaming.

    Joining the pieces gives back exactly `answer`.
    """
    yield from re.findall(r"\S+\s*|\s+", answer)


def prepare(
    db: Session,
    user: User,
    question: str,
    top_k: int = TOP_K,
    embedder: Embedder | None = None,
    history: list[Turn] | None = None,
    rewriter: ChatModel | None = None,
) -> Prepared:
    """All database work: CHUNK (fresh from PostgreSQL) and RETRIEVE.

    For a follow-up ("And for Globex?"), the previous question is glued on for SEARCH, so
    the topic can be found. Stage 73 tried having the model rewrite follow-ups into
    standalone questions (app/rag/rewrite.py); stage 76 measured it worse, so it's off
    (REWRITE_FOLLOW_UPS) unless a `rewriter` is passed in. The model that writes the
    answer always sees the real question.

    Stage 69: a "list" question ("Which skills have no proof yet?") is routed to a TOOL
    (app/rag/tools.py) that computes the exact answer; its result becomes note [1], and
    search fills the rest. The keyword rules (behind the stage-70 guards) are used because
    they picked the fewest wrong tools when measured (app/rag/router_eval.py); a question
    they don't recognise simply gets search, as before.
    """
    question = question.strip()
    if not question:
        raise EmptyQuestionError()
    question = question[:MAX_QUESTION_CHARS]
    previous = next((t.text for t in reversed(history or []) if t.role == "user"), "")
    if rewriter is None and REWRITE_FOLLOW_UPS:
        rewriter = configured_rewriter()
    rewritten = standalone_question(question, history or [], rewriter) if rewriter is not None else None
    search_text = rewritten or f"{question} {previous[:MAX_QUESTION_CHARS]}".strip()

    # Stage 78: a request to change something ("Mark React as studying") is answered with
    # a proposal to confirm, not a search. Rules decide (app/rag/actions.py), never the model.
    action = detect_action(question, _saved_skills(db))
    if action is not None:
        return Prepared(question, [], 0, "bm25", None, (), action)

    chunks = note_cache.notes(db, user)  # cached until any data changes (stage 82)
    known_names = vocabulary(chunks)
    call = guarded_keyword_route(rewritten or question, [c.title for c in chunks if c.kind == "job"], known_names)
    tool_chunk = tools.run(db, user, call) if call is not None else None
    found = retrieve(
        chunks, search_text, top_k - 1 if tool_chunk else top_k, embedder if embedder is not None else configured_embedder()
    )
    picked = ([(tool_chunk, 1.0)] if tool_chunk else []) + [(chunks[i], score) for i, score in found.hits]
    sources = [Source(n, chunk, score) for n, (chunk, score) in enumerate(picked, start=1)]
    return Prepared(question, sources, len(chunks), found.mode, found.note, known_names)


def _join_notes(*notes: str | None) -> str | None:
    kept = [n for n in notes if n]
    return " ".join(kept) if kept else None


def _intro(question: str, tool: Chunk, chat: ChatModel) -> str:
    """The model's one-sentence introduction to an exact list, or DEFAULT_INTRO if it fails
    or misbehaves (several lines, too long, or names a skill the list doesn't)."""
    messages = [
        {"role": "system", "content": INTRO_SYSTEM},
        {"role": "user", "content": f"Question: {question}\nThe list is titled: {tool.title}"},
    ]
    try:
        intro = "".join(chat.stream(messages)).strip().strip('"')
    except GenerationUnavailableError:
        return DEFAULT_INTRO
    if not intro or "\n" in intro or len(intro) > MAX_INTRO_CHARS or "[" in intro:
        return DEFAULT_INTRO
    if not check_faithfulness(intro, [Note(1, tool.kind, tool.title, tool.text)]).ok:
        return DEFAULT_INTRO
    return intro


def answer_events(
    prepared: Prepared,
    history: list[Turn] | None = None,
    chat: ChatModel | None = None,
    exact_lists: bool | None = None,
) -> Iterator[dict]:
    """GENERATE, as events. No database access here, so it's safe to stream.

    meta -> delta... -> (replace) -> done. `replace` carries the final text whenever the
    checks changed what was streamed; `done` says who wrote the answer.
    """
    exact_lists = EXACT_LISTS if exact_lists is None else exact_lists
    sources = prepared.sources
    yield {
        "type": "meta",
        "sources": sources,
        "retrieval": prepared.retrieval,
        "note": prepared.note,
        "searched": prepared.searched,
        "action": prepared.action.to_dict() if prepared.action else None,
    }
    if prepared.action is not None:  # a proposal (or a refusal): no notes, no model
        for piece in stream_pieces(reply_for(prepared.action)):
            yield {"type": "delta", "text": piece}
        yield {"type": "done", "written_by": "notes", "note": None}
        return
    extractive = _compose(sources)

    if not sources or chat is None:  # nothing to ground an answer on, or no model: the notes
        for piece in stream_pieces(extractive):
            yield {"type": "delta", "text": piece}
        yield {"type": "done", "written_by": "notes", "note": prepared.note}
        return

    tool = sources[0].chunk if sources[0].chunk.kind == "tool" and sources[0].chunk.lines else None
    if exact_lists and tool is not None:  # the list from the data, word for word
        lines = list(tool.lines)
        lines[0] = f"{lines[0]} [1]"
        text = _intro(prepared.question, tool, chat) + "\n\n" + "\n".join(lines)
        for piece in stream_pieces(text):
            yield {"type": "delta", "text": piece}
        yield {"type": "done", "written_by": "notes", "note": prepared.note}
        return

    notes = fit_notes([Note(s.number, s.chunk.kind, s.chunk.title, s.chunk.text) for s in sources])
    messages = build_messages(prepared.question, notes, history or [])
    written: list[str] = []
    try:
        for token in chat.stream(messages):
            written.append(token)
            yield {"type": "delta", "text": token}
    except GenerationUnavailableError as error:
        note = f"The AI writer is unavailable, so here are the notes themselves. {error}"
        yield {"type": "replace", "text": extractive}
        yield {"type": "done", "written_by": "notes", "note": _join_notes(prepared.note, note)}
        return

    text = "".join(written)
    cleaned = clean_citations(text, len(notes)).strip()
    if not cited_numbers(cleaned, len(notes)):
        yield {"type": "replace", "text": extractive}
        yield {"type": "done", "written_by": "notes", "note": _join_notes(prepared.note, UNCITED_NOTE)}
        return
    verdict = check_faithfulness(cleaned, notes, prepared.known_names)
    if not verdict.ok:
        note = f"The AI's answer didn't match your notes ({'; '.join(verdict.problems)}), so here are the notes themselves."
        yield {"type": "replace", "text": extractive}
        yield {"type": "done", "written_by": "notes", "note": _join_notes(prepared.note, note)}
        return
    if cleaned != text:
        yield {"type": "replace", "text": cleaned}
    yield {"type": "done", "written_by": "ai", "note": prepared.note}


def ask(
    db: Session,
    user: User,
    question: str,
    top_k: int = TOP_K,
    embedder: Embedder | None = None,
    history: list[Turn] | None = None,
    chat: ChatModel | None = None,
) -> AssistantAnswer:
    """The whole answer at once (the events, collected)."""
    prepared = prepare(db, user, question, top_k, embedder, history)
    text, written_by, note = "", "notes", prepared.note
    for event in answer_events(prepared, history, chat if chat is not None else configured_chat()):
        if event["type"] == "delta":
            text += event["text"]
        elif event["type"] == "replace":
            text = event["text"]
        elif event["type"] == "done":
            written_by, note = event["written_by"], event["note"]
    return AssistantAnswer(
        text, prepared.sources, prepared.searched, prepared.retrieval, note, written_by, prepared.action
    )
