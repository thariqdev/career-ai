"""Accounts (stage 97): sign up, log in, log out, and who is logged in. Stage 98 adds
forgot password (an emailed one-time link), resetting with that link, and changing the
password while logged in.

A successful sign-up or log-in sets the session cookie: HttpOnly (page scripts can't
read it, so an injected script can't steal it), SameSite=Lax (other sites can't send
it with their own form posts) and Secure (HTTPS only; off for local http dev). The
password never comes back in any reply. Errors (wrong password, email taken, weak
password, locked account) are domain errors mapped in errors.py.
"""

from fastapi import APIRouter, BackgroundTasks, Depends, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.models import UserResponse
from app.core.services import auth_service, mail_service, user_service
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


# --- stage 98: forgot / reset / change password ----------------------------------------

FORGOT_REPLY = "If an account exists for that email, we've sent a link to reset the password."


class ForgotPassword(BaseModel):
    email: str = Field(max_length=254)


class ResetPassword(BaseModel):
    token: str = Field(max_length=200)
    new_password: str = Field(max_length=auth_service.MAX_PASSWORD_CHARS)


class ChangePassword(BaseModel):
    current_password: str = Field(max_length=auth_service.MAX_PASSWORD_CHARS)
    new_password: str = Field(max_length=auth_service.MAX_PASSWORD_CHARS)


@router.post("/forgot-password", status_code=202)
def forgot_password(payload: ForgotPassword, background: BackgroundTasks, db: Session = Depends(get_db)) -> dict:
    """Always the same reply, and the email goes out after the reply (in the background),
    so neither the words nor the timing tell whether the account exists."""
    found = auth_service.request_reset(db, payload.email)
    db.commit()
    if found is not None:
        user, token = found
        link = f"{mail_service.app_url()}/reset-password?token={token}"
        subject, body = mail_service.reset_email(user.full_name, link, auth_service.RESET_MINUTES)
        background.add_task(mail_service.send_email, user.email, subject, body)
    return {"detail": FORGOT_REPLY}


@router.post("/reset-password", response_model=UserResponse)
def reset_password(payload: ResetPassword, response: Response, db: Session = Depends(get_db)) -> User:
    user = auth_service.reset_password(db, payload.token, payload.new_password)
    _start_session(db, user, response)  # logged out everywhere else, logged in here
    return user


@router.post("/change-password", response_model=UserResponse)
def change_password(
    payload: ChangePassword,
    response: Response,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> User:
    auth_service.change_password(db, user, payload.current_password, payload.new_password)
    _start_session(db, user, response)
    return user
