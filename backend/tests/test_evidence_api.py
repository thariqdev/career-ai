"""HTTP tests for the /evidence endpoints.

Same TestClient + dependency_overrides[get_db] + StaticPool in-memory SQLite pattern
as test_skills_api.py.
"""

from collections.abc import Iterator
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.models import Education, Evidence, User, WorkExperience
from app.db.models.enums import EvidenceType
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


def _session(engine: Engine) -> Session:
    return Session(engine, autoflush=False)


def test_create_evidence_persists_and_appears_in_list(client: TestClient) -> None:
    response = client.post(
        "/evidence",
        json={"evidence_type": "project", "title": "FundsApp repo", "url": "https://example.com"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["evidence_type"] == "project"
    assert body["title"] == "FundsApp repo"
    assert body["url"] == "https://example.com"
    assert body["description"] is None
    assert isinstance(body["id"], int)

    listed = client.get("/evidence")
    assert listed.status_code == 200
    assert listed.json() == [body]


def test_create_evidence_with_bad_evidence_type_is_422(client: TestClient) -> None:
    response = client.post("/evidence", json={"evidence_type": "not_a_real_type", "title": "x"})

    assert response.status_code == 422


def test_create_evidence_referencing_a_nonexistent_work_experience_is_404(
    client: TestClient,
) -> None:
    response = client.post(
        "/evidence",
        json={"evidence_type": "work_experience", "title": "x", "work_experience_id": 999},
    )

    assert response.status_code == 404
    assert "999" in response.json()["detail"]


def test_create_evidence_referencing_another_users_work_experience_is_404(
    client: TestClient, engine: Engine
) -> None:
    """Bypass the API to create a work experience owned by a different user."""
    with _session(engine) as db:
        other_user = User(email="other@example.com")
        other_work = WorkExperience(
            user=other_user, company="Acme", role="Engineer", start_date=date(2020, 1, 1)
        )
        db.add_all([other_user, other_work])
        db.commit()
        other_work_id = other_work.id

    response = client.post(
        "/evidence",
        json={
            "evidence_type": "work_experience",
            "title": "x",
            "work_experience_id": other_work_id,
        },
    )

    assert response.status_code == 404


def test_create_evidence_referencing_another_users_education_is_404(
    client: TestClient, engine: Engine
) -> None:
    with _session(engine) as db:
        other_user = User(email="other@example.com")
        other_education = Education(user=other_user, institution="State University")
        db.add_all([other_user, other_education])
        db.commit()
        other_education_id = other_education.id

    response = client.post(
        "/evidence",
        json={"evidence_type": "certification", "title": "x", "education_id": other_education_id},
    )

    assert response.status_code == 404


def test_list_evidence_only_returns_the_current_users_evidence(
    client: TestClient, engine: Engine
) -> None:
    client.post("/evidence", json={"evidence_type": "other", "title": "mine"})
    with _session(engine) as db:
        other_user = User(email="other@example.com")
        other_evidence = Evidence(user=other_user, evidence_type=EvidenceType.OTHER, title="not mine")
        db.add_all([other_user, other_evidence])
        db.commit()

    listed = client.get("/evidence").json()

    assert [item["title"] for item in listed] == ["mine"]


def test_list_evidence_is_ordered_by_created_at(client: TestClient) -> None:
    for title in ["first", "second", "third"]:
        client.post("/evidence", json={"evidence_type": "other", "title": title})

    listed = client.get("/evidence").json()

    assert [item["title"] for item in listed] == ["first", "second", "third"]


def test_openapi_includes_evidence_paths(client: TestClient) -> None:
    schema = client.get("/openapi.json")

    assert schema.status_code == 200
    assert {"/evidence"} <= set(schema.json()["paths"])
    assert client.get("/docs").status_code == 200
