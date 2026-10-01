"""HTTP tests for removing one requirement: only its own history goes with it.

Same TestClient + dependency_overrides[get_db] + StaticPool in-memory SQLite pattern as
the other API tests.
"""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.services import skill_service
from app.db.models import ComparisonResult, ComparisonResultEvidence, JobDescription, User
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


@pytest.fixture(autouse=True)
def _free_extractor(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)  # use the free skill-list reader


@pytest.fixture()
def setup(client: TestClient, engine: Engine) -> dict:
    """Python is claimed and verified with evidence; two jobs both ask for Python and Docker."""
    with Session(engine, autoflush=False) as db:
        python_id = skill_service.create_skill(db, "Python").id
        skill_service.create_skill(db, "Docker")
        db.commit()
    claim_id = client.post("/user-skills", json={"skill_id": python_id}).json()["id"]
    evidence_id = client.post("/evidence", json={"evidence_type": "project", "title": "Repo"}).json()["id"]
    client.post(f"/user-skills/{claim_id}/evidence-links", json={"evidence_id": evidence_id})
    client.post(f"/user-skills/{claim_id}/status", json={"status": "verified"})

    jobs = []
    for title in ("Backend", "Platform"):
        job_id = client.post(
            "/job-descriptions", json={"raw_text": "Need Python and Docker.", "title": title}
        ).json()["id"]
        client.post(f"/job-descriptions/{job_id}/extract")
        assert client.post(f"/job-descriptions/{job_id}/compare").status_code == 200
        jobs.append(job_id)
    return {"jobs": jobs, "claim_id": claim_id, "evidence_id": evidence_id}


def _requirement_id(client: TestClient, job_id: int, skill_name: str) -> int:
    requirements = client.get(f"/job-descriptions/{job_id}").json()["requirements"]
    return next(r["id"] for r in requirements if r["skill_name"] == skill_name)


def _skill_names(client: TestClient, job_id: int) -> list[str]:
    return sorted(r["skill_name"] for r in client.get(f"/job-descriptions/{job_id}").json()["requirements"])


def _result_count(engine: Engine, model: type) -> int:
    with Session(engine) as db:
        return db.scalar(select(func.count()).select_from(model))


def test_removing_a_requirement_takes_only_its_own_results(
    client: TestClient, engine: Engine, setup: dict
) -> None:
    backend, platform = setup["jobs"]
    assert _result_count(engine, ComparisonResult) == 4
    assert _result_count(engine, ComparisonResultEvidence) == 2  # Python's, once per job

    docker_id = _requirement_id(client, backend, "Docker")

    response = client.delete(
        f"/job-descriptions/{backend}/requirements/{_requirement_id(client, backend, 'Python')}"
    )

    assert response.status_code == 204
    assert _skill_names(client, backend) == ["Docker"]
    results = client.get(f"/job-descriptions/{backend}/results").json()
    assert [r["job_requirement_id"] for r in results] == [docker_id]
    assert _result_count(engine, ComparisonResult) == 3
    assert _result_count(engine, ComparisonResultEvidence) == 1
    # The other job still has both requirements and both results.
    assert _skill_names(client, platform) == ["Docker", "Python"]
    assert len(client.get(f"/job-descriptions/{platform}/results").json()) == 2


def test_claim_evidence_and_skill_are_kept(client: TestClient, setup: dict) -> None:
    backend = setup["jobs"][0]

    client.delete(f"/job-descriptions/{backend}/requirements/{_requirement_id(client, backend, 'Python')}")

    [claim] = client.get("/user-skills").json()
    assert claim["status"] == "verified"
    assert claim["evidence_ids"] == [setup["evidence_id"]]
    assert [e["id"] for e in client.get("/evidence").json()] == [setup["evidence_id"]]
    assert sorted(s["name"] for s in client.get("/skills").json()) == ["Docker", "Python"]


def test_a_removed_gap_leaves_gaps_and_interview_prep(client: TestClient, setup: dict) -> None:
    backend = setup["jobs"][0]
    assert [g["requirement"]["skill_name"] for g in client.get(f"/job-descriptions/{backend}/gaps").json()] == [
        "Docker"
    ]

    client.delete(f"/job-descriptions/{backend}/requirements/{_requirement_id(client, backend, 'Docker')}")

    assert client.get(f"/job-descriptions/{backend}/gaps").json() == []
    prep = client.get(f"/job-descriptions/{backend}/interview-prep")
    assert prep.status_code == 200
    assert "Docker" not in prep.text


def test_a_requirement_of_another_job_is_404(client: TestClient, setup: dict) -> None:
    backend, platform = setup["jobs"]
    platform_python = _requirement_id(client, platform, "Python")

    assert client.delete(f"/job-descriptions/{backend}/requirements/{platform_python}").status_code == 404
    assert _skill_names(client, platform) == ["Docker", "Python"]


def test_unknown_ids_are_404(client: TestClient, setup: dict) -> None:
    backend = setup["jobs"][0]
    requirement_id = _requirement_id(client, backend, "Python")

    assert client.delete(f"/job-descriptions/{backend}/requirements/999").status_code == 404
    assert client.delete(f"/job-descriptions/999/requirements/{requirement_id}").status_code == 404
    assert _skill_names(client, backend) == ["Docker", "Python"]


def test_another_users_job_is_404(client: TestClient, engine: Engine, setup: dict) -> None:
    with Session(engine, autoflush=False) as db:
        other_job = JobDescription(user=User(email="other@example.com"), raw_text="Need Python.")
        db.add(other_job)
        db.commit()
        other_job_id = other_job.id
    backend = setup["jobs"][0]
    requirement_id = _requirement_id(client, backend, "Python")

    # The requirement exists, but the job in the URL isn't yours: same 404 as "missing".
    assert client.delete(f"/job-descriptions/{other_job_id}/requirements/{requirement_id}").status_code == 404
    assert _skill_names(client, backend) == ["Docker", "Python"]


def test_look_for_new_skills_can_add_it_back(client: TestClient, setup: dict) -> None:
    """Documented limitation: the posting still mentions it, so a re-read finds it again."""
    backend = setup["jobs"][0]
    client.delete(f"/job-descriptions/{backend}/requirements/{_requirement_id(client, backend, 'Docker')}")

    client.post(f"/job-descriptions/{backend}/extract-new")

    assert _skill_names(client, backend) == ["Docker", "Python"]
