"""The user's own profile records: projects, work experience, education.

These are facts the user enters (never inferred, never filled in by AI). Their main
job is to be something reviewable that Evidence can point to ("this proof comes from
my FundsApp project"), per PROJECT_RULES.md sections 4 and 8.

Rules: required text can't be blank; optional text that's blank is stored as NULL;
an end date can't be before its start date; a project link must be http(s) because
the frontend renders it as a link. A record can't be removed while any Evidence points
to it (ProfileRecordInUseError), so proof never silently loses its source.

Same conventions as the other services: plain functions taking a Session, no HTTP
knowledge, flush but never commit, and flush before reading (autoflush=False).
"""

from datetime import date
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.exceptions import (
    EmptyProfileFieldError,
    InvalidDateRangeError,
    ProfileRecordInUseError,
)
from app.core.web_links import require_web_link
from app.db.models import Education, Evidence, Project, User, WorkExperience

# Which Evidence column points at each kind of record.
_EVIDENCE_COLUMN = {
    Project: Evidence.project_id,
    WorkExperience: Evidence.work_experience_id,
    Education: Evidence.education_id,
}


def _required(value: str, field: str) -> str:
    clean = value.strip()
    if not clean:
        raise EmptyProfileFieldError(field)
    return clean


def _optional(value: str | None) -> str | None:
    if value is None or not value.strip():
        return None
    return value.strip()


def _check_dates(start: date | None, end: date | None) -> None:
    if start is not None and end is not None and end < start:
        raise InvalidDateRangeError()


def create_project(
    db: Session,
    user: User,
    *,
    name: str,
    role: str | None = None,
    description: str | None = None,
    url: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
) -> Project:
    _check_dates(start_date, end_date)
    link = _optional(url)
    project = Project(
        user=user,
        name=_required(name, "Project name"),
        role=_optional(role),
        description=_optional(description),
        url=require_web_link(link) if link is not None else None,
        start_date=start_date,
        end_date=end_date,
    )
    db.add(project)
    db.flush()
    return project


def create_work_experience(
    db: Session,
    user: User,
    *,
    company: str,
    role: str,
    start_date: date,
    end_date: date | None = None,
    description: str | None = None,
) -> WorkExperience:
    _check_dates(start_date, end_date)
    work = WorkExperience(
        user=user,
        company=_required(company, "Company"),
        role=_required(role, "Role"),
        start_date=start_date,
        end_date=end_date,
        description=_optional(description),
    )
    db.add(work)
    db.flush()
    return work


def create_education(
    db: Session,
    user: User,
    *,
    institution: str,
    degree: str | None = None,
    field_of_study: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    description: str | None = None,
) -> Education:
    _check_dates(start_date, end_date)
    education = Education(
        user=user,
        institution=_required(institution, "Institution"),
        degree=_optional(degree),
        field_of_study=_optional(field_of_study),
        start_date=start_date,
        end_date=end_date,
        description=_optional(description),
    )
    db.add(education)
    db.flush()
    return education


def list_records(db: Session, user: User, model: type) -> list[Any]:
    """The user's records of one kind, most recent first (undated ones last). Read-only."""
    db.flush()
    return list(
        db.scalars(
            select(model)
            .where(model.user_id == user.id)
            .order_by(model.start_date.desc().nulls_last(), model.id.desc())
        )
    )


def delete_record(db: Session, record: Any, label: str) -> None:
    """Remove a profile record nothing cites; ProfileRecordInUseError (409) otherwise."""
    db.flush()
    column = _EVIDENCE_COLUMN[type(record)]
    count = db.scalar(select(func.count()).select_from(Evidence).where(column == record.id))
    if count:
        raise ProfileRecordInUseError(label, count)
    db.delete(record)
    db.flush()
