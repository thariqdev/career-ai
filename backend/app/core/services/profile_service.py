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


# Fields that can't be cleared, with the label used in the error message.
_REQUIRED = {
    Project: {"name": "Project name"},
    WorkExperience: {"company": "Company", "role": "Role", "start_date": "Start date"},
    Education: {"institution": "Institution"},
}


def update_record(db: Session, record: Any, changes: dict[str, Any]) -> Any:
    """Apply only the fields present in `changes` (a PATCH), then re-check every rule.

    A key that's absent keeps its value; None (or blank text) clears an optional field
    and is refused for a required one. Date order is checked on the record as it WILL
    be, so moving only the start date past the existing end date is caught too.
    """
    required = _REQUIRED[type(record)]
    clean: dict[str, Any] = {}
    for key, value in changes.items():
        if key in required:
            if value is None or (isinstance(value, str) and not value.strip()):
                raise EmptyProfileFieldError(required[key])
            clean[key] = value.strip() if isinstance(value, str) else value
        elif value is None or isinstance(value, str):
            clean[key] = _optional(value)
        else:
            clean[key] = value  # dates
    if clean.get("url") is not None:
        clean["url"] = require_web_link(clean["url"])

    _check_dates(
        clean.get("start_date", record.start_date), clean.get("end_date", record.end_date)
    )
    for key, value in clean.items():
        setattr(record, key, value)
    db.flush()
    return record


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
