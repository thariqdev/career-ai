"""A read-only backup of everything Career AI stores for one user, as plain data.

Nothing here is generated or inferred: every value is exactly what is in PostgreSQL, so
the export doubles as an honest record of what the app knows. Ids are kept so the links
between records (claim -> evidence, requirement -> results) stay understandable.

Ownership: per-user tables are filtered by the user (directly, or through the job or
claim they belong to), so another user's data never appears. Skills, nicknames and
saved learning links are a shared taxonomy, so all of them are included.

Same conventions as the other services: plain functions taking a Session, no HTTP
knowledge, and this one never writes (it doesn't even flush).
"""

import enum
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    ComparisonResult,
    ComparisonResultEvidence,
    CVSkillPresence,
    DismissedRequirement,
    Education,
    Evidence,
    JobDescription,
    JobRequirement,
    LearningProgress,
    LearningResource,
    Project,
    Skill,
    SkillAlias,
    User,
    UserSkill,
    UserSkillEvidence,
    WorkExperience,
)

FORMAT_VERSION = 1


def _plain(value: Any) -> Any:
    """Turn a column value into something JSON can hold, without changing its meaning."""
    if isinstance(value, enum.Enum):
        return value.value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def _row(obj: Any, skip: tuple[str, ...] = ("user_id",)) -> dict[str, Any]:
    """Every column of one ORM row (minus the owner id, which is the same everywhere)."""
    return {
        column.key: _plain(getattr(obj, column.key))
        for column in obj.__table__.columns
        if column.key not in skip
    }


def export_all(db: Session, user: User) -> dict[str, Any]:
    """Everything stored for `user`, plus the shared skill taxonomy. Read-only."""

    def mine(model: type) -> list[Any]:
        return list(db.scalars(select(model).where(model.user_id == user.id).order_by(model.id)))

    aliases_by_skill: dict[int, list[str]] = {}
    for alias in db.scalars(select(SkillAlias).order_by(SkillAlias.id)):
        aliases_by_skill.setdefault(alias.skill_id, []).append(alias.alias)
    skills = [
        {**_row(skill), "aliases": aliases_by_skill.get(skill.id, [])}
        for skill in db.scalars(select(Skill).order_by(Skill.id))
    ]

    claims = mine(UserSkill)
    evidence_by_claim: dict[int, list[int]] = {}
    if claims:
        for link in db.scalars(
            select(UserSkillEvidence)
            .where(UserSkillEvidence.user_skill_id.in_([c.id for c in claims]))
            .order_by(UserSkillEvidence.user_skill_id, UserSkillEvidence.evidence_id)
        ):
            evidence_by_claim.setdefault(link.user_skill_id, []).append(link.evidence_id)

    jobs = []
    for job in mine(JobDescription):
        requirements = list(
            db.scalars(
                select(JobRequirement)
                .where(JobRequirement.job_description_id == job.id)
                .order_by(JobRequirement.id)
            )
        )
        results = list(
            db.scalars(
                select(ComparisonResult)
                .where(ComparisonResult.job_requirement_id.in_([r.id for r in requirements]))
                .order_by(ComparisonResult.id)
            )
        ) if requirements else []
        cited: dict[int, list[int]] = {}
        if results:
            for link in db.scalars(
                select(ComparisonResultEvidence)
                .where(ComparisonResultEvidence.comparison_result_id.in_([r.id for r in results]))
                .order_by(ComparisonResultEvidence.comparison_result_id, ComparisonResultEvidence.evidence_id)
            ):
                cited.setdefault(link.comparison_result_id, []).append(link.evidence_id)
        dismissed = db.scalars(
            select(DismissedRequirement.skill_id)
            .where(DismissedRequirement.job_description_id == job.id)
            .order_by(DismissedRequirement.skill_id)
        )
        jobs.append(
            {
                **_row(job),
                "requirements": [_row(r) for r in requirements],
                "comparison_results": [
                    {**_row(r), "evidence_ids": cited.get(r.id, [])} for r in results
                ],
                "removed_skill_ids": list(dismissed),
            }
        )

    return {
        "app": "Career AI",
        "format_version": FORMAT_VERSION,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "user": {"email": user.email, "full_name": user.full_name},
        "skills": skills,
        "claims": [{**_row(c), "evidence_ids": evidence_by_claim.get(c.id, [])} for c in claims],
        "evidence": [_row(e) for e in mine(Evidence)],
        "projects": [_row(p) for p in mine(Project)],
        "work_experiences": [_row(w) for w in mine(WorkExperience)],
        "educations": [_row(e) for e in mine(Education)],
        "job_descriptions": jobs,
        "cv_marks": [_row(m) for m in mine(CVSkillPresence)],
        "learning_progress": [_row(p) for p in mine(LearningProgress)],
        "learning_resources": [_row(r) for r in db.scalars(select(LearningResource).order_by(LearningResource.id))],
    }
