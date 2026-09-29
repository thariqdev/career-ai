"""HTTP tests for /skills/{skill_id}/cv-presence and /skills/{skill_id}/cv-status.

Same TestClient + dependency_overrides[get_db] + StaticPool in-memory SQLite pattern as
test_skills_api.py. Kept as its own file, same reasoning as test_user_skills_api.py and
test_evidence_api.py being split out already: a cohesive feature area, and keeps
test_skills_api.py from growing indefinitely.
"""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.services import skill_service, verification_service
from app.core.services.user_service import DEFAULT_USER_EMAIL
from app.db.models import CVSkillPresence, Evidence, User, UserSkill
from app.db.models.enums import EvidenceType, VerificationStatus
from app.dependencies import get_db
from app.main import app
from database import Base


def _bootstrapped_user(client: TestClient, db: Session) -> User:
    """GET /me bootstraps the single hardcoded user; fetch that same row by email
    rather than creating an unrelated User, so combined_status() looks up the
    right (user, skill) pair when the route later resolves get_current_user."""
    client.get("/me")
    return db.scalar(select(User).where(User.email == DEFAULT_USER_EMAIL))


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


def _presence_count(engine: Engine) -> int:
    with _session(engine) as db:
        return db.scalar(select(func.count()).select_from(CVSkillPresence))


# --- PATCH cv-presence -----------------------------------------------------------


def test_patch_creates_a_new_row_when_none_exists(client: TestClient, engine: Engine) -> None:
    skill_id = _create_skill(engine, "Docker")

    response = client.patch(f"/skills/{skill_id}/cv-presence", json={"present": True})

    assert response.status_code == 200
    body = response.json()
    assert body["skill_id"] == skill_id
    assert body["skill_name"] == "Docker"
    assert body["present"] is True
    assert _presence_count(engine) == 1


def test_patch_again_updates_the_existing_row_instead_of_creating_a_second(
    client: TestClient, engine: Engine
) -> None:
    skill_id = _create_skill(engine, "Docker")
    first = client.patch(f"/skills/{skill_id}/cv-presence", json={"present": True})
    assert first.json()["present"] is True

    second = client.patch(f"/skills/{skill_id}/cv-presence", json={"present": False})

    assert second.status_code == 200
    assert second.json()["present"] is False
    assert _presence_count(engine) == 1
    with _session(engine) as db:
        [row] = db.scalars(select(CVSkillPresence)).all()
        assert row.present is False


def test_patch_on_a_nonexistent_skill_is_404_and_creates_nothing(
    client: TestClient, engine: Engine
) -> None:
    response = client.patch("/skills/999/cv-presence", json={"present": True})

    assert response.status_code == 404
    assert _presence_count(engine) == 0


# --- GET cv-status -----------------------------------------------------------------


def test_cv_status_with_no_claim_and_no_presence(client: TestClient, engine: Engine) -> None:
    skill_id = _create_skill(engine, "Docker")

    response = client.get(f"/skills/{skill_id}/cv-status")

    assert response.status_code == 200
    body = response.json()
    assert body["skill_id"] == skill_id
    assert body["knowledge_status"] is None
    assert body["cv_status"] == "not_present"
    assert body["recommendation"] is None


def test_cv_status_after_patching_present_with_no_claim_warns(
    client: TestClient, engine: Engine
) -> None:
    skill_id = _create_skill(engine, "Docker")
    client.patch(f"/skills/{skill_id}/cv-presence", json={"present": True})

    response = client.get(f"/skills/{skill_id}/cv-status")

    assert response.status_code == 200
    body = response.json()
    assert body["cv_status"] == "present"
    assert "without verified evidence" in body["recommendation"]


def test_cv_status_for_verified_skill_missing_from_cv_suggests_adding_it(
    client: TestClient, engine: Engine
) -> None:
    skill_id = _create_skill(engine, "Docker")
    with _session(engine) as db:
        # Build the VERIFIED claim directly via verification_service, same as other test files.
        skill = skill_service.get_skill(db, skill_id)
        user = _bootstrapped_user(client, db)
        user_skill = UserSkill(user=user, skill=skill)
        db.add(user_skill)
        db.flush()
        evidence = Evidence(user=user, evidence_type=EvidenceType.PROJECT, title="repo")
        db.add(evidence)
        db.flush()
        verification_service.link_evidence(db, user_skill, evidence)
        verification_service.set_status(db, user_skill, VerificationStatus.VERIFIED)
        db.commit()

    response = client.get(f"/skills/{skill_id}/cv-status")

    assert response.status_code == 200
    body = response.json()
    assert body["knowledge_status"] == "verified"
    assert body["cv_status"] == "missing_from_cv"
    assert "Consider adding" in body["recommendation"]


def test_cv_status_for_verified_skill_present_on_cv_has_no_recommendation(
    client: TestClient, engine: Engine
) -> None:
    skill_id = _create_skill(engine, "Docker")
    with _session(engine) as db:
        skill = skill_service.get_skill(db, skill_id)
        user = _bootstrapped_user(client, db)
        user_skill = UserSkill(user=user, skill=skill)
        db.add(user_skill)
        db.flush()
        evidence = Evidence(user=user, evidence_type=EvidenceType.PROJECT, title="repo")
        db.add(evidence)
        db.flush()
        verification_service.link_evidence(db, user_skill, evidence)
        verification_service.set_status(db, user_skill, VerificationStatus.VERIFIED)
        db.commit()

    client.patch(f"/skills/{skill_id}/cv-presence", json={"present": True})
    response = client.get(f"/skills/{skill_id}/cv-status")

    assert response.status_code == 200
    body = response.json()
    assert body["knowledge_status"] == "verified"
    assert body["cv_status"] == "present"
    assert body["recommendation"] is None


def test_cv_status_on_a_nonexistent_skill_is_404(client: TestClient) -> None:
    response = client.get("/skills/999/cv-status")

    assert response.status_code == 404


def test_openapi_includes_both_new_paths(client: TestClient) -> None:
    schema = client.get("/openapi.json")

    assert schema.status_code == 200
    paths = set(schema.json()["paths"])
    assert {"/skills/{skill_id}/cv-presence", "/skills/{skill_id}/cv-status"} <= paths
    assert client.get("/docs").status_code == 200
