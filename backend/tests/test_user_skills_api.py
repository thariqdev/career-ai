"""HTTP tests for the /user-skills endpoints.

Same TestClient + dependency_overrides[get_db] + StaticPool in-memory SQLite pattern
as test_skills_api.py.
"""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.services import skill_service
from app.db.models import Evidence, Skill, User, UserSkill
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


def _create_skill(engine: Engine, name: str) -> int:
    with _session(engine) as db:
        skill = skill_service.create_skill(db, name)
        db.commit()
        return skill.id


def _count(engine: Engine, model: type) -> int:
    with _session(engine) as db:
        return db.scalar(select(func.count()).select_from(model))


# --- claim a skill ------------------------------------------------------------


def test_claim_skill_returns_201_and_appears_in_list(client: TestClient, engine: Engine) -> None:
    skill_id = _create_skill(engine, "Python")

    response = client.post("/user-skills", json={"skill_id": skill_id})

    assert response.status_code == 201
    body = response.json()
    assert body["skill_id"] == skill_id
    assert body["skill_name"] == "Python"
    assert body["status"] == "provisional"
    assert body["notes"] is None
    assert isinstance(body["id"], int)

    listed = client.get("/user-skills")
    assert listed.status_code == 200
    assert listed.json() == [body]


def test_claim_an_unknown_skill_is_404(client: TestClient, engine: Engine) -> None:
    response = client.post("/user-skills", json={"skill_id": 999})

    assert response.status_code == 404
    assert _count(engine, UserSkill) == 0


def test_claiming_the_same_skill_twice_is_409_and_only_one_row_exists(
    client: TestClient, engine: Engine
) -> None:
    skill_id = _create_skill(engine, "Python")
    first = client.post("/user-skills", json={"skill_id": skill_id})
    assert first.status_code == 201

    second = client.post("/user-skills", json={"skill_id": skill_id})

    assert second.status_code == 409
    assert _count(engine, UserSkill) == 1


def test_list_is_ordered_by_skill_name(client: TestClient, engine: Engine) -> None:
    for name in ["Python", "Docker", "PostgreSQL"]:
        client.post("/user-skills", json={"skill_id": _create_skill(engine, name)})

    names = [item["skill_name"] for item in client.get("/user-skills").json()]

    assert names == ["Docker", "PostgreSQL", "Python"]


# --- link evidence --------------------------------------------------------------


def test_link_evidence_returns_201_and_is_visible_on_the_claim(
    client: TestClient, engine: Engine
) -> None:
    skill_id = _create_skill(engine, "Python")
    user_skill_id = client.post("/user-skills", json={"skill_id": skill_id}).json()["id"]
    evidence_id = client.post(
        "/evidence", json={"evidence_type": "project", "title": "FundsApp repo"}
    ).json()["id"]

    response = client.post(
        f"/user-skills/{user_skill_id}/evidence-links", json={"evidence_id": evidence_id}
    )

    assert response.status_code == 201
    assert response.json()["id"] == user_skill_id
    with _session(engine) as db:
        user_skill = db.get(UserSkill, user_skill_id)
        assert [link.evidence_id for link in user_skill.evidence_links] == [evidence_id]


def test_linking_the_same_evidence_twice_is_409(client: TestClient, engine: Engine) -> None:
    skill_id = _create_skill(engine, "Python")
    user_skill_id = client.post("/user-skills", json={"skill_id": skill_id}).json()["id"]
    evidence_id = client.post(
        "/evidence", json={"evidence_type": "project", "title": "repo"}
    ).json()["id"]
    client.post(f"/user-skills/{user_skill_id}/evidence-links", json={"evidence_id": evidence_id})

    response = client.post(
        f"/user-skills/{user_skill_id}/evidence-links", json={"evidence_id": evidence_id}
    )

    assert response.status_code == 409


def test_linking_evidence_owned_by_another_user_is_409(client: TestClient, engine: Engine) -> None:
    skill_id = _create_skill(engine, "Python")
    user_skill_id = client.post("/user-skills", json={"skill_id": skill_id}).json()["id"]
    with _session(engine) as db:
        other_user = User(email="other@example.com")
        foreign_evidence = Evidence(user=other_user, evidence_type=EvidenceType.PROJECT, title="not yours")
        db.add_all([other_user, foreign_evidence])
        db.commit()
        foreign_evidence_id = foreign_evidence.id

    response = client.post(
        f"/user-skills/{user_skill_id}/evidence-links", json={"evidence_id": foreign_evidence_id}
    )

    assert response.status_code == 409


def test_linking_to_a_nonexistent_or_not_owned_user_skill_is_404(
    client: TestClient, engine: Engine
) -> None:
    evidence_id = client.post(
        "/evidence", json={"evidence_type": "project", "title": "repo"}
    ).json()["id"]

    assert (
        client.post("/user-skills/999/evidence-links", json={"evidence_id": evidence_id}).status_code
        == 404
    )

    with _session(engine) as db:
        other_user = User(email="other@example.com")
        other_skill = Skill(name="Rust")
        other_user_skill = UserSkill(user=other_user, skill=other_skill)
        db.add_all([other_user, other_skill, other_user_skill])
        db.commit()
        other_user_skill_id = other_user_skill.id

    response = client.post(
        f"/user-skills/{other_user_skill_id}/evidence-links", json={"evidence_id": evidence_id}
    )
    assert response.status_code == 404


def test_linking_nonexistent_evidence_is_404(client: TestClient, engine: Engine) -> None:
    skill_id = _create_skill(engine, "Python")
    user_skill_id = client.post("/user-skills", json={"skill_id": skill_id}).json()["id"]

    response = client.post(
        f"/user-skills/{user_skill_id}/evidence-links", json={"evidence_id": 999}
    )

    assert response.status_code == 404


# --- status updates --------------------------------------------------------------


def test_verified_with_no_evidence_is_409_and_status_unchanged(
    client: TestClient, engine: Engine
) -> None:
    skill_id = _create_skill(engine, "Python")
    user_skill_id = client.post("/user-skills", json={"skill_id": skill_id}).json()["id"]

    response = client.post(f"/user-skills/{user_skill_id}/status", json={"status": "verified"})

    assert response.status_code == 409
    with _session(engine) as db:
        assert db.get(UserSkill, user_skill_id).status.value == "provisional"


def test_link_evidence_then_verify_succeeds(client: TestClient, engine: Engine) -> None:
    skill_id = _create_skill(engine, "Python")
    user_skill_id = client.post("/user-skills", json={"skill_id": skill_id}).json()["id"]
    evidence_id = client.post(
        "/evidence", json={"evidence_type": "project", "title": "FundsApp repo"}
    ).json()["id"]
    client.post(f"/user-skills/{user_skill_id}/evidence-links", json={"evidence_id": evidence_id})

    response = client.post(f"/user-skills/{user_skill_id}/status", json={"status": "verified"})

    assert response.status_code == 200
    assert response.json()["status"] == "verified"


def test_downgrade_to_provisional_always_succeeds(client: TestClient, engine: Engine) -> None:
    skill_id = _create_skill(engine, "Python")
    user_skill_id = client.post("/user-skills", json={"skill_id": skill_id}).json()["id"]
    evidence_id = client.post(
        "/evidence", json={"evidence_type": "project", "title": "repo"}
    ).json()["id"]
    client.post(f"/user-skills/{user_skill_id}/evidence-links", json={"evidence_id": evidence_id})
    client.post(f"/user-skills/{user_skill_id}/status", json={"status": "verified"})

    response = client.post(f"/user-skills/{user_skill_id}/status", json={"status": "provisional"})

    assert response.status_code == 200
    assert response.json()["status"] == "provisional"


def test_status_update_with_bad_value_is_422(client: TestClient, engine: Engine) -> None:
    skill_id = _create_skill(engine, "Python")
    user_skill_id = client.post("/user-skills", json={"skill_id": skill_id}).json()["id"]

    response = client.post(f"/user-skills/{user_skill_id}/status", json={"status": "not_a_status"})

    assert response.status_code == 422


def test_status_update_on_a_nonexistent_or_not_owned_user_skill_is_404(
    client: TestClient, engine: Engine
) -> None:
    assert client.post("/user-skills/999/status", json={"status": "provisional"}).status_code == 404

    with _session(engine) as db:
        other_user = User(email="other@example.com")
        other_skill = Skill(name="Rust")
        other_user_skill = UserSkill(user=other_user, skill=other_skill)
        db.add_all([other_user, other_skill, other_user_skill])
        db.commit()
        other_user_skill_id = other_user_skill.id

    response = client.post(
        f"/user-skills/{other_user_skill_id}/status", json={"status": "provisional"}
    )
    assert response.status_code == 404


# --- docs -------------------------------------------------------------------------


def test_openapi_includes_user_skill_paths(client: TestClient) -> None:
    schema = client.get("/openapi.json")

    assert schema.status_code == 200
    paths = set(schema.json()["paths"])
    assert {
        "/user-skills",
        "/user-skills/{user_skill_id}/evidence-links",
        "/user-skills/{user_skill_id}/status",
    } <= paths
    assert client.get("/docs").status_code == 200
