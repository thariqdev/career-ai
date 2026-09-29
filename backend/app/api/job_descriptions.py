"""Job-descriptions endpoints: create, read, extract requirements, compare, read gaps.

Routes stay thin: they call requirement_service/comparison_service, which are unchanged
by this file, and commit after a successful write (services flush but never commit).
Domain errors (e.g. RequirementsAlreadyExistError) are never caught here — they flow to
the app-wide handler in errors.py, already mapped to HTTP statuses.

Ownership check (404, never 403): whether a job description exists AND belongs to the
current user is checked once per route, via _get_owned_job_description. A wrong owner
and a missing id return the exact same 404, so a caller can never use the response to
learn whether some other user's job description id exists. This is an HTTP-layer
concern about what a response may reveal, not a domain rule, so it lives here rather
than in a service — requirement_service and comparison_service take a JobDescription
object already, so they never need to know about ownership at all.

Every route resolves user: User = Depends(get_current_user); no route or schema here
takes a user_id.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.client import RequirementExtractor
from app.core.models import (
    ComparisonResultResponse,
    ExtractionResponse,
    GapResponse,
    JobDescriptionCreate,
    JobDescriptionResponse,
    RejectedRequirementResponse,
)
from app.core.services import comparison_service, requirement_service
from app.db.models import JobDescription, User
from app.dependencies import get_current_user, get_db, get_requirement_extractor

router = APIRouter(prefix="/job-descriptions", tags=["job-descriptions"])


def _get_owned_job_description(db: Session, job_description_id: int, user: User) -> JobDescription:
    """Load a job description the current user owns, or raise 404 (never 403)."""
    job_description = db.get(JobDescription, job_description_id)
    if job_description is None or job_description.user_id != user.id:
        raise HTTPException(status_code=404, detail=f"Job description {job_description_id} not found.")
    return job_description


@router.post("", response_model=JobDescriptionResponse, status_code=201)
def create_job_description(
    payload: JobDescriptionCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> JobDescription:
    # No business rule to enforce beyond shape (which Pydantic already checked), so this
    # is built directly rather than through a service — same as SkillCreate's own
    # construction has none; only skill_service's actual rules (create_skill, add_alias)
    # warrant a service.
    job_description = JobDescription(
        user=user,
        raw_text=payload.raw_text,
        title=payload.title,
        company=payload.company,
        source_url=payload.source_url,
    )
    db.add(job_description)
    db.commit()
    return job_description


@router.get("", response_model=list[JobDescriptionResponse])
def list_job_descriptions(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[JobDescription]:
    # Read-only: no commit needed beyond what get_current_user already did.
    # id.desc() breaks ties when created_at is identical (e.g. two inserts within the
    # same clock tick — SQLite's CURRENT_TIMESTAMP only has second resolution), so
    # "most recent first" stays deterministic even then.
    return list(
        db.scalars(
            select(JobDescription)
            .where(JobDescription.user_id == user.id)
            .order_by(JobDescription.created_at.desc(), JobDescription.id.desc())
        )
    )


@router.get("/{job_description_id}", response_model=JobDescriptionResponse)
def read_job_description(
    job_description_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> JobDescription:
    return _get_owned_job_description(db, job_description_id, user)


@router.post("/{job_description_id}/extract", response_model=ExtractionResponse)
def extract_requirements(
    job_description_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    extractor: RequirementExtractor = Depends(get_requirement_extractor),
) -> ExtractionResponse:
    job_description = _get_owned_job_description(db, job_description_id, user)
    outcome = requirement_service.extract_requirements(db, job_description, extractor)
    db.commit()
    return ExtractionResponse(
        accepted=outcome.accepted,
        rejected=[RejectedRequirementResponse.from_rejection(r) for r in outcome.rejected],
    )


@router.post("/{job_description_id}/compare", response_model=list[ComparisonResultResponse])
def compare_job_description(
    job_description_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list:
    job_description = _get_owned_job_description(db, job_description_id, user)
    results = comparison_service.compare_job_description(db, job_description)
    db.commit()
    return results


@router.get("/{job_description_id}/gaps", response_model=list[GapResponse])
def read_skill_gaps(
    job_description_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[GapResponse]:
    # Read-only: no commit. skill_gaps only reads (see comparison_service), and
    # get_current_user already committed the one write this request could ever need
    # (creating the bootstrap user, if it didn't already exist).
    job_description = _get_owned_job_description(db, job_description_id, user)
    gaps = comparison_service.skill_gaps(db, job_description)
    return [GapResponse.from_gap(gap) for gap in gaps]
