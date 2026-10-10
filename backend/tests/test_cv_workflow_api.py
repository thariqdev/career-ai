"""Tests for the CV-first workflow: add all CV skills, job match summary, and the reset script.

Same TestClient + StaticPool in-memory SQLite pattern as the other API tests.
"""

import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.services import skill_service
from app.db.models import JobDescription, Skill, User, UserSkill
from app.dependencies import get_db
from app.main import app
from database import Base
from scripts import reset_data


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
def client(engine: Engine, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)  # use the free skill-list reader

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


CV = "Backend developer: Python, FastAPI, PostgreSQL and Docker. Frontend in React and JS. Git daily."


def _add_all(client: TestClient, text: str = CV) -> dict:
    response = client.post("/cv/add-all", data={"text": text})
    assert response.status_code == 200, response.json()
    return response.json()


def _claims(client: TestClient) -> dict[str, str]:
    names = {s["id"]: s["name"] for s in client.get("/skills").json()}
    return {names[c["skill_id"]]: c["status"] for c in client.get("/user-skills").json()}


# --- add all my CV skills -------------------------------------------------------------


def test_an_empty_app_gets_every_cv_skill_marked_and_provisionally_claimed(client: TestClient) -> None:
    body = _add_all(client)

    expected = ["Python", "FastAPI", "PostgreSQL", "Docker", "React", "JavaScript", "Git"]
    assert body["added_skills"] == expected
    assert sorted(body["marked_on_cv"]) == sorted(expected)
    assert sorted(body["claimed"]) == sorted(expected)
    assert set(_claims(client).values()) == {"provisional"}  # a CV is a claim, never proof
    statuses = {s["skill_name"]: s["cv_status"] for s in client.get("/cv/status").json()}
    assert set(statuses) == set(expected) and set(statuses.values()) == {"present"}
    javascript = next(s for s in client.get("/skills").json() if s["name"] == "JavaScript")
    assert javascript["aliases"] == ["JS"] and javascript["category"] == "Languages"


def test_running_it_again_adds_nothing(client: TestClient) -> None:
    _add_all(client)

    body = _add_all(client)

    assert body["added_skills"] == body["marked_on_cv"] == body["claimed"] == []
    assert len(body["already_done"]) == 7
    assert len(client.get("/skills").json()) == 7


def test_existing_skills_and_claims_are_kept_as_they_are(client: TestClient, engine: Engine) -> None:
    with Session(engine, autoflush=False) as db:
        python = skill_service.create_skill(db, "Python")
        db.commit()
        python_id = python.id
    claim_id = client.post("/user-skills", json={"skill_id": python_id}).json()["id"]
    evidence_id = client.post("/evidence", json={"evidence_type": "project", "title": "Repo"}).json()["id"]
    client.post(f"/user-skills/{claim_id}/evidence-links", json={"evidence_id": evidence_id})
    client.post(f"/user-skills/{claim_id}/status", json={"status": "verified"})

    body = _add_all(client)

    assert "Python" not in body["added_skills"] and "Python" not in body["claimed"]
    assert "Python" in body["marked_on_cv"]
    assert _claims(client)["Python"] == "verified"  # untouched
    assert sum(1 for s in client.get("/skills").json() if s["name"] == "Python") == 1


def test_add_all_needs_a_cv(client: TestClient) -> None:
    assert client.post("/cv/add-all").status_code == 422
    assert client.post("/cv/add-all", data={"text": "  "}).status_code == 422


# --- job match ------------------------------------------------------------------------


def _job(client: TestClient, text: str) -> int:
    job_id = client.post("/job-descriptions", json={"raw_text": text}).json()["id"]
    client.post(f"/job-descriptions/{job_id}/extract")
    return job_id


def test_match_splits_proven_on_cv_and_missing(client: TestClient, engine: Engine) -> None:
    _add_all(client, "Python, Docker and Git.")
    with Session(engine, autoflush=False) as db:
        skill_service.create_skill(db, "Kubernetes")
        skill_service.create_skill(db, "Go")
        db.commit()
    claims = {c["skill_id"]: c["id"] for c in client.get("/user-skills").json()}
    python_id = next(s["id"] for s in client.get("/skills").json() if s["name"] == "Python")
    evidence_id = client.post("/evidence", json={"evidence_type": "project", "title": "Repo"}).json()["id"]
    client.post(f"/user-skills/{claims[python_id]}/evidence-links", json={"evidence_id": evidence_id})
    client.post(f"/user-skills/{claims[python_id]}/status", json={"status": "verified"})
    job_id = _job(client, "We need Python, Docker, Kubernetes and Go. Python again.")

    body = client.get(f"/job-descriptions/{job_id}/match").json()

    assert [i["name"] for i in body["proven"]] == ["Python"]
    assert [i["name"] for i in body["on_cv"]] == ["Docker"]
    assert [i["name"] for i in body["missing"]] == ["Kubernetes", "Go"]
    assert body["total"] == 4  # Python counted once
    assert body["percent"] == 50


def test_match_is_current_without_comparing_again(client: TestClient) -> None:
    _add_all(client, "Python only.")
    job_id = _job(client, "Need Python and Docker.")
    assert client.get(f"/job-descriptions/{job_id}/match").json()["percent"] == 50

    _add_all(client, "Docker too.")  # added later; no "Compare again" needed

    assert client.get(f"/job-descriptions/{job_id}/match").json()["percent"] == 100


def test_a_job_with_no_requirements_is_zero_percent(client: TestClient) -> None:
    job_id = _job(client, "We want a nice person.")

    body = client.get(f"/job-descriptions/{job_id}/match").json()

    assert (body["percent"], body["total"]) == (0, 0)


def test_another_users_job_match_is_404(client: TestClient, engine: Engine) -> None:
    with Session(engine, autoflush=False) as db:
        job = JobDescription(user=User(email="other@example.com"), raw_text="Python")
        db.add(job)
        db.commit()
        job_id = job.id

    assert client.get(f"/job-descriptions/{job_id}/match").status_code == 404


# --- reset script -----------------------------------------------------------------------


def test_reset_refuses_without_yes(client: TestClient, engine: Engine, tmp_path: Path) -> None:
    _add_all(client)

    assert reset_data.main([], engine=engine, backup_dir=tmp_path) == 2

    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(Skill)) == 7
    assert list(tmp_path.iterdir()) == []


def test_reset_backs_up_then_empties_everything(client: TestClient, engine: Engine, tmp_path: Path) -> None:
    _add_all(client)
    _job(client, "Need Python.")

    assert reset_data.main(["--yes"], engine=engine, backup_dir=tmp_path) == 0

    assert all(n == 0 for n in reset_data.counts(engine).values())
    [backup] = list(tmp_path.iterdir())
    data = json.loads(backup.read_text(encoding="utf-8"))
    assert data["app"] == "Career AI" and len(data["skills"]) == 7 and len(data["job_descriptions"]) == 1


def test_the_backup_restores_into_the_emptied_app(client: TestClient, engine: Engine, tmp_path: Path) -> None:
    _add_all(client)
    reset_data.main(["--yes"], engine=engine, backup_dir=tmp_path)
    [backup] = list(tmp_path.iterdir())

    response = client.post("/import", files={"file": ("b.json", backup.read_bytes(), "application/json")})

    assert response.status_code == 200, response.json()
    assert len(client.get("/skills").json()) == 7
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(UserSkill)) == 7


def test_unsaved_common_skills_in_a_posting_count_as_missing(client: TestClient) -> None:
    """In an empty app, a posting's skills are still seen, so "what's missing" is real."""
    job_id = _job(client, "We use Kubernetes, Terraform and K8s operators.")

    body = client.get(f"/job-descriptions/{job_id}/match").json()

    assert [(i["skill_id"], i["name"]) for i in body["missing"]] == [(None, "Kubernetes"), (None, "Terraform")]
    assert body["percent"] == 0


def test_skills_removed_from_the_job_are_left_out(client: TestClient) -> None:
    _add_all(client, "Python and Docker.")
    job_id = _job(client, "Need Python and Docker.")
    docker_requirement = next(
        r["id"] for r in client.get(f"/job-descriptions/{job_id}").json()["requirements"] if r["skill_name"] == "Docker"
    )
    client.delete(f"/job-descriptions/{job_id}/requirements/{docker_requirement}")

    body = client.get(f"/job-descriptions/{job_id}/match").json()

    assert [i["name"] for i in body["on_cv"]] == ["Python"] and body["total"] == 1
