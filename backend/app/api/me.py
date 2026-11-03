"""GET /me (who the app runs as) and PATCH /me (save your name).

get_current_user resolves (and, on first call, creates) the single user before these
routes run. The name is read from the CV when you add it, and can be edited on Profile.
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.models import UserResponse
from app.core.services import auth_service, cv_replace_service, user_service
from app.core.exceptions import WrongCurrentPasswordError
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


class EmptyAccount(BaseModel):
    password: str = Field(max_length=auth_service.MAX_PASSWORD_CHARS)


@router.post("/me/empty")
def empty_account(
    payload: EmptyAccount,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Remove everything in your account but keep your login and name (so you can restore
    a backup into it). Needs your password, so it can't happen by one stray click."""
    from app.rag import note_cache

    if not auth_service.verify_password(payload.password, user.password_hash):
        raise WrongCurrentPasswordError()
    removed = cv_replace_service.empty_account(db, user)
    db.commit()
    note_cache.clear()
    return {"removed": removed}
