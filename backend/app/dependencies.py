from collections.abc import Generator

from fastapi import Depends
from sqlalchemy.orm import Session

from app.ai.client import RequirementExtractor
from app.ai.providers.stub_extractor import NoOpRequirementExtractor
from app.core.services import user_service
from app.db.models import User
from database import SessionLocal

# Holds no state, so one shared instance is fine. This is the single wiring point that
# changes when a real LLM-backed provider exists — swap what this returns, and every
# endpoint using Depends(get_requirement_extractor) picks it up with no other changes.
# Tests override this dependency with a fake extractor to exercise real accept/reject
# behavior over HTTP; production traffic gets the safe no-op placeholder until then.
_requirement_extractor = NoOpRequirementExtractor()


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


def get_requirement_extractor() -> RequirementExtractor:
    """The extractor endpoints use by default: the safe placeholder (see stub_extractor)."""
    return _requirement_extractor
