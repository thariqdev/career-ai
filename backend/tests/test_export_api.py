"""HTTP tests for GET /export: a complete, read-only backup of one user's data.

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
from app.db.models import (
    CVSkillPresence,
    Evidence,
    JobDescription,
    LearningProgress,
    Project,
    User,
    UserSkill,
)
from app.db.models.enums import EvidenceType, LearningStatus
from app.dependencies import get_db
from app.main import app
from database import Base

SECTIONS = [
    "skills",
    "claims",
    "evidence",
    "projects",
    "work_experiences",
    "educations",
    "job_descriptions",
    "cv_marks",
    "learning_progress",
    "learning_resources",
]


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


@pytest.fixture()
def filled(client: TestClient, engine: Engine) -> dict:
    """One of everything for the current user, plus another user's private rows."""
    with Session(engine, autoflush=False) as db:
        python_id = skill_service.create_skill(db, "Python", "Languages").id
        docker_id = skill_service.create_skill(db, "Docker").id
        skill_service.add_alias(db, skill_service.get_skill(db, python_id), "py")
        db.commit()

    project_id = client.post("/projects", json={"name": "FundsApp", "start_date": "2025-01-01"}).json()["id"]
    client.post("/work-experiences", json={"company": "Acme", "role": "Intern", "start_date": "2024-06-01"})
    client.post("/educations", json={"institution": "State University", "degree": "BSc"})
    evidence_id = client.post(
        "/evidence", json={"evidence_type": "project", "title": "Repo", "project_id": project_id}
    ).json()["id"]
    claim_id = client.post("/user-skills", json={"skill_id": python_id}).json()["id"]
    client.post(f"/user-skills/{claim_id}/evidence-links", json={"evidence_id": evidence_id})
    client.post(f"/user-skills/{claim_id}/status", json={"status": "verified"})
    client.patch(f"/skills/{python_id}/cv-presence", json={"present": True})
    client.put(f"/skills/{docker_id}/learning-progress", json={"status": "studying"})
    client.post(
        f"/skills/{docker_id}/learning-resources",
        json={"mode": "theory_interview", "title": "Docs", "url": "https://docs.docker.com/"},
    )
    job_id = client.post(
        "/job-descriptions", json={"raw_text": "Need Python and Docker.", "title": "Backend"}
    ).json()["id"]
    client.post(f"/job-descriptions/{job_id}/extract")
    client.post(f"/job-descriptions/{job_id}/compare")

    with Session(engine, autoflush=False) as db:
        other = User(email="other@example.com")
        db.add_all(
            [
                UserSkill(user=other, skill_id=docker_id),
                Evidence(user=other, evidence_type=EvidenceType.PROJECT, title="Not mine"),
                Project(user=other, name="Secret project"),
                JobDescription(user=other, raw_text="Secret job", title="Theirs"),
                CVSkillPresence(user=other, skill_id=docker_id, present=True),
                LearningProgress(user=other, skill_id=python_id, status=LearningStatus.FINISHED),
            ]
        )
        db.commit()
    return {
        "python_id": python_id,
        "docker_id": docker_id,
        "claim_id": claim_id,
        "evidence_id": evidence_id,
        "project_id": project_id,
        "job_id": job_id,
    }


def _export(client: TestClient) -> dict:
    response = client.get("/export")
    assert response.status_code == 200
    return response.json()


def test_export_contains_every_section_with_its_links(client: TestClient, filled: dict) -> None:
    data = _export(client)

    assert data["app"] == "Career AI"
    assert data["format_version"] == 1
    assert data["user"]["email"] == "me@career-ai.local"
    assert [s["name"] for s in data["skills"]] == ["Python", "Docker"]
    assert data["skills"][0]["aliases"] == ["py"]
    assert data["skills"][0]["category"] == "Languages"

    [claim] = data["claims"]
    assert (claim["id"], claim["skill_id"], claim["status"]) == (filled["claim_id"], filled["python_id"], "verified")
    assert claim["evidence_ids"] == [filled["evidence_id"]]

    [evidence] = data["evidence"]
    assert (evidence["title"], evidence["evidence_type"], evidence["project_id"]) == (
        "Repo",
        "project",
        filled["project_id"],
    )
    assert [p["name"] for p in data["projects"]] == ["FundsApp"]
    assert data["projects"][0]["start_date"] == "2025-01-01"
    assert [(w["company"], w["role"]) for w in data["work_experiences"]] == [("Acme", "Intern")]
    assert [e["institution"] for e in data["educations"]] == ["State University"]

    [job] = data["job_descriptions"]
    assert (job["title"], job["raw_text"]) == ("Backend", "Need Python and Docker.")
    assert [r["requirement_text"] for r in job["requirements"]] == ["Python", "Docker"]
    by_requirement = {r["job_requirement_id"]: r for r in job["comparison_results"]}
    python_requirement = job["requirements"][0]["id"]
    assert by_requirement[python_requirement]["knowledge_status"] == "verified"
    assert by_requirement[python_requirement]["evidence_ids"] == [filled["evidence_id"]]
    assert job["removed_skill_ids"] == []

    assert [(m["skill_id"], m["present"]) for m in data["cv_marks"]] == [(filled["python_id"], True)]
    assert [(p["skill_id"], p["status"]) for p in data["learning_progress"]] == [(filled["docker_id"], "studying")]
    assert [r["url"] for r in data["learning_resources"]] == ["https://docs.docker.com/"]


def test_removed_requirements_are_exported(client: TestClient, filled: dict) -> None:
    job_id = filled["job_id"]
    docker_requirement = next(
        r["id"] for r in client.get(f"/job-descriptions/{job_id}").json()["requirements"] if r["skill_name"] == "Docker"
    )
    client.delete(f"/job-descriptions/{job_id}/requirements/{docker_requirement}")

    [job] = _export(client)["job_descriptions"]

    assert job["removed_skill_ids"] == [filled["docker_id"]]
    assert [r["requirement_text"] for r in job["requirements"]] == ["Python"]


def test_another_users_data_is_never_included(client: TestClient, filled: dict) -> None:
    data = _export(client)
    text = str(data)

    for secret in ("Not mine", "Secret project", "Secret job", "Theirs", "other@example.com"):
        assert secret not in text
    assert len(data["claims"]) == 1
    assert len(data["cv_marks"]) == 1
    assert len(data["learning_progress"]) == 1
    assert "user_id" not in data["claims"][0]


def test_download_headers(client: TestClient) -> None:
    response = client.get("/export")

    assert response.headers["content-type"] == "application/json"
    disposition = response.headers["content-disposition"]
    assert disposition.startswith('attachment; filename="career-ai-export-')
    assert disposition.endswith('.json"')


def test_empty_database_exports_empty_lists(client: TestClient) -> None:
    data = _export(client)

    for section in SECTIONS:
        assert data[section] == [], section


def test_exporting_changes_nothing(client: TestClient, engine: Engine, filled: dict) -> None:
    def counts() -> dict[str, int]:
        with Session(engine) as db:
            return {
                table.name: db.scalar(select(func.count()).select_from(table))
                for table in Base.metadata.sorted_tables
            }

    before = counts()
    _export(client)
    _export(client)
    assert counts() == before
