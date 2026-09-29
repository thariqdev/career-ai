"""User-skill endpoints: claim a skill, list claims, link evidence, request a status change.

Routes stay thin: they call skill_service/verification_service, which are unchanged by
this file, and commit after a successful write (services flush but never commit).
Domain errors (EvidenceOwnershipError, EvidenceAlreadyLinkedError, InsufficientEvidenceError)
are never caught here — they flow to the app-wide handler in errors.py, already mapped to
HTTP statuses.

Ownership check (404, never 403), same reasoning as job_descriptions.py: a UserSkill that
doesn't exist and one that exists but belongs to someone else return the identical 404,
via the one shared helper below.

Claiming a skill twice: this route explicitly checks for an existing (user_id, skill_id)
claim and returns 409 before inserting, rather than letting UserSkill's DB-level unique
constraint (uq_user_skill) fail. Chosen because: (1) it gives a clean, predictable
{"detail": ...} body, consistent with every other collision response in this API (e.g.
skill_service's SkillNameCollisionError -> 409), instead of a raw IntegrityError surfacing
as an unhandled 500; (2) there is exactly one caller of "create a UserSkill" today (this
route) — if a second caller appears later, this check is small enough to promote into a
dedicated user_skill_service at that point.

Every route resolves user: User = Depends(get_current_user); no route or schema here
takes a user_id.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.models import EvidenceLinkCreate, StatusUpdate, UserSkillCreate, UserSkillResponse
from app.core.services import skill_service, verification_service
from app.db.models import Evidence, Skill, User, UserSkill
from app.dependencies import get_current_user, get_db

router = APIRouter(prefix="/user-skills", tags=["user-skills"])


def _get_owned_user_skill(db: Session, user_skill_id: int, user: User) -> UserSkill:
    """Load a UserSkill claim the current user owns, or raise 404 (never 403)."""
    user_skill = db.get(UserSkill, user_skill_id)
    if user_skill is None or user_skill.user_id != user.id:
        raise HTTPException(status_code=404, detail=f"UserSkill {user_skill_id} not found.")
    return user_skill


@router.post("", response_model=UserSkillResponse, status_code=201)
def claim_skill(
    payload: UserSkillCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UserSkill:
    skill = skill_service.get_skill(db, payload.skill_id)
    if skill is None:
        raise HTTPException(status_code=404, detail=f"Skill {payload.skill_id} not found.")

    existing = db.scalar(
        select(UserSkill).where(
            UserSkill.user_id == user.id, UserSkill.skill_id == payload.skill_id
        )
    )
    if existing is not None:
        raise HTTPException(status_code=409, detail=f"Skill {payload.skill_id} is already claimed.")

    user_skill = UserSkill(user=user, skill=skill)
    db.add(user_skill)
    db.commit()
    return user_skill


@router.get("", response_model=list[UserSkillResponse])
def list_user_skills(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> list[UserSkill]:
    return list(
        db.scalars(
            select(UserSkill)
            .join(Skill, UserSkill.skill_id == Skill.id)
            .where(UserSkill.user_id == user.id)
            .order_by(Skill.name, Skill.id)
        )
    )


@router.post("/{user_skill_id}/evidence-links", response_model=UserSkillResponse, status_code=201)
def link_evidence(
    user_skill_id: int,
    payload: EvidenceLinkCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UserSkill:
    user_skill = _get_owned_user_skill(db, user_skill_id, user)

    evidence = db.get(Evidence, payload.evidence_id)
    if evidence is None:
        raise HTTPException(status_code=404, detail=f"Evidence {payload.evidence_id} not found.")
    # Evidence that exists but is owned by someone else is NOT checked here:
    # verification_service.link_evidence already raises EvidenceOwnershipError for that
    # (mapped to 409) — checking it here too would duplicate the service's own rule.

    verification_service.link_evidence(db, user_skill, evidence)
    db.commit()
    return user_skill


@router.post("/{user_skill_id}/status", response_model=UserSkillResponse)
def update_status(
    user_skill_id: int,
    payload: StatusUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UserSkill:
    user_skill = _get_owned_user_skill(db, user_skill_id, user)
    verification_service.set_status(db, user_skill, payload.status)
    db.commit()
    return user_skill
