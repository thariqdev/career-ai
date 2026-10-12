"""TOOLS (RAG stage 69): exact answers from the database for "list" and "count" questions.

Search hands the model the 4 notes that LOOK most like the question. That suits "Tell me
about Python", but not "Which skills have no proof yet?": the answer needs every skill
checked, and the closest-looking notes may not hold it. A tool is a plain function
that computes the exact answer from PostgreSQL. Its result becomes a note like any
other ("[1] (tool) Skills with no proof yet: ..."), so the model only puts it into
words, and the citation and faithfulness checks still apply.

Every tool here is READ-ONLY: the assistant can look things up, never change them.
Which tool (if any) a question needs is decided by app/rag/router.py.
"""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.services import match_service
from app.db.models import CVSkillPresence, JobDescription, Skill, User, UserSkill
from app.db.models.enums import VerificationStatus
from app.rag.chunker import Chunk, job_label, known_skill_names
from app.rag.sanitize import describe, split_known


@dataclass(frozen=True)
class ToolCall:
    name: str
    job: str | None = None  # job_gaps only: words naming one job ("Acme"); None = all jobs


# name -> what it answers. Also shown to the model when it picks tools (router.py).
TOOLS: dict[str, str] = {
    "skills_without_proof": "List the user's skills (claimed or on their CV) that are not verified, with no proof yet.",
    "verified_skills": "List the user's verified (proven) skills and their proof.",
    "skills_on_cv": "List the skills on the user's CV.",
    "job_gaps": "List the skills the user is missing for their jobs, for one named job or for all jobs.",
    "learn_first": "Rank the missing skills to learn first, by how many of the user's jobs need them.",
}


def _note(name: str, title: str, lines: tuple[str, ...], link: str) -> Chunk:
    """A tool's result as a note: the lines joined for the model, and kept for display."""
    return Chunk(f"tool:{name}", "tool", title, " ".join(lines), link, lines)


def _join(names: list[str]) -> str:
    return ", ".join(names) if names else "none"


def _jobs(db: Session, user: User) -> list[JobDescription]:
    return list(db.scalars(select(JobDescription).where(JobDescription.user_id == user.id).order_by(JobDescription.id)))


def matches_job(label: str, words: str) -> bool:
    """Does a job label contain every word (3+ letters) of `words`? ("acme" -> "Backend Engineer at Acme")"""
    wanted = [w for w in words.lower().replace(",", " ").split() if len(w) >= 3 and w not in {"job", "the", "role", "for"}]
    return bool(wanted) and all(w in label.lower() for w in wanted)


def find_jobs(jobs: list[JobDescription], words: str) -> list[JobDescription]:
    return [job for job in jobs if matches_job(job_label(job), words)]


def _skills_without_proof(db: Session, user: User) -> Chunk:
    claims = {c.skill_id: c for c in db.scalars(select(UserSkill).where(UserSkill.user_id == user.id))}
    on_cv = set(
        db.scalars(
            select(CVSkillPresence.skill_id).where(CVSkillPresence.user_id == user.id, CVSkillPresence.present.is_(True))
        )
    )
    claimed, cv_only = [], []
    for skill in db.scalars(select(Skill).order_by(Skill.name)):
        claim = claims.get(skill.id)
        if claim is not None and claim.status != VerificationStatus.VERIFIED and not claim.evidence_links:
            claimed.append(skill.name)
        elif claim is None and skill.id in on_cv:
            cv_only.append(skill.name)
    lines = (
        f"Skills with no proof yet: {len(claimed) + len(cv_only)}.",
        f"Claimed but no proof linked: {_join(claimed)}.",
        f"On your CV but not claimed or proven: {_join(cv_only)}.",
    )
    return _note("skills_without_proof", "Skills with no proof yet", lines, "/skills")


def _verified_skills(db: Session, user: User) -> Chunk:
    claims = db.scalars(
        select(UserSkill).where(UserSkill.user_id == user.id, UserSkill.status == VerificationStatus.VERIFIED)
    )
    parts = sorted(
        f"{c.skill.name} (proof: {_join(sorted(link.evidence.title for link in c.evidence_links))})" for c in claims
    )
    lines = (f"Verified (proven) skills: {len(parts)}.", f"{_join(parts)}.")
    return _note("verified_skills", "Your verified skills", lines, "/skills")


def _skills_on_cv(db: Session, user: User) -> Chunk:
    names = list(
        db.scalars(
            select(Skill.name)
            .join(CVSkillPresence, CVSkillPresence.skill_id == Skill.id)
            .where(CVSkillPresence.user_id == user.id, CVSkillPresence.present.is_(True))
            .order_by(Skill.name)
        )
    )
    lines = (f"Skills on your CV: {len(names)}.", f"{_join(names)}.")
    return _note("skills_on_cv", "Skills on your CV", lines, "/cv")


def _job_gaps(db: Session, user: User, job: str | None) -> Chunk:
    jobs = _jobs(db, user)
    chosen = find_jobs(jobs, job) if job else jobs
    if job and not chosen:
        lines = (f"No job matches \"{job}\". Your jobs: {_join([job_label(j) for j in jobs])}.",)
        return _note("job_gaps", "Missing skills per job", lines, "/job-descriptions")
    known = known_skill_names(db)
    lines = tuple(
        f"Missing for {job_label(j)}: {describe([item.name for item in match_service.job_match(db, user, j).missing], known)}."
        for j in chosen
    ) or ("No job descriptions pasted yet.",)
    link = f"/job-descriptions/{chosen[0].id}" if len(chosen) == 1 else "/job-descriptions"
    title = f"Missing skills for {job_label(chosen[0])}" if len(chosen) == 1 else "Missing skills per job"
    return _note("job_gaps", title, lines, link)


def _learn_first(db: Session, user: User) -> Chunk:
    needed: dict[str, list[str]] = {}
    known = known_skill_names(db)
    for j in _jobs(db, user):
        for name in split_known([item.name for item in match_service.job_match(db, user, j).missing], known)[0]:
            needed.setdefault(name, []).append(job_label(j))
    ranked = sorted(needed, key=lambda name: (-len(needed[name]), name.lower()))[:10]
    parts = [f"{i}. {name} (needed by {len(needed[name])} job{'s' if len(needed[name]) != 1 else ''})"
             for i, name in enumerate(ranked, start=1)]
    lines = ("Missing skills to learn first, most needed first:", *parts) if parts else ("No missing skills to learn.",)
    return _note("learn_first", "What to learn first", lines, "/")


def run(db: Session, user: User, call: ToolCall) -> Chunk:
    """Run one tool and return its result as a note."""
    if call.name == "skills_without_proof":
        return _skills_without_proof(db, user)
    if call.name == "verified_skills":
        return _verified_skills(db, user)
    if call.name == "skills_on_cv":
        return _skills_on_cv(db, user)
    if call.name == "job_gaps":
        return _job_gaps(db, user, call.job)
    if call.name == "learn_first":
        return _learn_first(db, user)
    raise ValueError(f"Unknown tool: {call.name}")
