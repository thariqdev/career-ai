"""HTTP tests for the four-step learning path: each tick comes only from recorded facts.

Same TestClient + dependency_overrides[get_db] + StaticPool in-memory SQLite pattern as
the other API tests.
"""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.services import skill_service
from app.db.models import LearningProgress, Skill, User
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


def _skill(engine: Engine, name: str = "Docker") -> int:
    with Session(engine, autoflush=False) as db:
        skill_id = skill_service.create_skill(db, name).id
        db.commit()
    return skill_id


def _progress(client: TestClient, skill_id: int, status: str) -> None:
    assert client.put(f"/skills/{skill_id}/learning-progress", json={"status": status}).status_code == 200


def _claim(client: TestClient, skill_id: int) -> int:
    return client.post("/user-skills", json={"skill_id": skill_id}).json()["id"]


def _link_evidence(client: TestClient, claim_id: int) -> None:
    evidence_id = client.post("/evidence", json={"evidence_type": "project", "title": "Repo"}).json()["id"]
    assert client.post(f"/user-skills/{claim_id}/evidence-links", json={"evidence_id": evidence_id}).status_code == 201


def _status(client: TestClient, claim_id: int, status: str) -> None:
    assert client.post(f"/user-skills/{claim_id}/status", json={"status": status}).status_code == 200


def _path(client: TestClient, skill_id: int) -> dict:
    response = client.get(f"/skills/{skill_id}/learning-path")
    assert response.status_code == 200
    return response.json()


def _states(path: dict) -> list[str]:
    return [s["state"] for s in path["steps"]]


# --- the journey, one stage at a time --------------------------------------------------


def test_nothing_recorded_yet_starts_at_step_one(client: TestClient, engine: Engine) -> None:
    path = _path(client, _skill(engine))

    assert [s["key"] for s in path["steps"]] == ["start", "finish", "prove", "verify"]
    assert _states(path) == ["current", "todo", "todo", "todo"]
    assert path["next_step"] == "Start learning"
    assert [l["label"] for l in path["steps"][0]["links"]] == ["Theory on YouTube", "Hands-on course on YouTube"]
    assert path["steps"][0]["links"][1]["url"].endswith("search_query=Docker+full+course+tutorial")


def test_studying_moves_to_finish(client: TestClient, engine: Engine) -> None:
    skill_id = _skill(engine)
    _progress(client, skill_id, "studying")

    assert _states(_path(client, skill_id)) == ["done", "current", "todo", "todo"]


def test_finished_studying_moves_to_prove_but_never_ticks_it(client: TestClient, engine: Engine) -> None:
    skill_id = _skill(engine)
    _claim(client, skill_id)  # a claim exists, but no evidence is linked
    _progress(client, skill_id, "finished")

    path = _path(client, skill_id)

    assert _states(path) == ["done", "done", "current", "todo"]
    assert path["next_step"] == "Prove it"


def test_linked_evidence_ticks_prove_but_not_verify(client: TestClient, engine: Engine) -> None:
    skill_id = _skill(engine)
    _progress(client, skill_id, "finished")
    _link_evidence(client, _claim(client, skill_id))  # still provisional

    assert _states(_path(client, skill_id)) == ["done", "done", "done", "current"]


def test_partial_is_proof_but_not_verification(client: TestClient, engine: Engine) -> None:
    skill_id = _skill(engine)
    _progress(client, skill_id, "finished")
    claim = _claim(client, skill_id)
    _link_evidence(client, claim)
    _status(client, claim, "partial")

    assert _states(_path(client, skill_id)) == ["done", "done", "done", "current"]


def test_verified_completes_the_path(client: TestClient, engine: Engine) -> None:
    skill_id = _skill(engine)
    _progress(client, skill_id, "finished")
    claim = _claim(client, skill_id)
    _link_evidence(client, claim)
    _status(client, claim, "verified")

    path = _path(client, skill_id)

    assert _states(path) == ["done", "done", "done", "done"]
    assert path["next_step"] is None


def test_steps_done_out_of_order_still_point_at_the_first_open_one(client: TestClient, engine: Engine) -> None:
    skill_id = _skill(engine)
    claim = _claim(client, skill_id)
    _link_evidence(client, claim)
    _status(client, claim, "verified")  # proven, but never marked as studying

    path = _path(client, skill_id)

    assert _states(path) == ["current", "todo", "done", "done"]
    assert path["next_step"] == "Start learning"


def test_saved_links_appear_in_the_start_step(client: TestClient, engine: Engine) -> None:
    skill_id = _skill(engine)
    client.post(
        f"/skills/{skill_id}/learning-resources",
        json={"mode": "technical_practical", "title": "Docker docs", "url": "https://docs.docker.com/"},
    )

    links = _path(client, skill_id)["steps"][0]["links"]

    assert links[-1] == {"label": "Docker docs", "url": "https://docs.docker.com/"}


def test_unknown_skill_is_404(client: TestClient) -> None:
    assert client.get("/skills/999/learning-path").status_code == 404


# --- several at once ---------------------------------------------------------------------


def test_batch_keeps_order_collapses_duplicates_and_skips_unknown_ids(client: TestClient, engine: Engine) -> None:
    docker, python = _skill(engine, "Docker"), _skill(engine, "Python")
    _progress(client, python, "studying")

    response = client.get("/learning-paths", params=[("skill_ids", python), ("skill_ids", 999), ("skill_ids", docker), ("skill_ids", python)])

    assert response.status_code == 200
    assert [(p["skill_name"], p["next_step"]) for p in response.json()] == [
        ("Python", "Finish learning"),
        ("Docker", "Start learning"),
    ]
    assert client.get("/learning-paths").json() == []


def test_another_users_progress_doesnt_count(client: TestClient, engine: Engine) -> None:
    skill_id = _skill(engine)
    with Session(engine, autoflush=False) as db:
        db.add(LearningProgress(user=User(email="other@example.com"), skill=db.get(Skill, skill_id), status=LearningStatus.FINISHED))
        db.commit()

    assert _states(_path(client, skill_id)) == ["current", "todo", "todo", "todo"]
