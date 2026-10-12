"""Which questions are general knowledge, and which are about the user? (stage 92)

Run from backend/:   .venv/Scripts/python -m app.rag.general_eval

QUESTIONS was written and committed BEFORE the classifier, over the fixed made-up career in
app/rag/evaluate.py (project FundsApp, evidence "FundsApp repo", jobs "Backend Engineer at
Acme" and "Frontend Developer at Globex", work at Initech, Chinmaya College).

- "general": about the world ("What is Docker?"): may be answered from general knowledge,
  clearly labelled, never saying anything about the user.
- "data": about the user or their records: answered ONLY from their data, as before.

The hard requirement: no "data" question may ever take the general path (that would
answer a question about the user from the model's imagination). A "general" question
taking the data path is only a missed chance (the old "couldn't find" reply).
"""

QUESTIONS: list[tuple[str, str]] = [
    # --- general knowledge -----------------------------------------------------------------
    ("What is Docker?", "general"),
    ("What is Kubernetes used for?", "general"),
    ("Explain REST vs GraphQL", "general"),
    ("How does a load balancer work?", "general"),
    ("What's the difference between SQL and NoSQL?", "general"),
    ("How should someone prepare for a system design interview?", "general"),
    ("What are microservices?", "general"),
    ("Define CI/CD", "general"),
    ("Why is unit testing important?", "general"),
    ("What does a backend engineer do?", "general"),
    ("Tips for a technical interview", "general"),
    ("How do neural networks learn?", "general"),
    # --- about the user or their records ---------------------------------------------------
    ("What am I missing for my jobs?", "data"),
    ("Is my Python skill verified?", "data"),
    ("Do I know Docker?", "data"),
    ("Should I learn Kubernetes?", "data"),
    ("What should I learn first?", "data"),
    ("Tell me about Python", "data"),
    ("What is FundsApp?", "data"),  # the user's own project
    ("Where did I work before?", "data"),
    ("Which skills have no proof yet?", "data"),
    ("How do I prove Docker?", "data"),
    ("What is my name?", "data"),
    ("Am I ready for the Acme job?", "data"),
    ("What does the Backend Engineer job need?", "data"),  # the user's own job
    ("Explain my gaps for Globex", "data"),
    ("Which jobs need GraphQL?", "data"),
    ("Tell me about the Acme job", "data"),
    ("How can I learn React?", "data"),
    ("What is Chinmaya College?", "data"),  # the user's own education
]


# --- the measurement (written after QUESTIONS was committed) --------------------------------


def score() -> tuple[int, int, int, list[str]]:
    """(right, data questions sent to the general path (must be 0), general ones missed, mistakes)."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from sqlalchemy.pool import StaticPool

    from app.rag.evaluate import fill_fixture
    from app.rag.general import classify, job_titles, own_names
    from database import Base

    engine = create_engine("sqlite://", poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine, autoflush=False) as db:
        user = fill_fixture(db)
        names, titles = own_names(db, user), job_titles(db, user)
    engine.dispose()
    right = leaked = missed = 0
    mistakes = []
    for question, want in QUESTIONS:
        got = classify(question, names, titles)
        if got == want:
            right += 1
            continue
        if want == "data":
            leaked += 1
        else:
            missed += 1
        mistakes.append(f"    {question!r}: got {got}, want {want}")
    return right, leaked, missed, mistakes


def main() -> int:
    right, leaked, missed, mistakes = score()
    print(f"right {right}/{len(QUESTIONS)}   personal questions sent to general (must be 0): {leaked}   general missed: {missed}")
    for line in mistakes:
        print(line)
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
