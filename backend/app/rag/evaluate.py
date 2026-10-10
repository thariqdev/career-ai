"""Measure retrieval quality before trying to improve it.

Run from backend/:   .venv/Scripts/python -m app.rag.evaluate

Why: "it feels better" isn't evidence. Real RAG work keeps a small GOLDEN SET (questions
plus the chunks that SHOULD be retrieved) and scores every change against it. Two
standard numbers:

- Recall@k: of the chunks that should be found, the fraction that appear in the top k.
  Asks "did the right notes make it into what the model will read?"
      expected {A, B}, top-4 = [A, X, Y, Z]  ->  recall@4 = 1/2 = 0.5
- MRR (mean reciprocal rank): 1 / (position of the FIRST right chunk), averaged over
  questions (0 if none is in the top k). Asks "how high is the first good answer?"
      first right chunk at #1 -> 1.0,  #2 -> 0.5,  #3 -> 0.33,  not found -> 0

The data here is a FIXED made-up career built in a throwaway in-memory database, so the
scores only change when the retrieval code (or the chunk wording) changes, never because
the user's real data changed. Chunks are named by (kind, title), which stays stable.
"""

import sys
from dataclasses import dataclass
from datetime import date

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.rag.bm25 import BM25Index
from app.rag.chunker import Chunk, build_chunks

K = 4  # the assistant reads the top 4 notes (assistant.TOP_K)

CV = "Python, PostgreSQL, Docker, React and TypeScript. Git daily."

# (question, the chunks that should be retrieved as (kind, title))
GOLDEN: list[tuple[str, set[tuple[str, str]]]] = [
    ("What am I missing for the Backend Engineer job?", {("gap", "Kubernetes gap"), ("gap", "AWS gap"), ("job", "Backend Engineer at Acme")}),
    ("Which skills does the frontend job need?", {("job", "Frontend Developer at Globex")}),
    ("Which skills have no proof yet?", {("overview", "Your overview")}),
    ("What should I learn first?", {("overview", "Your overview")}),
    ("Tell me about Python", {("skill", "Python")}),
    ("Is my Python skill verified?", {("skill", "Python")}),
    ("Which project proves my Python?", {("evidence", "FundsApp repo")}),
    ("Do I know Kubernetes?", {("gap", "Kubernetes gap")}),
    ("What jobs need Docker?", {("skill", "Docker")}),
    ("Tell me about my education", {("education", "Chinmaya College")}),
    ("Where did I work before?", {("work", "Backend Intern at Initech")}),
    ("What is FundsApp?", {("project", "FundsApp"), ("evidence", "FundsApp repo")}),
    ("What gaps do I have in my jobs?", {("job", "Backend Engineer at Acme"), ("job", "Frontend Developer at Globex")}),
    ("Which skills am I learning right now?", {("skill", "React")}),
    ("Which skills are on my CV?", {("overview", "Your overview")}),
]


@dataclass(frozen=True)
class QuestionScore:
    question: str
    recall: float
    reciprocal_rank: float
    retrieved: list[str]


def recall_at_k(retrieved: list[tuple[str, str]], expected: set[tuple[str, str]], k: int = K) -> float:
    return len(expected & set(retrieved[:k])) / len(expected) if expected else 0.0


def reciprocal_rank(retrieved: list[tuple[str, str]], expected: set[tuple[str, str]], k: int = K) -> float:
    for position, key in enumerate(retrieved[:k], start=1):
        if key in expected:
            return 1 / position
    return 0.0


def build_fixture_chunks() -> list[Chunk]:
    """The fixed made-up career, chunked by the real chunker."""
    # Imported here so `import app.rag.evaluate` stays light for the API.
    from app.core.services import cv_adopt_service, user_service
    from app.db.models import Education, Evidence, JobDescription, LearningProgress, Project, UserSkillEvidence, WorkExperience
    from app.db.models.enums import EvidenceType, LearningStatus, VerificationStatus
    from database import Base

    engine = create_engine("sqlite://", poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine, autoflush=False) as db:
        user = user_service.get_or_create_default_user(db)
        cv_adopt_service.add_all_from_cv(db, user, CV)
        claims = {c.skill.name: c for c in user.user_skills}
        project = Project(user=user, name="FundsApp", description="A budgeting API built with Python and PostgreSQL.")
        evidence = Evidence(user=user, evidence_type=EvidenceType.PROJECT, title="FundsApp repo", project=project)
        db.add_all([project, evidence])
        db.flush()
        db.add(UserSkillEvidence(user_skill_id=claims["Python"].id, evidence_id=evidence.id))
        claims["Python"].status = VerificationStatus.VERIFIED
        db.add(LearningProgress(user=user, skill_id=claims["React"].skill_id, status=LearningStatus.STUDYING))
        db.add(WorkExperience(user=user, company="Initech", role="Backend Intern", start_date=date(2023, 1, 1), end_date=date(2023, 6, 1)))
        db.add(Education(user=user, institution="Chinmaya College", degree="BCA", start_date=date(2020, 6, 1), end_date=date(2023, 3, 1)))
        db.add(JobDescription(user=user, title="Backend Engineer", company="Acme", raw_text="Backend role: Python, PostgreSQL, Kubernetes and AWS."))
        db.add(JobDescription(user=user, title="Frontend Developer", company="Globex", raw_text="Frontend role: React, TypeScript and GraphQL."))
        db.flush()
        chunks = build_chunks(db, user)
    engine.dispose()
    return chunks


def evaluate(
    chunks: list[Chunk],
    stem: bool | None = None,
    k: int = K,
    mode: str = "bm25",
    embedder=None,
) -> list[QuestionScore]:
    """Score retrieval on the golden set; by default exactly the assistant's BM25 settings.

    mode "vector" (meaning only) and "hybrid" (BM25 + meaning, fused) need an embedder and
    use the assistant's own `retrieve`, so what's scored is what the assistant does.
    """
    from app.rag.assistant import USE_STEMMING, retrieve

    if stem is None:
        stem = USE_STEMMING
    index = BM25Index([f"{c.title}. {c.text}" for c in chunks], stem=stem)
    keys = [(c.kind, c.title) for c in chunks]
    scores = []
    for question, expected in GOLDEN:
        missing = expected - set(keys)
        if missing:
            raise ValueError(f"Golden set names chunks that don't exist: {missing}")
        if mode == "bm25":
            retrieved = [keys[hit.index] for hit in index.search(question, k)]
        else:
            found = retrieve(chunks, question, k, embedder, mode)  # type: ignore[arg-type]
            if found.mode != mode:
                raise RuntimeError(found.note or f"{mode} retrieval wasn't available")
            retrieved = [keys[i] for i, _ in found.hits]
        scores.append(
            QuestionScore(
                question,
                recall_at_k(retrieved, expected, k),
                reciprocal_rank(retrieved, expected, k),
                [f"{kind}:{title}" for kind, title in retrieved],
            )
        )
    return scores


def summary(scores: list[QuestionScore]) -> tuple[float, float]:
    """(mean recall@k, MRR)."""
    n = len(scores)
    return sum(s.recall for s in scores) / n, sum(s.reciprocal_rank for s in scores) / n


def _ollama_embedder():
    """The real embedder if Ollama answers, else (None, reason)."""
    import os

    from app.rag.embeddings import DEFAULT_MODEL, CachedEmbedder, EmbeddingUnavailableError, OllamaEmbedder

    model = (os.getenv("OLLAMA_EMBED_MODEL") or DEFAULT_MODEL).strip()
    embedder = CachedEmbedder(OllamaEmbedder(model, base_url=os.getenv("OLLAMA_BASE_URL") or "http://127.0.0.1:11434"))
    try:
        embedder.embed(["probe"])
    except EmbeddingUnavailableError as error:
        return None, str(error)
    return embedder, model


def main() -> int:
    chunks = build_fixture_chunks()
    results = {"BM25, no stemming": evaluate(chunks, stem=False), "BM25 + stemming": evaluate(chunks, stem=True)}
    embedder, info = _ollama_embedder()
    if embedder is not None:
        results[f"meaning ({info})"] = evaluate(chunks, mode="vector", embedder=embedder)
        results["hybrid (BM25+meaning)"] = evaluate(chunks, mode="hybrid", embedder=embedder)
    else:
        print(f"Meaning search not scored: {info}\n")
    print(f"{len(GOLDEN)} golden questions over {len(chunks)} notes, top {K}\n")
    print(f"{'question':<52}" + "".join(f"{name:>22}" for name in results))
    for i, (question, _) in enumerate(GOLDEN):
        row = "".join(f"{'R=%.2f MRR=%.2f' % (r[i].recall, r[i].reciprocal_rank):>22}" for r in results.values())
        print(f"{question[:51]:<52}{row}")
    print()
    for name, scores in results.items():
        recall, mrr = summary(scores)
        print(f"{name:<34} recall@{K} = {recall:.3f}   MRR = {mrr:.3f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
