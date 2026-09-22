from collections.abc import Generator

from sqlalchemy.orm import Session

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
