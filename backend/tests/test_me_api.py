"""HTTP tests for GET /me.

Same TestClient + dependency_overrides[get_db] + StaticPool in-memory SQLite pattern
as test_skills_api.py.
"""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.services.user_service import DEFAULT_USER_EMAIL
from app.db.models import User
from app.dependencies import get_db
from app.main import app
from database import Base


@pytest.fixture()
def engine() -> Iterator[Engine]:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture()
def client(engine: Engine) -> Iterator[TestClient]:
    def override_get_db() -> Iterator[Session]:
        db = Session(engine, autoflush=False)
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def _user_count(engine: Engine) -> int:
    with Session(engine) as db:
        return db.scalar(select(func.count()).select_from(User))


def test_get_me_on_a_fresh_database_creates_the_default_user(
    client: TestClient, engine: Engine
) -> None:
    assert _user_count(engine) == 0

    response = client.get("/me")

    assert response.status_code == 200
    body = response.json()
    assert body["email"] == DEFAULT_USER_EMAIL
    assert body["full_name"] is None
    assert isinstance(body["id"], int)
    assert _user_count(engine) == 1


def test_get_me_twice_returns_the_same_user_and_creates_no_duplicate(
    client: TestClient, engine: Engine
) -> None:
    first = client.get("/me").json()
    second = client.get("/me").json()

    assert first["id"] == second["id"]
    assert first == second
    assert _user_count(engine) == 1
