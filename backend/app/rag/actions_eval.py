"""The action detector's test set (RAG stage 78), written BEFORE the detector existed.

Over the fixed made-up career in app/rag/evaluate.py (saved skills: Docker, Git,
PostgreSQL, Python, React, TypeScript; Kubernetes is only a job's gap, not a skill).

Each case: a chat message and what the detector must return:
- ("progress", skill, status)   propose setting learning progress
- ("link", skill, mode)         propose saving a learning link
- ("refused", skill)            explain this isn't done through the chat (verify, evidence, delete)
- None                          no action: it's a question (search answers it), or unclear

A WRONG action (proposing something not asked for) is the worst outcome, so the bar is
zero; a missed action is only an inconvenience (the chat answers normally).
"""

ActionExpectation = tuple | None

ACTION_CASES: list[tuple[str, ActionExpectation]] = [
    # --- should propose an action -----------------------------------------------------------
    ("Mark React as studying", ("progress", "React", "studying")),
    ("I'm learning Docker now", ("progress", "Docker", "studying")),
    ("I started studying TypeScript", ("progress", "TypeScript", "studying")),
    ("I finished learning Docker", ("progress", "Docker", "finished")),
    ("Mark Git as finished", ("progress", "Git", "finished")),
    ("Set PostgreSQL to not started", ("progress", "PostgreSQL", "not_started")),
    ("Can you mark Python as done?", ("progress", "Python", "finished")),
    ("Please mark TypeScript as in progress", ("progress", "TypeScript", "studying")),
    ("Save https://youtu.be/abc123 as a Docker tutorial", ("link", "Docker", "technical_practical")),
    ("Add this React interview video: https://www.youtube.com/watch?v=xyz", ("link", "React", "theory_interview")),
    # --- must be refused (not done through the chat) ----------------------------------------
    ("Verify my Python skill", ("refused", "Python")),
    ("Mark React as verified", ("refused", "React")),
    ("Delete Docker", ("refused", "Docker")),
    ("Can you add evidence for Git?", ("refused", "Git")),
    # --- must do nothing ----------------------------------------------------------------------
    ("Is React studied?", None),
    ("Am I learning React?", None),
    ("Which skills am I studying?", None),
    ("Mark Kubernetes as studying", None),  # not one of the saved skills
    ("Mark React and Docker as studying", None),  # two skills: unclear which
    ("What should I learn first?", None),
    ("Save this link for later", None),  # no skill, no link
    ("How do I verify Docker?", None),  # a question about how, not a request
]


# --- the measurement (written after ACTION_CASES was committed) ---------------------------


def fixture_skills() -> dict[int, tuple[str, list[str]]]:
    """{skill_id: (name, terms)} of the made-up career's saved skills."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from sqlalchemy.pool import StaticPool

    from app.db.models import Skill
    from app.rag.evaluate import fill_fixture
    from database import Base

    engine = create_engine("sqlite://", poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine, autoflush=False) as db:
        fill_fixture(db)
        skills = {s.id: (s.name, [s.name, *(a.alias for a in s.aliases)]) for s in db.query(Skill)}
    engine.dispose()
    return skills


def outcome(action) -> tuple | None:
    if action is None:
        return None
    if action.kind == "progress":
        return ("progress", action.skill_name, action.body["status"])
    if action.kind == "link":
        return ("link", action.skill_name, action.body["mode"])
    return ("refused", action.skill_name)


def score(cases=ACTION_CASES) -> tuple[int, int, int, list[str]]:
    """(right, wrong action, missed action, mistakes). Wrong = proposed something not asked."""
    from app.rag.actions import detect_action

    skills = fixture_skills()
    right = wrong = missed = 0
    mistakes = []
    for message, want in cases:
        got = outcome(detect_action(message, skills))
        if got == want:
            right += 1
            continue
        if got is None:
            missed += 1
        else:
            wrong += 1
        mistakes.append(f"    {message!r}: got {got}, want {want}")
    return right, wrong, missed, mistakes


def main() -> int:
    right, wrong, missed, mistakes = score()
    print(f"actions: right {right}/{len(ACTION_CASES)}   wrong action {wrong}   missed {missed}")
    for line in mistakes:
        print(line)
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
