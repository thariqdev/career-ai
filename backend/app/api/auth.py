"""Accounts (stage 97): sign up, log in, log out, and who is logged in.

A successful sign-up or log-in sets the session cookie: HttpOnly (page scripts can't
read it, so an injected script can't steal it), SameSite=Lax (other sites can't send
it with their own form posts) and Secure (HTTPS only; off for local http dev). The
password never comes back in any reply. Errors (wrong password, email taken, weak
password, locked account) are domain errors mapped in errors.py.
"""

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.models import UserResponse
from app.core.services import auth_service, user_service
from app.db.models import User
from app.dependencies import SESSION_COOKIE, get_current_user, get_db, session_cookie_secure

router = APIRouter(prefix="/auth", tags=["auth"])


class SignUp(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(max_length=auth_service.MAX_PASSWORD_CHARS)
    full_name: str | None = Field(default=None, max_length=user_service.MAX_NAME_CHARS)


class LogIn(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(max_length=auth_service.MAX_PASSWORD_CHARS)


def _start_session(db: Session, user: User, response: Response) -> None:
    token = auth_service.create_session(db, user)
    db.commit()
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=auth_service.SESSION_DAYS * 24 * 3600,
        httponly=True,
        samesite="lax",
        secure=session_cookie_secure(),
        path="/",
    )


@router.post("/signup", response_model=UserResponse, status_code=201)
def sign_up(payload: SignUp, response: Response, db: Session = Depends(get_db)) -> User:
    user = auth_service.sign_up(db, payload.email, payload.password, payload.full_name)
    _start_session(db, user, response)
    return user


@router.post("/login", response_model=UserResponse)
def log_in(payload: LogIn, response: Response, db: Session = Depends(get_db)) -> User:
    try:
        user = auth_service.log_in(db, payload.email, payload.password)
    finally:
        db.commit()  # keep the failed-login count even when the login is refused
    _start_session(db, user, response)
    return user


@router.post("/logout", status_code=204)
def log_out(request: Request, db: Session = Depends(get_db)) -> Response:
    auth_service.end_session(db, request.cookies.get(SESSION_COOKIE))
    db.commit()
    response = Response(status_code=204)
    response.delete_cookie(SESSION_COOKIE, path="/", httponly=True, samesite="lax", secure=session_cookie_secure())
    return response


@router.get("/me", response_model=UserResponse)
def who_am_i(user: User = Depends(get_current_user)) -> User:
    return user
