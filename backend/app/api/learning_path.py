"""Learning-path endpoints: the four-step path for one skill, or for several at once.

Read-only and user-scoped; all the logic lives in learning_path_service.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.models import LearningPathResponse
from app.core.services import learning_path_service, skill_service
from app.db.models import Skill, User
from app.dependencies import get_current_user, get_db

router = APIRouter(tags=["learning-path"])


@router.get("/skills/{skill_id}/learning-path", response_model=LearningPathResponse)
def read_learning_path(
    skill_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> LearningPathResponse:
    skill = skill_service.get_skill(db, skill_id)
    if skill is None:
        raise HTTPException(status_code=404, detail=f"Skill {skill_id} not found.")
    [path] = learning_path_service.learning_paths(db, user, [skill])
    return LearningPathResponse.from_path(path)


@router.get("/learning-paths", response_model=list[LearningPathResponse])
def read_learning_paths(
    skill_ids: list[int] = Query(default=[]),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[LearningPathResponse]:
    """Paths for several skills (?skill_ids=1&skill_ids=2), in the order asked.

    Duplicates are collapsed and unknown ids are skipped: this is a convenience read
    for lists like the Dashboard's, not a lookup that should fail as a whole.
    """
    wanted = list(dict.fromkeys(skill_ids))
    by_id = {s.id: s for s in db.scalars(select(Skill).where(Skill.id.in_(wanted)))} if wanted else {}
    skills = [by_id[i] for i in wanted if i in by_id]
    return [
        LearningPathResponse.from_path(p)
        for p in learning_path_service.learning_paths(db, user, skills)
    ]
