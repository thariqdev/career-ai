"""Profile endpoints: the user's projects, work experience and education.

Add, list (most recent first), edit (PATCH: only the fields sent change) and remove
for each kind. Routes stay thin: rules live in
profile_service, and each write commits on success. Everything is user-scoped via
get_current_user, and a record that doesn't exist or isn't yours is the same 404
(never 403), as everywhere else in this API.
"""

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app.core.models import (
    EducationCreate,
    EducationResponse,
    EducationUpdate,
    ProjectCreate,
    ProjectResponse,
    ProjectUpdate,
    WorkExperienceCreate,
    WorkExperienceResponse,
    WorkExperienceUpdate,
)
from app.core.services import profile_service
from app.db.models import Education, Project, User, WorkExperience
from app.dependencies import get_current_user, get_db

router = APIRouter(tags=["profile"])


def _owned(db: Session, model: type, record_id: int, user: User, label: str):
    record = db.get(model, record_id)
    if record is None or record.user_id != user.id:
        raise HTTPException(status_code=404, detail=f"{label} {record_id} not found.")
    return record


# --- projects -------------------------------------------------------------------


@router.get("/projects", response_model=list[ProjectResponse])
def list_projects(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list:
    return profile_service.list_records(db, user, Project)


@router.post("/projects", response_model=ProjectResponse, status_code=201)
def add_project(
    payload: ProjectCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> Project:
    project = profile_service.create_project(db, user, **payload.model_dump())
    db.commit()
    return project


@router.patch("/projects/{project_id}", response_model=ProjectResponse)
def edit_project(
    project_id: int,
    payload: ProjectUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Project:
    project = _owned(db, Project, project_id, user, "Project")
    profile_service.update_record(db, project, payload.model_dump(exclude_unset=True))
    db.commit()
    return project


@router.delete("/projects/{project_id}", status_code=204)
def remove_project(
    project_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> Response:
    project = _owned(db, Project, project_id, user, "Project")
    profile_service.delete_record(db, project, f'Project "{project.name}"')
    db.commit()
    return Response(status_code=204)


# --- work experience ---------------------------------------------------------------


@router.get("/work-experiences", response_model=list[WorkExperienceResponse])
def list_work_experiences(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> list:
    return profile_service.list_records(db, user, WorkExperience)


@router.post("/work-experiences", response_model=WorkExperienceResponse, status_code=201)
def add_work_experience(
    payload: WorkExperienceCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> WorkExperience:
    work = profile_service.create_work_experience(db, user, **payload.model_dump())
    db.commit()
    return work


@router.patch("/work-experiences/{work_experience_id}", response_model=WorkExperienceResponse)
def edit_work_experience(
    work_experience_id: int,
    payload: WorkExperienceUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> WorkExperience:
    work = _owned(db, WorkExperience, work_experience_id, user, "Work experience")
    profile_service.update_record(db, work, payload.model_dump(exclude_unset=True))
    db.commit()
    return work


@router.delete("/work-experiences/{work_experience_id}", status_code=204)
def remove_work_experience(
    work_experience_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    work = _owned(db, WorkExperience, work_experience_id, user, "Work experience")
    profile_service.delete_record(db, work, f'Your role at "{work.company}"')
    db.commit()
    return Response(status_code=204)


# --- education --------------------------------------------------------------------


@router.get("/educations", response_model=list[EducationResponse])
def list_educations(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list:
    return profile_service.list_records(db, user, Education)


@router.post("/educations", response_model=EducationResponse, status_code=201)
def add_education(
    payload: EducationCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> Education:
    education = profile_service.create_education(db, user, **payload.model_dump())
    db.commit()
    return education


@router.patch("/educations/{education_id}", response_model=EducationResponse)
def edit_education(
    education_id: int,
    payload: EducationUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Education:
    education = _owned(db, Education, education_id, user, "Education")
    profile_service.update_record(db, education, payload.model_dump(exclude_unset=True))
    db.commit()
    return education


@router.delete("/educations/{education_id}", status_code=204)
def remove_education(
    education_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> Response:
    education = _owned(db, Education, education_id, user, "Education")
    profile_service.delete_record(db, education, f'Education at "{education.institution}"')
    db.commit()
    return Response(status_code=204)
