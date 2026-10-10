"""Deleting a job description, or one of its requirements, with the history that belongs only to it.

A job's requirements and their comparison results (and those results' evidence links)
exist only for that job, so they go with it. Nothing outside the job is touched:
skills, claims, evidence and CV marks stay exactly as they were. (Evidence itself is
never deleted here; only the ComparisonResultEvidence rows that cited it for this job.)

The same holds one level down: a single requirement's comparison results exist only
for that requirement, so delete_requirement removes them with it and leaves the job's
other requirements and results alone. It also leaves a "not for this job" note
(DismissedRequirement) for the requirement's skill, so re-reading the posting doesn't add
it back; allow_again deletes that note.

Rows are removed child-first, in foreign-key order, with bulk DELETE statements.

Same conventions as the other services: plain functions taking a Session, no HTTP
knowledge, flush but never commit.
"""

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.exceptions import DismissalNotFoundError, DuplicateJobDescriptionError
from app.core.services.skill_service import normalize_text
from app.db.models import (
    User,
    ComparisonResult,
    ComparisonResultEvidence,
    DismissedRequirement,
    JobDescription,
    JobRequirement,
    Skill,
)


def delete_job_description(db: Session, job_description: JobDescription) -> None:
    db.flush()
    requirement_ids = select(JobRequirement.id).where(
        JobRequirement.job_description_id == job_description.id
    )
    result_ids = select(ComparisonResult.id).where(
        ComparisonResult.job_requirement_id.in_(requirement_ids)
    )
    db.execute(
        delete(ComparisonResultEvidence).where(
            ComparisonResultEvidence.comparison_result_id.in_(result_ids)
        )
    )
    db.execute(delete(ComparisonResult).where(ComparisonResult.job_requirement_id.in_(requirement_ids)))
    db.execute(delete(JobRequirement).where(JobRequirement.job_description_id == job_description.id))
    db.execute(
        delete(DismissedRequirement).where(
            DismissedRequirement.job_description_id == job_description.id
        )
    )
    db.execute(delete(JobDescription).where(JobDescription.id == job_description.id))
    db.flush()


def delete_requirement(db: Session, requirement: JobRequirement) -> None:
    """Remove one requirement with its own comparison results (and their evidence links).

    Nothing else is touched: other requirements of the job keep their results. If the
    requirement maps to a skill, a "not for this job" note is kept (once per job and
    skill), so "Look for new skills" doesn't add it back. A requirement without a skill
    leaves no note: there's nothing stable to key it on.
    """
    db.flush()
    result_ids = select(ComparisonResult.id).where(
        ComparisonResult.job_requirement_id == requirement.id
    )
    db.execute(
        delete(ComparisonResultEvidence).where(
            ComparisonResultEvidence.comparison_result_id.in_(result_ids)
        )
    )
    db.execute(delete(ComparisonResult).where(ComparisonResult.job_requirement_id == requirement.id))
    db.execute(delete(JobRequirement).where(JobRequirement.id == requirement.id))
    job_id, skill_id = requirement.job_description_id, requirement.skill_id
    if skill_id is not None and _dismissal(db, job_id, skill_id) is None:
        db.add(DismissedRequirement(job_description_id=job_id, skill_id=skill_id))
    db.flush()


def _dismissal(db: Session, job_description_id: int, skill_id: int) -> DismissedRequirement | None:
    return db.scalar(
        select(DismissedRequirement).where(
            DismissedRequirement.job_description_id == job_description_id,
            DismissedRequirement.skill_id == skill_id,
        )
    )


def dismissed_skills(db: Session, job_description: JobDescription) -> list[Skill]:
    """The skills removed from this job, by name. Read-only."""
    db.flush()
    return list(
        db.scalars(
            select(Skill)
            .join(DismissedRequirement, DismissedRequirement.skill_id == Skill.id)
            .where(DismissedRequirement.job_description_id == job_description.id)
            .order_by(Skill.name, Skill.id)
        )
    )


def allow_again(db: Session, job_description: JobDescription, skill_id: int) -> None:
    """Delete the "not for this job" note. Re-adds nothing: a later re-read may find it."""
    db.flush()
    note = _dismissal(db, job_description.id, skill_id)
    if note is None:
        raise DismissalNotFoundError(skill_id)
    db.delete(note)
    db.flush()


def find_duplicate(db: Session, user: User, raw_text: str) -> JobDescription | None:
    """This user's job with the same posting text, ignoring case and spacing, if any."""
    key = normalize_text(raw_text)
    if not key:
        return None
    for job in db.scalars(select(JobDescription).where(JobDescription.user_id == user.id)):
        if normalize_text(job.raw_text) == key:
            return job
    return None


def create_job_description(
    db: Session,
    user: User,
    *,
    raw_text: str,
    title: str | None = None,
    company: str | None = None,
    source_url: str | None = None,
) -> JobDescription:
    """Save a pasted posting. Refuses the same text twice (DuplicateJobDescriptionError,
    409): an exact copy would only duplicate its requirements, results and match."""
    existing = find_duplicate(db, user, raw_text)
    if existing is not None:
        label = existing.title or " ".join(existing.raw_text.split())[:40]
        raise DuplicateJobDescriptionError(existing.created_at.strftime("%d/%m/%Y"), label)
    job = JobDescription(user=user, raw_text=raw_text, title=title, company=company, source_url=source_url)
    db.add(job)
    db.flush()
    return job
