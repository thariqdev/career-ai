"""Learning-resource endpoints: list a skill's resources, save a link, remove a link.

Routes stay thin: they call learning_service and commit after a successful write.
Each saved link belongs to the user who saved it (stage 97), for a skill from the shared
dictionary; another user's link is reported as not found. Domain errors (blank title, bad URL, duplicate) flow to errors.py.
"""

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app.core.models import (
    LearningModeResources,
    LearningResourceCreate,
    LearningResourceResponse,
    SkillLearningResourcesResponse,
)
from app.core.services import learning_service, skill_service
from app.db.models import LearningResource, Skill, User
from app.db.models.enums import LearningMode
from app.dependencies import get_current_user, get_db

router = APIRouter(tags=["learning-resources"])


def _get_skill(db: Session, skill_id: int) -> Skill:
    skill = skill_service.get_skill(db, skill_id)
    if skill is None:
        raise HTTPException(status_code=404, detail=f"Skill {skill_id} not found.")
    return skill


@router.get("/skills/{skill_id}/learning-resources", response_model=SkillLearningResourcesResponse)
def read_learning_resources(
    skill_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> SkillLearningResourcesResponse:
    skill = _get_skill(db, skill_id)
    saved = learning_service.list_resources(db, user, skill)
    return SkillLearningResourcesResponse(
        skill_id=skill.id,
        skill_name=skill.name,
        modes=[
            LearningModeResources(
                mode=mode.value,
                search_query=learning_service.search_query(skill.name, mode),
                search_url=learning_service.youtube_search_url(skill.name, mode),
                resources=[
                    LearningResourceResponse.model_validate(r) for r in saved if r.mode == mode
                ],
            )
            for mode in LearningMode
        ],
    )


@router.post(
    "/skills/{skill_id}/learning-resources",
    response_model=LearningResourceResponse,
    status_code=201,
)
def add_learning_resource(
    skill_id: int,
    payload: LearningResourceCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> LearningResource:
    skill = _get_skill(db, skill_id)
    resource = learning_service.add_resource(db, user, skill, payload.mode, payload.title, payload.url)
    db.commit()
    return resource


@router.delete("/learning-resources/{resource_id}", status_code=204)
def remove_learning_resource(
    resource_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> Response:
    resource = db.get(LearningResource, resource_id)
    if resource is None or resource.user_id != user.id:
        raise HTTPException(status_code=404, detail=f"Learning resource {resource_id} not found.")
    learning_service.remove_resource(db, resource)
    db.commit()
    return Response(status_code=204)
