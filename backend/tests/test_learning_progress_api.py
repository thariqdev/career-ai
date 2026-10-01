"""HTTP tests for learning progress, including the rule that it never affects verification.

Same TestClient + dependency_overrides[get_db] + StaticPool in-memory SQLite pattern
as test_user_skills_api.py.
"""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.services import skill_service
from app.db.models import LearningProgress, Skill, User, UserSkill
from app.db.models.enums import LearningStatus
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


def _create_skill(engine: Engine, name: str) -> int:
    with Session(engine, autoflush=False) as db:
        skill = skill_service.create_skill(db, name)
        db.commit()
        return skill.id


def _count(engine: Engine, model: type) -> int:
    with Session(engine, autoflush=False) as db:
        return db.scalar(select(func.count()).select_from(model))


def _set(client: TestClient, skill_id: int, status: str):
    return client.put(f"/skills/{skill_id}/learning-progress", json={"status": status})


# --- setting progress ------------------------------------------------------------


def test_nothing_is_listed_before_any_progress_is_set(client: TestClient) -> None:
    response = client.get("/learning-progress")

    assert response.status_code == 200
    assert response.json() == []


def test_set_studying_then_finished_updates_one_row(client: TestClient, engine: Engine) -> None:
    skill_id = _create_skill(engine, "Docker")

    studying = _set(client, skill_id, "studying")
    finished = _set(client, skill_id, "finished")

    assert studying.status_code == 200
    assert studying.json()["status"] == "studying"
    assert studying.json()["skill_name"] == "Docker"
    assert studying.json()["updated_at"] is not None
    assert finished.status_code == 200
    assert finished.json()["status"] == "finished"
    assert _count(engine, LearningProgress) == 1
    assert [(p["skill_id"], p["status"]) for p in client.get("/learning-progress").json()] == [
        (skill_id, "finished")
    ]


def test_not_started_removes_the_row(client: TestClient, engine: Engine) -> None:
    skill_id = _create_skill(engine, "Docker")
    _set(client, skill_id, "studying")

    response = _set(client, skill_id, "not_started")

    assert response.status_code == 200
    assert response.json()["status"] == "not_started"
    assert response.json()["updated_at"] is None
    assert _count(engine, LearningProgress) == 0
    assert client.get("/learning-progress").json() == []


def test_not_started_when_nothing_was_set_is_fine_and_stores_nothing(
    client: TestClient, engine: Engine
) -> None:
    skill_id = _create_skill(engine, "Docker")

    response = _set(client, skill_id, "not_started")

    assert response.status_code == 200
    assert response.json()["status"] == "not_started"
    assert _count(engine, LearningProgress) == 0


def test_unknown_skill_is_404(client: TestClient, engine: Engine) -> None:
    assert _set(client, 999, "studying").status_code == 404
    assert _count(engine, LearningProgress) == 0


@pytest.mark.parametrize("bad_status", ["verified", "mastered", "", "STUDYING"])
def test_anything_other_than_the_three_statuses_is_422(
    client: TestClient, engine: Engine, bad_status: str
) -> None:
    skill_id = _create_skill(engine, "Docker")

    assert _set(client, skill_id, bad_status).status_code == 422
    assert _count(engine, LearningProgress) == 0


# --- listing -------------------------------------------------------------------


def test_list_is_ordered_by_skill_name(client: TestClient, engine: Engine) -> None:
    for name in ["Python", "Docker", "Kubernetes"]:
        _set(client, _create_skill(engine, name), "studying")

    names = [p["skill_name"] for p in client.get("/learning-progress").json()]

    assert names == ["Docker", "Kubernetes", "Python"]


def test_list_shows_only_the_current_users_progress(client: TestClient, engine: Engine) -> None:
    mine = _create_skill(engine, "Docker")
    _set(client, mine, "studying")
    with Session(engine, autoflush=False) as db:
        other_user = User(email="other@example.com")
        db.add(LearningProgress(user=other_user, skill=db.get(Skill, mine), status=LearningStatus.FINISHED))
        db.commit()

    listed = client.get("/learning-progress").json()

    assert [(p["skill_id"], p["status"]) for p in listed] == [(mine, "studying")]


# --- the key rule: studying is never proof ------------------------------------------


def test_finishing_studying_never_changes_a_claims_verification_status(
    client: TestClient, engine: Engine
) -> None:
    skill_id = _create_skill(engine, "Docker")
    claim = client.post("/user-skills", json={"skill_id": skill_id}).json()
    assert claim["status"] == "provisional"

    assert _set(client, skill_id, "finished").status_code == 200

    after = client.get("/user-skills").json()
    assert [(c["id"], c["status"], c["evidence_ids"]) for c in after] == [
        (claim["id"], "provisional", [])
    ]


def test_finishing_studying_an_unclaimed_skill_creates_no_claim(
    client: TestClient, engine: Engine
) -> None:
    skill_id = _create_skill(engine, "Docker")

    assert _set(client, skill_id, "finished").status_code == 200

    assert _count(engine, UserSkill) == 0
    assert client.get("/user-skills").json() == []
