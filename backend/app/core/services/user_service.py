"""Bootstraps the single hardcoded user this system runs as.

There is no auth yet, and no user_id ever appears in a request (PROJECT_RULES.md /
HANDOFF.md decision). Every request needs SOME user to attach data to, so the system
runs as one fixed account instead. This is plumbing to make that account exist, not a
domain rule: it decides nothing about verification, taxonomy, or comparisons.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import User

# Fixed, not configurable: a deliberate single-user bootstrap, not multi-tenant auth.
DEFAULT_USER_EMAIL = "me@career-ai.local"


def get_or_create_default_user(db: Session) -> User:
    """Return the one User this system runs as, creating it on first use.

    Flushes first (autoflush=False) so a user created earlier in the same session is
    found rather than duplicated. Does not commit — same convention as every other
    service; the caller owns the transaction.
    """
    db.flush()

    user = db.scalar(select(User).where(User.email == DEFAULT_USER_EMAIL))
    if user is not None:
        return user

    user = User(email=DEFAULT_USER_EMAIL)
    db.add(user)
    db.flush()
    return user
