"""Skills endpoints. Routes stay thin: call skill_service, commit on success.

Services flush but never commit, so each write route owns the transaction and commits
after a successful service call. If the service raises a DomainError the route never
reaches commit; the session closes and the transaction rolls back, and the app-wide
handler in errors.py turns the error into an HTTP response.

Skills themselves are a shared taxonomy, not per-user data, so most routes here are not
user-scoped. The cv-presence/cv-status routes are the exception: a skill's presence on
*your* CV is per-user, so those two use Depends(get_current_user).

Setting CV presence is an UPSERT (see cv_presence_service, shared with the CV upload).
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.models import (
    AliasCreate,
    CVPresenceResponse,
    CVPresenceUpdate,
    CVStatusResponse,
    SkillCreate,
    SkillResponse,
)
from app.core.services import cv_presence_service, cv_service, skill_service
from app.db.models import CVSkillPresence, Skill, User
from app.dependencies import get_current_user, get_db

router = APIRouter(prefix="/skills", tags=["skills"])

# Routes return ORM Skill objects; response_model=SkillResponse converts them (from_attributes).


@router.post("", response_model=SkillResponse, status_code=201)
def create_skill(payload: SkillCreate, db: Session = Depends(get_db)) -> Skill:
    skill = skill_service.create_skill(db, payload.name, payload.category)
    db.commit()
    return skill


@router.get("", response_model=list[SkillResponse])
def list_skills(db: Session = Depends(get_db)) -> list[Skill]:
    return skill_service.list_skills(db)


# Declared before any future "/{skill_id}" GET route so "resolve" is never captured as an id.
@router.get("/resolve", response_model=SkillResponse)
def resolve_skill(text: str, db: Session = Depends(get_db)) -> Skill:
    """Read-only lookup: never creates a skill or alias."""
    skill = skill_service.resolve_skill(db, text)
    if skill is None:
        raise HTTPException(status_code=404, detail="No matching skill.")
    return skill


@router.post("/{skill_id}/aliases", response_model=SkillResponse, status_code=201)
def add_alias(skill_id: int, payload: AliasCreate, db: Session = Depends(get_db)) -> Skill:
    skill = skill_service.get_skill(db, skill_id)
    if skill is None:
        raise HTTPException(status_code=404, detail=f"Skill {skill_id} not found.")
    skill_service.add_alias(db, skill, payload.alias)
    db.commit()
    return skill


# The alias goes in the query string, not the path: an alias like "CI/CD" would be
# split on its "/" by path routing even when URL-encoded.
@router.delete("/{skill_id}/aliases", response_model=SkillResponse)
def remove_alias(skill_id: int, alias: str, db: Session = Depends(get_db)) -> Skill:
    skill = skill_service.get_skill(db, skill_id)
    if skill is None:
        raise HTTPException(status_code=404, detail=f"Skill {skill_id} not found.")
    skill_service.remove_alias(db, skill, alias)
    db.commit()
    return skill


@router.patch("/{skill_id}/cv-presence", response_model=CVPresenceResponse)
def set_cv_presence(
    skill_id: int,
    payload: CVPresenceUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CVSkillPresence:
    skill = skill_service.get_skill(db, skill_id)
    if skill is None:
        raise HTTPException(status_code=404, detail=f"Skill {skill_id} not found.")
    presence = cv_presence_service.set_cv_presence(db, user, skill, payload.present)
    db.commit()
    return presence


@router.get("/{skill_id}/cv-status", response_model=CVStatusResponse)
def read_cv_status(
    skill_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CVStatusResponse:
    skill = skill_service.get_skill(db, skill_id)
    if skill is None:
        raise HTTPException(status_code=404, detail=f"Skill {skill_id} not found.")
    # Read-only: no commit. cv_service.combined_status only reads (same reasoning as
    # GET .../gaps in job_descriptions.py), and get_current_user already committed the
    # one write this request could ever need (creating the bootstrap user, if needed).
    combined = cv_service.combined_status(db, user, skill)
    return CVStatusResponse.from_combined_status(combined)
