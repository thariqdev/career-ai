"""HTTP tests for the skills endpoints.

FastAPI's TestClient runs the app in another thread, so the in-memory SQLite database
needs StaticPool + check_same_thread=False to be one shared database. Each request gets
a Session(autoflush=False), matching SessionLocal, and the get_db override is cleared
after every test.
"""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.exceptions import SkillNameCollisionError
from app.db.models import Skill, SkillAlias
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


def _counts(engine: Engine) -> tuple[int, int]:
    with Session(engine) as db:
        return (
            db.scalar(select(func.count()).select_from(Skill)),
            db.scalar(select(func.count()).select_from(SkillAlias)),
        )


def _create(client: TestClient, name: str, category: str | None = None) -> dict:
    response = client.post("/skills", json={"name": name, "category": category})
    assert response.status_code == 201, response.text
    return response.json()


# --- POST /skills ------------------------------------------------------------


def test_create_skill_returns_201_and_is_persisted(client: TestClient) -> None:
    response = client.post("/skills", json={"name": "  PostgreSQL ", "category": "Database"})

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "PostgreSQL"
    assert body["category"] == "Database"
    assert body["aliases"] == []
    assert isinstance(body["id"], int)
    assert client.get("/skills").json() == [body]


def test_create_skill_with_blank_name_is_422_and_creates_nothing(
    client: TestClient, engine: Engine
) -> None:
    response = client.post("/skills", json={"name": "   "})

    assert response.status_code == 422
    assert "blank" in response.json()["detail"].lower()
    assert _counts(engine) == (0, 0)


def test_create_skill_colliding_in_a_different_case_is_409(
    client: TestClient, engine: Engine
) -> None:
    _create(client, "PostgreSQL")

    response = client.post("/skills", json={"name": "postgresql"})

    assert response.status_code == 409
    assert "PostgreSQL" in response.json()["detail"]
    assert _counts(engine) == (1, 0)


@pytest.mark.parametrize("body", [{}, {"name": 123}, {"name": None}, {"category": "x"}])
def test_create_skill_with_bad_body_is_422_from_fastapi_validation(
    client: TestClient, engine: Engine, body: dict
) -> None:
    response = client.post("/skills", json=body)

    assert response.status_code == 422
    assert isinstance(response.json()["detail"], list)  # FastAPI's own validation shape
    assert _counts(engine) == (0, 0)


# --- POST /skills/{id}/aliases -----------------------------------------------


def test_add_alias_returns_201_then_resolve_finds_the_skill(client: TestClient) -> None:
    skill = _create(client, "PostgreSQL")

    response = client.post(f"/skills/{skill['id']}/aliases", json={"alias": " Postgres "})

    assert response.status_code == 201
    assert response.json()["id"] == skill["id"]
    assert response.json()["aliases"] == ["Postgres"]
    resolved = client.get("/skills/resolve", params={"text": "postgres"})
    assert resolved.status_code == 200
    assert resolved.json()["id"] == skill["id"]


def test_alias_colliding_with_another_skills_name_is_409(
    client: TestClient, engine: Engine
) -> None:
    _create(client, "PostgreSQL")
    mysql = _create(client, "MySQL")

    response = client.post(f"/skills/{mysql['id']}/aliases", json={"alias": "postgresql"})

    assert response.status_code == 409
    assert _counts(engine) == (2, 0)


def test_alias_on_a_nonexistent_skill_is_404(client: TestClient, engine: Engine) -> None:
    response = client.post("/skills/999/aliases", json={"alias": "Anything"})

    assert response.status_code == 404
    assert "999" in response.json()["detail"]
    assert _counts(engine) == (0, 0)


def test_blank_alias_is_422(client: TestClient) -> None:
    skill = _create(client, "PostgreSQL")

    response = client.post(f"/skills/{skill['id']}/aliases", json={"alias": "  "})

    assert response.status_code == 422


# --- GET /skills/resolve -----------------------------------------------------


def test_resolve_unknown_text_is_404_and_invents_nothing(
    client: TestClient, engine: Engine
) -> None:
    _create(client, "PostgreSQL")
    before = _counts(engine)

    response = client.get("/skills/resolve", params={"text": "Zorblax"})

    assert response.status_code == 404
    assert "detail" in response.json()
    assert _counts(engine) == before


def test_resolve_is_case_and_whitespace_insensitive(client: TestClient) -> None:
    skill = _create(client, "PostgreSQL")

    response = client.get("/skills/resolve", params={"text": "  POSTGRESQL "})

    assert response.status_code == 200
    assert response.json()["id"] == skill["id"]


def test_resolve_without_text_is_422(client: TestClient) -> None:
    assert client.get("/skills/resolve").status_code == 422


def test_resolve_ambiguous_data_is_409(client: TestClient, engine: Engine) -> None:
    """Bypass the service to create the bad data the DB itself does not forbid."""
    with Session(engine) as db:
        first, second = Skill(name="React.js"), Skill(name="React Native")
        db.add_all(
            [first, second, SkillAlias(skill=first, alias="React"), SkillAlias(skill=second, alias="react")]
        )
        db.commit()

    response = client.get("/skills/resolve", params={"text": "React"})

    assert response.status_code == 409
    assert "ambiguous" in response.json()["detail"].lower()


# --- GET /skills, transactions ----------------------------------------------


def test_list_skills_is_ordered_by_name(client: TestClient) -> None:
    for name in ["Python", "Docker", "PostgreSQL"]:
        _create(client, name)

    names = [skill["name"] for skill in client.get("/skills").json()]

    assert names == ["Docker", "PostgreSQL", "Python"]


def test_failed_write_leaves_no_partial_data(
    client: TestClient, engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If the service flushes a row and THEN raises, the route never commits: rolled back."""
    from app.api import skills as skills_api

    def flush_then_fail(db: Session, name: str, category: str | None = None) -> Skill:
        db.add(Skill(name="Ghost"))
        db.flush()
        raise SkillNameCollisionError(name, "Ghost")

    monkeypatch.setattr(skills_api.skill_service, "create_skill", flush_then_fail)

    response = client.post("/skills", json={"name": "Whatever"})

    assert response.status_code == 409
    assert _counts(engine) == (0, 0)


def test_unmapped_domain_error_subclass_falls_back_to_400() -> None:
    from app.api.errors import _status_for
    from app.core.exceptions import (
        DomainError,
        EvidenceAlreadyLinkedError,
        InsufficientEvidenceError,
        RequirementsAlreadyExistError,
    )

    class SomethingNew(DomainError):
        pass

    assert _status_for(SomethingNew("x")) == 400
    assert _status_for(InsufficientEvidenceError(1, "VERIFIED")) == 409
    assert _status_for(EvidenceAlreadyLinkedError(1, 2)) == 409
    assert _status_for(RequirementsAlreadyExistError(1)) == 409


def test_openapi_docs_still_generate(client: TestClient) -> None:
    schema = client.get("/openapi.json")

    assert schema.status_code == 200
    paths = schema.json()["paths"]
    assert {"/health", "/skills", "/skills/resolve", "/skills/{skill_id}/aliases"} <= set(paths)
    assert client.get("/docs").status_code == 200
