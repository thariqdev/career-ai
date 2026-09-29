"""Evidence endpoints: record a piece of proof, list your own evidence.

Routes stay thin. POST builds the Evidence row directly rather than through a service —
same reasoning as JobDescription's own creation: there's no business rule beyond shape
(which EvidenceCreate's typed evidence_type field already enforces via Pydantic), only an
ownership check on any work_experience_id/project_id/education_id given, so a dedicated
service isn't warranted yet.

Sub-record ownership (404, never 403): if a work_experience_id/project_id/education_id is
given, it must exist AND belong to the current user, or the route responds 404 — the same
"exists-and-mine, or 404" principle used throughout this API (see job_descriptions.py),
extended here so evidence can never silently cite a record it has no business referencing.

Every route resolves user: User = Depends(get_current_user); no route or schema here
takes a user_id.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.models import EvidenceCreate, EvidenceResponse
from app.db.models import Education, Evidence, Project, User, WorkExperience
from app.dependencies import get_current_user, get_db

router = APIRouter(prefix="/evidence", tags=["evidence"])


def _require_owned_reference(
    db: Session, model: type, record_id: int | None, user: User, label: str
) -> None:
    """If record_id is given, it must exist and belong to the current user, else 404."""
    if record_id is None:
        return
    record = db.get(model, record_id)
    if record is None or record.user_id != user.id:
        raise HTTPException(status_code=404, detail=f"{label} {record_id} not found.")


@router.post("", response_model=EvidenceResponse, status_code=201)
def create_evidence(
    payload: EvidenceCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Evidence:
    _require_owned_reference(db, WorkExperience, payload.work_experience_id, user, "Work experience")
    _require_owned_reference(db, Project, payload.project_id, user, "Project")
    _require_owned_reference(db, Education, payload.education_id, user, "Education")

    evidence = Evidence(
        user=user,
        evidence_type=payload.evidence_type,
        title=payload.title,
        description=payload.description,
        url=payload.url,
        work_experience_id=payload.work_experience_id,
        project_id=payload.project_id,
        education_id=payload.education_id,
    )
    db.add(evidence)
    db.commit()
    return evidence


@router.get("", response_model=list[EvidenceResponse])
def list_evidence(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> list[Evidence]:
    return list(
        db.scalars(
            select(Evidence)
            .where(Evidence.user_id == user.id)
            .order_by(Evidence.created_at, Evidence.id)
        )
    )
