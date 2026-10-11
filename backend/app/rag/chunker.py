"""Chunking: turn the user's Career AI data into small, self-contained notes ("chunks").

RAG step 1. A retriever can only return what it was given, so how the data is cut up
decides what questions can be answered. Rules used here (the usual RAG advice):

- One fact-cluster per chunk: one skill, one job, one gap, one project... small enough
  that a hit is precise, big enough to stand on its own ("Kubernetes is missing for the
  Acme job" makes sense without any other chunk).
- Written as plain sentences using the words people ASK with ("missing", "proof",
  "learn", "verified", "on your CV"), because keyword search (BM25) only matches words
  that are literally there. Embeddings (stage 66) relax that.
- Every chunk carries a source (a link to the page it came from), so answers can cite.

Nothing is stored: chunks are rebuilt from PostgreSQL on every question, so they're
never stale (fine at this size; a big system would index ahead of time). Only the
current user's records are used; skills are the shared taxonomy, as everywhere else.
Read-only.
"""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.services import match_service
from app.rag.sanitize import safe
from app.db.models import (
    CVSkillPresence,
    Education,
    Evidence,
    JobDescription,
    LearningProgress,
    Project,
    Skill,
    User,
    UserSkill,
    WorkExperience,
)
from app.db.models.enums import LearningStatus, VerificationStatus


@dataclass(frozen=True)
class Chunk:
    id: str  # stable and unique, e.g. "skill:3", "gap:2:Kubernetes"
    kind: str  # overview | profile | skill | job | gap | evidence | project | work | education
    title: str
    text: str
    link: str  # the frontend page the fact comes from
    lines: tuple[str, ...] = ()  # tool results only: the answer as display lines (stage 74)


def job_label(job: JobDescription) -> str:
    """Title (and company), else the start of the posting: same idea as the frontend's jobLabel."""
    if job.title and job.title.strip():
        label = job.title.strip()
    else:
        words = " ".join(job.raw_text.split())
        label = words if len(words) <= 50 else words[:50].rstrip() + "…"
    # Job text comes from the internet: drop instruction-like parts (stage 79, sanitize.py).
    label = safe(label) if label else label
    return f"{label} at {safe(job.company)}" if job.company else label


def _join(names: list[str]) -> str:
    return ", ".join(names) if names else "none"


def build_chunks(db: Session, user: User) -> list[Chunk]:
    skills = list(db.scalars(select(Skill).order_by(Skill.name)))
    claims = {c.skill_id: c for c in db.scalars(select(UserSkill).where(UserSkill.user_id == user.id))}
    on_cv = set(
        db.scalars(
            select(CVSkillPresence.skill_id).where(
                CVSkillPresence.user_id == user.id, CVSkillPresence.present.is_(True)
            )
        )
    )
    progress = {
        p.skill_id: p.status
        for p in db.scalars(select(LearningProgress).where(LearningProgress.user_id == user.id))
    }
    jobs = list(
        db.scalars(select(JobDescription).where(JobDescription.user_id == user.id).order_by(JobDescription.id))
    )
    matches = {job.id: match_service.job_match(db, user, job) for job in jobs}

    # skill_id -> ["Backend at Acme (missing)", ...] for "which jobs need X?"
    needed_by: dict[int, list[str]] = {}
    for job in jobs:
        match = matches[job.id]
        for group, word in ((match.proven, "proven"), (match.on_cv, "on your CV, not proven"), (match.missing, "missing")):
            for item in group:
                if item.skill_id is not None:
                    needed_by.setdefault(item.skill_id, []).append(f"{job_label(job)} ({word})")

    chunks: list[Chunk] = []

    # --- skills -------------------------------------------------------------------------------
    for skill in skills:
        claim = claims.get(skill.id)
        proof = [link.evidence.title for link in claim.evidence_links] if claim else []
        if claim is None:
            status = "not claimed: you haven't said you have this skill"
        elif claim.status == VerificationStatus.VERIFIED:
            status = f"verified, proven by evidence: {_join(proof)}"
        elif claim.status == VerificationStatus.PARTIAL:
            status = f"partially proven, evidence: {_join(proof)}"
        elif proof:
            status = f"provisional (claimed, not marked verified yet), evidence linked: {_join(proof)}"
        elif claim.status == VerificationStatus.NOT_VERIFIED:
            status = "not verified, no proof"
        else:
            status = "provisional: claimed but not proven yet, no proof or evidence linked"
        learning = {
            LearningStatus.STUDYING: "studying it now",
            LearningStatus.FINISHED: "finished studying it",
        }.get(progress.get(skill.id), "not started learning")
        aliases = [a.alias for a in skill.aliases]
        parts = [
            f"Skill: {skill.name}" + (f" ({skill.category})" if skill.category else "") + ".",
            f"Also written as: {_join(aliases)}." if aliases else "",
            f"Your status: {status}.",
            f"On your CV: {'yes' if skill.id in on_cv else 'no'}.",
            f"Learning progress: {learning}.",
            f"Jobs that need it: {_join(needed_by.get(skill.id, []))}.",
        ]
        chunks.append(
            Chunk(f"skill:{skill.id}", "skill", skill.name, " ".join(p for p in parts if p), f"/skills/{skill.id}")
        )

    # --- jobs and their gaps --------------------------------------------------------------------
    for job in jobs:
        match = matches[job.id]
        label = job_label(job)
        application = job.application_status.value
        if job.applied_on:
            application += f", applied on {job.applied_on.isoformat()}"
        if job.next_interview_at:
            application += f", next interview {job.next_interview_at.isoformat(timespec='minutes')}"
        if not match.has_cv:
            fit = f"Match: not available yet because your CV hasn't been added. It asks for {match.total} skills."
        else:
            fit = (
                f"Match: {match.percent}%, you have {len(match.proven) + len(match.on_cv)} of {match.total} skills."
            )
        text = " ".join(
            [
                f"Job description: {label}.",
                f"Application status: {application}.",
                fit,
                f"Proven skills: {_join([safe(i.name) for i in match.proven])}.",
                f"On your CV but not proven: {_join([safe(i.name) for i in match.on_cv])}.",
                f"Missing skills (gaps to learn): {_join([safe(i.name) for i in match.missing])}.",
            ]
        )
        chunks.append(Chunk(f"job:{job.id}", "job", label, text, f"/job-descriptions/{job.id}"))

        for item in match.missing:
            name = safe(item.name)  # an unmatched requirement is the posting's own words
            need = "required" if item.is_required else "nice to have"
            text = (
                f"Gap: {name} is missing for the job {label} ({need}). "
                f"To close this gap: learn {name} (full course and interview question videos), "
                f"then build a project with it and link it as evidence to prove the skill."
            )
            link = f"/skills/{item.skill_id}" if item.skill_id is not None else f"/job-descriptions/{job.id}"
            chunks.append(Chunk(f"gap:{job.id}:{item.name}", "gap", f"{name} gap", text, link))

    # --- proof and profile ----------------------------------------------------------------------
    for evidence in db.scalars(select(Evidence).where(Evidence.user_id == user.id).order_by(Evidence.id)):
        proves = [
            f"{link.user_skill.skill.name} ({link.user_skill.status.value})" for link in evidence.user_skill_links
        ]
        source = (
            f" from project {evidence.project.name}" if evidence.project
            else f" from work at {evidence.work_experience.company}" if evidence.work_experience
            else f" from {evidence.education.institution}" if evidence.education
            else ""
        )
        text = (
            f"Evidence (proof): {evidence.title}, a {evidence.evidence_type.value.replace('_', ' ')}{source}. "
            f"It proves these skills: {_join(proves)}."
            + (f" Details: {evidence.description}" if evidence.description else "")
        )
        chunks.append(Chunk(f"evidence:{evidence.id}", "evidence", evidence.title, text, "/profile"))

    def dates(start, end, open_word: str = "present") -> str:
        if start is None and end is None:
            return "dates not given"
        return f"{start.isoformat() if start else '?'} to {end.isoformat() if end else open_word}"

    for project in db.scalars(select(Project).where(Project.user_id == user.id).order_by(Project.id)):
        text = f"Project: {project.name}, {dates(project.start_date, project.end_date, 'ongoing')}."
        if project.role:
            text += f" Your role: {project.role}."
        if project.description:
            text += f" About it: {project.description}"
        chunks.append(Chunk(f"project:{project.id}", "project", project.name, text, "/profile"))
    for work in db.scalars(select(WorkExperience).where(WorkExperience.user_id == user.id).order_by(WorkExperience.id)):
        text = f"Work experience: {work.role} at {work.company}, {dates(work.start_date, work.end_date)}."
        if work.description:
            text += f" What you did: {work.description}"
        chunks.append(Chunk(f"work:{work.id}", "work", f"{work.role} at {work.company}", text, "/profile"))
    for education in db.scalars(select(Education).where(Education.user_id == user.id).order_by(Education.id)):
        degree = ", ".join(x for x in (education.degree, education.field_of_study) if x) or "studies"
        text = f"Education: {degree} at {education.institution}, {dates(education.start_date, education.end_date)}."
        if education.description:
            text += f" Notes: {education.description}"
        chunks.append(Chunk(f"education:{education.id}", "education", education.institution, text, "/profile"))

    # --- one overview, for "summary" questions --------------------------------------------------
    verified = [s.name for s in skills if claims.get(s.id) and claims[s.id].status == VerificationStatus.VERIFIED]
    unproven = [
        s.name for s in skills
        if claims.get(s.id) and claims[s.id].status != VerificationStatus.VERIFIED and not claims[s.id].evidence_links
    ]
    missing_count: dict[str, int] = {}
    for match in matches.values():
        for item in match.missing:
            name = safe(item.name)
            missing_count[name] = missing_count.get(name, 0) + 1
    most_needed = sorted(missing_count, key=lambda name: (-missing_count[name], name))[:5]
    overview = (
        f"Overview summary of your career data: {len(skills)} skills saved, {len(on_cv)} on your CV, "
        f"{len(verified)} verified (proven): {_join(verified)}. "
        f"Skills claimed without any proof yet: {_join(unproven)}. "
        f"{len(jobs)} job descriptions pasted. "
        f"Most needed missing skills to learn first: {_join(most_needed)}."
    )
    chunks.insert(0, Chunk("overview", "overview", "Your overview", overview, "/"))

    # --- who you are, for "what is my name?" ----------------------------------------------------
    if user.full_name:
        about = f"Your name is {user.full_name}. This is your profile: who you are, about me."
    else:
        about = (
            "Your name is not saved yet. Add your name on the Profile page, or add your CV "
            "and it will be read from the top of it. This is your profile: who you are, about me."
        )
    chunks.insert(1, Chunk("profile", "profile", "Your name and profile", about, "/profile"))
    return chunks
