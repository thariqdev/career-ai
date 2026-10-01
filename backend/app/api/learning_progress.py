"""Learning-progress endpoints: set your progress on a skill, list your progress.

Routes stay thin: they call learning_progress_service and commit after a write.
Progress is personal, so both routes resolve the single user via get_current_user;
no route or schema takes a user_id.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.models import LearningProgressResponse, LearningProgressUpdate
from app.core.services import learning_progress_service, skill_service
from app.db.models import User
from app.db.models.enums import LearningStatus
from app.dependencies import get_current_user, get_db

router = APIRouter(tags=["learning-progress"])


@router.put("/skills/{skill_id}/learning-progress", response_model=LearningProgressResponse)
def set_learning_progress(
    skill_id: int,
    payload: LearningProgressUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> LearningProgressResponse:
    skill = skill_service.get_skill(db, skill_id)
    if skill is None:
        raise HTTPException(status_code=404, detail=f"Skill {skill_id} not found.")
    status = None if payload.status == "not_started" else LearningStatus(payload.status)
    progress = learning_progress_service.set_progress(db, user, skill, status)
    db.commit()
    return LearningProgressResponse.for_skill(skill, progress)


@router.get("/learning-progress", response_model=list[LearningProgressResponse])
def list_learning_progress(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> list[LearningProgressResponse]:
    return [
        LearningProgressResponse.for_skill(progress.skill, progress)
        for progress in learning_progress_service.list_progress(db, user)
    ]
