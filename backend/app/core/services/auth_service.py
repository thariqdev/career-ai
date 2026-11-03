"""Accounts: sign up, log in, log out, and who a request belongs to (stage 97).

Passwords are never stored. scrypt (Python's built-in hashlib.scrypt, no extra
library) turns each one plus a random salt into a hash that is slow to compute on
purpose, so a stolen database can't be brute-forced quickly. Checking compares hashes
in constant time.

A login creates a SESSION: a long random token (secrets.token_urlsafe) that the browser
keeps in an HttpOnly cookie. Only the token's SHA-256 is stored, so the database alone
can't be used to log in. Sessions last SESSION_DAYS; logging out deletes the row.

Guessing is slowed down: after MAX_FAILED_LOGINS wrong passwords the account is locked
for LOCK_MINUTES. Unknown emails and wrong passwords get the same answer, and a dummy
hash is checked for unknown emails, so the reply doesn't reveal which emails exist.

Same conventions as the other services: flush, never commit (the route commits).
"""

import base64
import hashlib
import hmac
import re
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.exceptions import (
    AccountClaimError,
    AccountLockedError,
    EmailTakenError,
    InvalidCredentialsError,
    InvalidEmailError,
    InvalidResetLinkError,
    WeakPasswordError,
    WrongCurrentPasswordError,
)
from app.db.models import AuthSession, PasswordReset, User

SESSION_DAYS = 30
MAX_FAILED_LOGINS = 5
LOCK_MINUTES = 5
RESET_MINUTES = 30  # a forgot-password link works this long, once
MAX_RESETS_PER_HOUR = 3  # per account, so nobody can flood someone's inbox
MIN_PASSWORD_CHARS = 8
MAX_PASSWORD_CHARS = 128
# scrypt cost: n=2**14, r=8, p=1 (about 16 MB of memory and ~50 ms per check).
SCRYPT_N, SCRYPT_R, SCRYPT_P = 2**14, 8, 1
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(moment: datetime | None) -> datetime | None:
    """SQLite gives back naive datetimes; treat them as UTC."""
    return moment if moment is None or moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def normalize_email(email: str) -> str:
    return email.strip().lower()


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P, dklen=32)
    encode = lambda b: base64.b64encode(b).decode()  # noqa: E731
    return f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${encode(salt)}${encode(digest)}"


def verify_password(password: str, stored: str | None) -> bool:
    try:
        name, n, r, p, salt, digest = (stored or "").split("$")
        if name != "scrypt":
            return False
        expected = base64.b64decode(digest)
        actual = hashlib.scrypt(
            password.encode(), salt=base64.b64decode(salt), n=int(n), r=int(r), p=int(p), dklen=len(expected)
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, expected)


_DUMMY_HASH = hash_password("not-a-real-password")  # checked for unknown emails (same timing)


def check_new_password(password: str) -> None:
    if not MIN_PASSWORD_CHARS <= len(password) <= MAX_PASSWORD_CHARS:
        raise WeakPasswordError(MIN_PASSWORD_CHARS, MAX_PASSWORD_CHARS)


def find_user(db: Session, email: str) -> User | None:
    db.flush()
    return db.scalar(select(User).where(func.lower(User.email) == normalize_email(email)))


def sign_up(db: Session, email: str, password: str, full_name: str | None = None) -> User:
    clean = normalize_email(email)
    if not _EMAIL.match(clean):
        raise InvalidEmailError()
    check_new_password(password)
    if find_user(db, clean) is not None:
        raise EmailTakenError()
    name = (full_name or "").strip() or None
    user = User(email=clean, full_name=name, password_hash=hash_password(password))
    db.add(user)
    db.flush()
    return user


def log_in(db: Session, email: str, password: str) -> User:
    """The user for these credentials. Wrong ones raise InvalidCredentialsError (the same
    message for an unknown email), a locked account raises AccountLockedError."""
    user = find_user(db, email)
    if user is None or user.password_hash is None:
        verify_password(password, _DUMMY_HASH)
        raise InvalidCredentialsError()
    locked_until = _aware(user.locked_until)
    if locked_until is not None and locked_until > _now():
        raise AccountLockedError(LOCK_MINUTES)
    if not verify_password(password, user.password_hash):
        user.failed_logins += 1
        if user.failed_logins >= MAX_FAILED_LOGINS:
            user.failed_logins = 0
            user.locked_until = _now() + timedelta(minutes=LOCK_MINUTES)
        db.flush()
        raise InvalidCredentialsError()
    user.failed_logins = 0
    user.locked_until = None
    db.flush()
    return user


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_session(db: Session, user: User) -> str:
    """A new session for this user. Returns the token for the cookie (never stored)."""
    token = secrets.token_urlsafe(32)
    db.add(AuthSession(user_id=user.id, token_hash=_token_hash(token), expires_at=_now() + timedelta(days=SESSION_DAYS)))
    db.flush()
    return token


def user_for_token(db: Session, token: str | None) -> User | None:
    """Who this session token belongs to, or None (unknown or expired)."""
    if not token:
        return None
    session = db.scalar(select(AuthSession).where(AuthSession.token_hash == _token_hash(token)))
    if session is None:
        return None
    if _aware(session.expires_at) <= _now():
        db.delete(session)
        db.flush()
        return None
    return db.get(User, session.user_id)


def end_session(db: Session, token: str | None) -> None:
    if token:
        db.execute(delete(AuthSession).where(AuthSession.token_hash == _token_hash(token)))
        db.flush()


def end_all_sessions(db: Session, user: User) -> None:
    """Log this user out everywhere (used when the password changes, stage 98)."""
    db.execute(delete(AuthSession).where(AuthSession.user_id == user.id))
    db.flush()


# --- forgot password and change password (stage 98) -------------------------------------


def request_reset(db: Session, email: str) -> tuple[User, str] | None:
    """A new one-time reset link's token for this email, or None (no such account, or
    already MAX_RESETS_PER_HOUR links in the last hour). The caller replies the same way
    either way, so nobody can find out which emails have accounts."""
    user = find_user(db, email)
    if user is None:
        return None
    hour_ago = _now() - timedelta(hours=1)
    recent = [
        moment for moment in db.scalars(select(PasswordReset.created_at).where(PasswordReset.user_id == user.id))
        if _aware(moment) > hour_ago
    ]
    if len(recent) >= MAX_RESETS_PER_HOUR:
        return None
    token = secrets.token_urlsafe(32)
    db.add(PasswordReset(user_id=user.id, token_hash=_token_hash(token), created_at=_now(),
                         expires_at=_now() + timedelta(minutes=RESET_MINUTES)))
    db.flush()
    return user, token


def _set_password(db: Session, user: User, new_password: str) -> None:
    check_new_password(new_password)
    user.password_hash = hash_password(new_password)
    user.failed_logins = 0
    user.locked_until = None
    end_all_sessions(db, user)  # every other device is logged out


def reset_password(db: Session, token: str, new_password: str) -> User:
    """Use a reset link: set the new password, log out everywhere. Raises
    InvalidResetLinkError for an unknown, used or expired link (nothing changes)."""
    reset = db.scalar(select(PasswordReset).where(PasswordReset.token_hash == _token_hash(token or "")))
    if reset is None or reset.used_at is not None or _aware(reset.expires_at) <= _now():
        raise InvalidResetLinkError()
    user = db.get(User, reset.user_id)
    _set_password(db, user, new_password)
    for open_link in db.scalars(
        select(PasswordReset).where(PasswordReset.user_id == user.id, PasswordReset.used_at.is_(None))
    ):
        open_link.used_at = _now()  # this link, and any other unused one, can't be used again
    db.flush()
    return user


def change_password(db: Session, user: User, current_password: str, new_password: str) -> None:
    """While logged in: needs the current password. Logs out every session (the caller
    starts a fresh one for this browser)."""
    if not verify_password(current_password, user.password_hash):
        raise WrongCurrentPasswordError()
    _set_password(db, user, new_password)
    db.flush()


# --- claiming the old built-in user (stage 100) -------------------------------------------


def claim_built_in_user(db: Session, email: str, password: str, full_name: str | None = None) -> User:
    """Turn the pre-accounts built-in user (me@career-ai.local, no password) into a real
    account: your email and password, all its data kept. Refuses when there's nothing to
    claim, when it already has a password, or when the email belongs to another account."""
    from app.core.services.user_service import DEFAULT_USER_EMAIL

    user = find_user(db, DEFAULT_USER_EMAIL)
    if user is None:
        raise AccountClaimError("There's no built-in user to claim (it was claimed already, or never created).")
    if user.password_hash is not None:
        raise AccountClaimError("The built-in user already has a password: log in instead.")
    clean = normalize_email(email)
    if not _EMAIL.match(clean):
        raise InvalidEmailError()
    other = find_user(db, clean)
    if other is not None and other.id != user.id:
        raise EmailTakenError()
    check_new_password(password)
    user.email = clean
    user.password_hash = hash_password(password)
    if full_name and full_name.strip():
        user.full_name = full_name.strip()
    db.flush()
    return user
