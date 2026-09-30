import os
from collections.abc import Generator

from fastapi import Depends
from sqlalchemy.orm import Session

from app.ai.client import RequirementExtractor
from app.ai.providers.claude_extractor import ClaudeRequirementExtractor
from app.ai.providers.skill_list_extractor import SkillListExtractor
from app.core.services import skill_service, user_service
from app.db.models import User
from database import SessionLocal


def get_db() -> Generator[Session, None, None]:
    """Create and yield a SQLAlchemy Session for a single request.

    The session is created when the request starts and is always closed
    when the request finishes, even if an exception is raised.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_current_user(db: Session = Depends(get_db)) -> User:
    """Resolve the single hardcoded user this system runs as (see user_service).

    Unlike a service, this DOES commit. Services flush but never commit because a
    route owns the transaction — but this dependency runs BEFORE the route body, so
    the user must already be durably in the database before the route's own service
    calls (which may reference user_id) and its own commit run. It is a narrow,
    deliberate exception to "services don't commit, routes do", not a new pattern:
    it exists to guarantee the user exists, nothing else.
    """
    user = user_service.get_or_create_default_user(db)
    db.commit()
    return user


def get_requirement_extractor(db: Session = Depends(get_db)) -> RequirementExtractor:
    """Claude if ANTHROPIC_API_KEY is set, otherwise the deterministic skill-list matcher.

    The single wiring point for extraction. ClaudeRequirementExtractor() never touches
    the network at construction time (see its docstring). The matcher gets a snapshot
    of skill names/aliases as plain strings and never holds the Session itself; with no
    skills saved it proposes nothing. FastAPI caches get_db per request, so this reads
    through the same Session the route uses.
    """
    if os.getenv("ANTHROPIC_API_KEY"):
        return ClaudeRequirementExtractor()
    return SkillListExtractor(skill_service.skill_terms(db))
