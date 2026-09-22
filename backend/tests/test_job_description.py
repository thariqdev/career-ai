"""Relationship check for JobDescription.

Uses an in-memory SQLite database, same approach as the other model tests.
No extraction/parsing logic exists yet — this only confirms the raw-capture
record is wired to User correctly.
"""

from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.models import JobDescription, User
from database import Base


@pytest.fixture()
def session() -> Iterator[Session]:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        yield db
    engine.dispose()


def test_job_description_is_stored_verbatim_and_linked_to_user(session: Session) -> None:
    user = User(email="dev@example.com")
    posting = JobDescription(
        user=user,
        title="Senior Backend Engineer",
        company="Acme Corp",
        raw_text="We are looking for a backend engineer with Python and PostgreSQL experience.",
    )

    session.add_all([user, posting])
    session.commit()

    assert posting in user.job_descriptions
    assert posting.user is user
    assert posting.raw_text.startswith("We are looking for")
