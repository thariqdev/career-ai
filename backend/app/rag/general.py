"""General-knowledge questions, answered honestly and clearly labelled (stage 92).

"What is Docker?" is about the world, not about the user, and used to get "I couldn't find
anything in your data". A question about the user must still be answered ONLY from their
data. So rules (not the model) decide, in this order:

1. Personal words (I, my, me...) -> about the user: data only.
2. Names one of the user's own things (a project, company, institution, proof, or a job
   title followed by "job"/"role") -> data only. ("What is FundsApp?" is their project.)
3. A general question shape ("What is...", "Explain...", "How does...") -> general.
4. Otherwise -> data; and if search then finds nothing (and 1-2 didn't apply) -> general.

A general answer comes from the local model with a strict prompt: it knows nothing about
the person and must not mention their skills, CV, jobs or proof. Then a check rejects
any answer that talks about "your skills", "you have experience..." and so on, and the
reply falls back to the usual "couldn't find". The chat labels every general answer
"General knowledge, not from your data".
"""

import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Education, Evidence, JobDescription, Project, User, WorkExperience

LABEL = "General knowledge, not from your data. Double-check important details: a small local model can be wrong."
NO_MODEL = (
    "That sounds like a general question. I can answer those when the local AI is switched on; "
    "without it I can only answer from your own Career AI data."
)

_PERSONAL = re.compile(r"\b(?:i|i'm|im|i've|i'd|i'll|me|my|mine|myself)\b", re.IGNORECASE)
_GENERAL = re.compile(
    r"^\s*(?:what\s+(?:is|are|does|do)\b|what's\b|explain\b|define\b|describe\b|"
    r"how\s+(?:does|do|is|are|should|can|would|to)\b|why\s+(?:is|are|do|does|should)\b|"
    r"(?:the\s+)?difference\s+between\b|compare\b|tips\b|best\s+practices\b|when\s+should\b)",
    re.IGNORECASE,
)
_JOB_WORD = r"(?:\s+(?:job|role|position|posting))"

SYSTEM = """You answer general-knowledge questions about technology, careers and job \
interviews, inside a career app. Be accurate, brief and practical: a few sentences or a \
short list.
You know NOTHING about the person asking. Never say what they know, have, have done, \
should claim or are ready for, and never mention their skills, CV, jobs, proof or status.
If the question asks about the person themselves, reply with exactly: NOT_GENERAL"""

_ABOUT_USER = re.compile(
    r"\byour\s+(?:skills?|cv|resume|résumé|proof|evidence|experience|jobs?|gaps?|profile|projects?|applications?)\b"
    r"|\byou(?:'ve|\s+have|\s+are|'re)\b[^.\n]*\b(?:verified|proven|skilled|experienced|qualified|ready)\b"
    r"|\bNOT_GENERAL\b",
    re.IGNORECASE,
)


def own_names(db: Session, user: User) -> list[str]:
    """The user's own things a question might name (lower-cased): never general topics."""
    names: set[str] = set()
    names |= {p.name for p in db.scalars(select(Project).where(Project.user_id == user.id))}
    names |= {e.title for e in db.scalars(select(Evidence).where(Evidence.user_id == user.id))}
    names |= {e.institution for e in db.scalars(select(Education).where(Education.user_id == user.id))}
    names |= {w.company for w in db.scalars(select(WorkExperience).where(WorkExperience.user_id == user.id))}
    for job in db.scalars(select(JobDescription).where(JobDescription.user_id == user.id)):
        if job.company:
            names.add(job.company)
    if user.full_name:
        names.add(user.full_name)
    return sorted(n.strip().lower() for n in names if n and len(n.strip()) >= 3)


def job_titles(db: Session, user: User) -> list[str]:
    jobs = db.scalars(select(JobDescription).where(JobDescription.user_id == user.id))
    return sorted({j.title.strip().lower() for j in jobs if j.title and len(j.title.strip()) >= 3})


def _names_own_thing(question: str, names: list[str], titles: list[str]) -> bool:
    low = question.lower()
    if any(re.search(rf"(?<![\w]){re.escape(n)}(?![\w])", low) for n in names):
        return True
    return any(re.search(rf"(?<![\w]){re.escape(t)}{_JOB_WORD}", low) for t in titles)


def is_about_user(question: str, names: list[str], titles: list[str]) -> bool:
    return bool(_PERSONAL.search(question)) or _names_own_thing(question, names, titles)


def classify(question: str, names: list[str], titles: list[str]) -> str:
    """"general" or "data" (rules 1-3; rule 4's search fallback happens in the assistant)."""
    if is_about_user(question, names, titles):
        return "data"
    return "general" if _GENERAL.search(question) else "data"


def messages_for(question: str) -> list[dict[str, str]]:
    return [{"role": "system", "content": SYSTEM}, {"role": "user", "content": question}]


def acceptable(answer: str) -> bool:
    """A general answer may not talk about the user (or refuse with NOT_GENERAL)."""
    return bool(answer.strip()) and not _ABOUT_USER.search(answer)
