"""Skills endpoints. Routes stay thin: call skill_service, commit on success.

Services flush but never commit, so each write route owns the transaction and commits
after a successful service call. If the service raises a DomainError the route never
reaches commit; the session closes and the transaction rolls back, and the app-wide
handler in errors.py turns the error into an HTTP response.

Skills are a shared taxonomy, not per-user data, so nothing here is user-scoped.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.models import AliasCreate, SkillCreate, SkillResponse
from app.core.services import skill_service
from app.db.models import Skill
from app.dependencies import get_db

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
