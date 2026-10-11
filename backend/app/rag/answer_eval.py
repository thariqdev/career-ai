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
