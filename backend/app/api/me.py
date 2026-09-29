"""Proof endpoint for the single-hardcoded-user bootstrap (see user_service, dependencies).

No service logic here beyond the dependency: get_current_user already resolved
(and, on first call, created) the user before this route runs.
"""

from fastapi import APIRouter, Depends

from app.core.models import UserResponse
from app.db.models import User
from app.dependencies import get_current_user

router = APIRouter(tags=["me"])


@router.get("/me", response_model=UserResponse)
def read_current_user(user: User = Depends(get_current_user)) -> User:
    return user
