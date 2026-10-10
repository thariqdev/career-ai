"""GET /me (who the app runs as) and PATCH /me (save your name).

get_current_user resolves (and, on first call, creates) the single user before these
routes run. The name is read from the CV when you add it, and can be edited on Profile.
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.models import UserResponse
from app.core.services import user_service
from app.db.models import User
from app.dependencies import get_current_user, get_db

router = APIRouter(tags=["me"])


@router.get("/me", response_model=UserResponse)
def read_current_user(user: User = Depends(get_current_user)) -> User:
    return user


class UserUpdate(BaseModel):
    full_name: str | None = Field(default=None, max_length=user_service.MAX_NAME_CHARS)


@router.patch("/me", response_model=UserResponse)
def update_current_user(
    payload: UserUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> User:
    user_service.set_full_name(db, user, payload.full_name)
    db.commit()
    return user
