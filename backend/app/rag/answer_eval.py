"""Measure answer quality: does the written answer say what it should, every time?

Run from backend/:   .venv/Scripts/python -m app.rag.answer_eval

ANSWERS was written and committed BEFORE any stage-74 change, over the fixed made-up
career in app/rag/evaluate.py (Python verified by the FundsApp repo; Docker, Git,
PostgreSQL, React, TypeScript on the CV without proof; React being studied; jobs
"Backend Engineer at Acme" missing Kubernetes and AWS, "Frontend Developer at Globex"
missing GraphQL; Backend Intern at Initech; BCA at Chinmaya College; no name saved).

Each case lists facts the answer MUST mention (a tuple = any one of these wordings
counts) and, where it's safe to check, words it must NOT contain.
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class AnswerCase:
    question: str
    must: tuple[tuple[str, ...], ...]  # each fact: any of these wordings (case-insensitive)
    must_not: tuple[str, ...] = field(default=())


def _c(question: str, must: list, must_not: tuple[str, ...] = ()) -> AnswerCase:
    return AnswerCase(question, tuple(m if isinstance(m, tuple) else (m,) for m in must), must_not)


NOT_PROVEN = ("not verified", "isn't verified", "not proven", "no proof", "not yet proven", "provisional", "unproven")

ANSWERS: list[AnswerCase] = [
    # --- exact-list questions (answered by a tool) -----------------------------------------
    _c("Which skills have no proof yet?", ["Docker", "Git", "PostgreSQL", "React", "TypeScript"]),
    _c("Which skills are verified?", ["Python", "FundsApp"]),
    _c("Which skills are on my CV?", ["Docker", "Git", "PostgreSQL", "Python", "React", "TypeScript"]),
    _c("What am I missing for the Acme job?", ["Kubernetes", "AWS"], must_not=("GraphQL",)),
    _c("What am I missing for my jobs?", ["Kubernetes", "AWS", "GraphQL"]),
    _c("What should I learn first?", ["AWS", "GraphQL", "Kubernetes"]),
    # --- search questions ------------------------------------------------------------------
    _c("Is my Python skill verified?", [("verified", "proven"), "FundsApp"]),
    _c("Is Docker verified?", ["Docker", NOT_PROVEN]),
    _c("What is FundsApp?", ["budget", "Python", "PostgreSQL"]),
    _c("Where did I work before?", ["Initech", "Backend Intern"]),
    _c("Tell me about my education", ["BCA", "Chinmaya"]),
    _c("What am I studying right now?", ["React"]),
    _c("Which job needs GraphQL?", [("Frontend Developer", "Globex")]),
    _c("What is my name?", [("not saved", "isn't saved", "not been saved", "couldn't find", "don't have", "no name")]),
    _c("Which skills for the Globex job do I already have?", ["React", "TypeScript"]),
]


# --- the measurement (written after ANSWERS was committed) --------------------------------

RUNS = 3


def facts_found(answer: str, case: AnswerCase) -> tuple[frozenset[int], list[str]]:
    """(indexes of the MUST facts the answer mentions, MUST_NOT words it contains)"""
    low = answer.lower()
    found = frozenset(i for i, options in enumerate(case.must) if any(o.lower() in low for o in options))
    return found, [w for w in case.must_not if w.lower() in low]


def main() -> int:
    import os
    import sys
    import time

    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from sqlalchemy.pool import StaticPool

    from app.rag.assistant import answer_events, prepare
    from app.rag.evaluate import _ollama_embedder, fill_fixture
    from app.rag.generate import DEFAULT_CHAT_MODEL, OllamaChat
    from database import Base

    model = os.getenv("OLLAMA_CHAT_MODEL") or DEFAULT_CHAT_MODEL
    embedder, _ = _ollama_embedder()
    engine = create_engine("sqlite://", poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine, autoflush=False) as db:
        user = fill_fixture(db)
        prepared = [prepare(db, user, c.question, embedder=embedder, rewriter=None) for c in ANSWERS]
    engine.dispose()

    candidates = {
        "A  today (temperature 0.2)": (0.2, False),
        "B  temperature 0": (0.0, False),
        "C  exact lists by code (0.2)": (0.2, True),
        "B+C  both": (0.0, True),
    }
    for name, (temperature, exact) in candidates.items():
        chat = OllamaChat(model, temperature=temperature)
        complete = total = steady = forbidden = ai_kept = 0
        start = time.time()
        weak: list[str] = []
        for case, ready in zip(ANSWERS, prepared):
            runs = []
            for _ in range(RUNS):
                text, written_by = "", "notes"
                for e in answer_events(ready, [], chat, exact_lists=exact):
                    if e["type"] == "delta":
                        text += e["text"]
                    elif e["type"] == "replace":
                        text = e["text"]
                    elif e["type"] == "done":
                        written_by = e["written_by"]
                found, bad = facts_found(text, case)
                runs.append(found)
                complete += len(found)
                total += len(case.must)
                forbidden += len(bad)
                ai_kept += written_by == "ai"
            steady += len(set(runs)) == 1
            if min(len(r) for r in runs) < len(case.must):
                weak.append(f"    {case.question!r}: facts found per run {[len(r) for r in runs]} of {len(case.must)}")
        seconds = (time.time() - start) / (len(ANSWERS) * RUNS)
        print(
            f"{name:<30} completeness {complete / total:.3f}   same facts every run {steady}/{len(ANSWERS)}   "
            f"forbidden words {forbidden}   AI-written kept {ai_kept}/{len(ANSWERS) * RUNS}   {seconds:.1f}s/answer"
        )
        for line in weak:
            print(line)
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
