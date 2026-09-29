"""Tests for user_service (the single-hardcoded-user bootstrap).

Uses a real on-disk SQLite file rather than :memory: for the cross-session test,
since two separate in-memory SQLite connections are two separate databases.
"""

from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.core.services.user_service import DEFAULT_USER_EMAIL, get_or_create_default_user
from app.db.models import User
from database import Base


@pytest.fixture()
def session() -> Iterator[Session]:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine, autoflush=False) as db:
        yield db
    engine.dispose()


def test_creates_the_user_on_first_call(session: Session) -> None:
    user = get_or_create_default_user(session)

    assert user.email == DEFAULT_USER_EMAIL
    assert user.id is not None
    assert session.scalar(select(func.count()).select_from(User)) == 1


def test_finds_a_pending_unflushed_user_instead_of_duplicating_it(session: Session) -> None:
    """The scenario the pre-lookup flush exists for: something else in the same
    session already added (but not yet flushed) the default user before this
    function's own SELECT runs. Without flushing first, the SELECT would miss it
    and the later INSERT would collide with the unique email constraint.
    """
    pending = User(email=DEFAULT_USER_EMAIL)
    session.add(pending)  # deliberately not flushed

    user = get_or_create_default_user(session)

    assert user is pending
    assert session.scalar(select(func.count()).select_from(User)) == 1


def test_calling_it_twice_in_the_same_session_returns_the_same_row(session: Session) -> None:
    first = get_or_create_default_user(session)
    second = get_or_create_default_user(session)

    assert second is first
    assert second.id == first.id
    assert session.scalar(select(func.count()).select_from(User)) == 1


def test_two_different_sessions_against_the_same_database_find_the_same_row(
    tmp_path,
) -> None:
    """Proves the lookup goes through the database, not in-session object identity."""
    db_path = tmp_path / "user_bootstrap.sqlite3"
    engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)

    with Session(engine, autoflush=False) as first_session:
        first_user = get_or_create_default_user(first_session)
        first_session.commit()
        first_id = first_user.id

    with Session(engine, autoflush=False) as second_session:
        second_user = get_or_create_default_user(second_session)
        assert second_user.id == first_id
        assert second_session.scalar(select(func.count()).select_from(User)) == 1

    engine.dispose()
