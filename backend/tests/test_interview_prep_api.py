"""HTTP tests for the interview prep sheet: fixed templates filled only with the user's data.

Same TestClient + dependency_overrides[get_db] + StaticPool in-memory SQLite pattern as
the other API tests, plus a fake extractor so the job's requirements are exact.
"""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.ai.schemas import ExtractedRequirement, ExtractionResult
from app.core.services import skill_service
from app.db.models import JobDescription, User
from app.dependencies import get_db, get_requirement_extractor
from app.main import app
from database import Base


class FakeExtractor:
    def __init__(self, *proposals: ExtractedRequirement) -> None:
        self._result = ExtractionResult(requirements=list(proposals))

    def extract_requirements(self, raw_text: str) -> ExtractionResult:
        return self._result


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


def _skills(engine: Engine, *names: str) -> dict[str, int]:
    with Session(engine, autoflush=False) as db:
        ids = {name: skill_service.create_skill(db, name).id for name in names}
        db.commit()
    return ids


def _job(client: TestClient, text: str, *proposals: ExtractedRequirement) -> int:
    app.dependency_overrides[get_requirement_extractor] = lambda: FakeExtractor(*proposals)
    job_id = client.post("/job-descriptions", json={"raw_text": text, "title": "Backend", "company": "Acme"}).json()["id"]
    assert client.post(f"/job-descriptions/{job_id}/extract").status_code == 200
    return job_id


def _req(text: str, mention: str | None = None, required: bool = True) -> ExtractedRequirement:
    return ExtractedRequirement(text=text, is_required=required, skill_mention=mention)


def _claim(client: TestClient, skill_id: int) -> int:
    return client.post("/user-skills", json={"skill_id": skill_id}).json()["id"]


def _proof(client: TestClient, claim_id: int, title: str, **source) -> int:
    evidence_id = client.post(
        "/evidence", json={"evidence_type": "project", "title": title, "url": None, **source}
    ).json()["id"]
    client.post(f"/user-skills/{claim_id}/evidence-links", json={"evidence_id": evidence_id})
    return evidence_id


def _status(client: TestClient, claim_id: int, status: str) -> None:
    assert client.post(f"/user-skills/{claim_id}/status", json={"status": status}).status_code == 200


def _prep(client: TestClient, job_id: int) -> dict:
    response = client.get(f"/job-descriptions/{job_id}/interview-prep")
    assert response.status_code == 200
    return response.json()


@pytest.fixture()
def sheet(client: TestClient, engine: Engine) -> dict:
    """One job covering every case: verified, partial, provisional, not verified, no claim, unmapped."""
    s = _skills(engine, "Python", "Docker", "Rust", "Go", "Kotlin")
    project = client.post("/projects", json={"name": "FundsApp"}).json()["id"]
    job = client.post(
        "/work-experiences", json={"company": "Acme", "role": "Intern", "start_date": "2023-06-01"}
    ).json()["id"]

    python = _claim(client, s["Python"])
    _proof(client, python, "FundsApp repo", project_id=project)
    _status(client, python, "verified")
    docker = _claim(client, s["Docker"])
    _proof(client, docker, "Internship Dockerfiles", work_experience_id=job)
    _status(client, docker, "partial")
    _claim(client, s["Rust"])  # stays provisional
    go = _claim(client, s["Go"])
    _status(client, go, "not_verified")
    client.post("/evidence", json={"evidence_type": "other", "title": "Unrelated proof"})  # never linked
    for skill in ["Python", "Rust"]:
        client.patch(f"/skills/{s[skill]}/cv-presence", json={"present": True})

    job_id = _job(
        client,
        "Some obscure tooling is nice. Need Python, Docker, Rust, Go and Kotlin.",
        _req("Some obscure tooling", required=False),  # first id, but "nice to have": listed last
        _req("Python", "Python"),
        _req("Docker", "Docker"),
        _req("Rust", "Rust"),
        _req("Go", "Go"),
        _req("Kotlin", "Kotlin"),
    )
    return _prep(client, job_id)


def _item(sheet: dict, text: str) -> dict:
    return next(i for i in sheet["items"] if i["requirement_text"] == text)


# --- one template per situation --------------------------------------------------


def test_header_and_order_required_first(sheet: dict) -> None:
    assert (sheet["title"], sheet["company"]) == ("Backend", "Acme")
    assert [i["requirement_text"] for i in sheet["items"]] == [
        "Python",
        "Docker",
        "Rust",
        "Go",
        "Kotlin",
        "Some obscure tooling",
    ]


def test_each_status_gets_its_template(sheet: dict) -> None:
    expected = {
        "Python": ("verified", "You can claim Python."),
        "Docker": ("partial", "You have some proof for Docker."),
        "Rust": ("provisional", "You've claimed Rust but haven't proven it yet."),
        "Go": ("not_verified", "Your claim on Go isn't backed by evidence."),
        "Kotlin": ("no_claim", "You haven't claimed Kotlin."),
        "Some obscure tooling": ("unmapped", "This requirement isn't linked to a skill"),
    }
    for text, (status, opening) in expected.items():
        item = _item(sheet, text)
        assert item["status"] == status, text
        assert item["guidance"].startswith(opening), text


def test_evidence_listed_is_exactly_the_linked_evidence_with_its_source(sheet: dict) -> None:
    listed = {i["requirement_text"]: [(e["title"], e["source"]) for e in i["evidence"]] for i in sheet["items"]}

    assert listed == {
        "Python": [("FundsApp repo", "project FundsApp")],
        "Docker": [("Internship Dockerfiles", "Intern at Acme")],
        "Rust": [],
        "Go": [],
        "Kotlin": [],
        "Some obscure tooling": [],
    }
    assert "Unrelated proof" not in str(sheet)  # never linked, so never offered as a talking point


def test_cv_warning_only_for_unproven_skills_on_the_cv(sheet: dict) -> None:
    warnings = {i["requirement_text"]: i["cv_warning"] for i in sheet["items"]}

    assert warnings["Rust"] == "Rust is on your CV, so expect to be asked about it."
    assert warnings["Python"] is None  # on the CV but verified: nothing to warn about
    assert all(warnings[t] is None for t in ["Docker", "Go", "Kotlin", "Some obscure tooling"])


def test_study_links_for_mapped_skills_only(sheet: dict) -> None:
    kotlin = _item(sheet, "Kotlin")
    assert [(l["mode"], l["query"]) for l in kotlin["study_links"]] == [
        ("theory_interview", "Kotlin interview questions"),
        ("technical_practical", "Kotlin full course tutorial"),
    ]
    assert kotlin["study_links"][0]["url"].startswith("https://www.youtube.com/results?search_query=")
    assert _item(sheet, "Some obscure tooling")["study_links"] == []
    assert _item(sheet, "Some obscure tooling")["skill_name"] is None


# --- current state, not the last comparison --------------------------------------------


def test_reflects_current_proof_without_comparing_again(client: TestClient, engine: Engine) -> None:
    s = _skills(engine, "Python")
    claim = _claim(client, s["Python"])
    job_id = _job(client, "Need Python.", _req("Python", "Python"))
    client.post(f"/job-descriptions/{job_id}/compare")
    assert _prep(client, job_id)["items"][0]["status"] == "provisional"

    _proof(client, claim, "Repo")
    _status(client, claim, "verified")

    assert _prep(client, job_id)["items"][0]["status"] == "verified"  # no compare needed


def test_a_job_with_no_requirements_has_an_empty_sheet(client: TestClient) -> None:
    job_id = _job(client, "Nothing here.")

    assert _prep(client, job_id)["items"] == []


def test_missing_or_another_users_job_is_404(client: TestClient, engine: Engine) -> None:
    assert client.get("/job-descriptions/999/interview-prep").status_code == 404
    with Session(engine, autoflush=False) as db:
        other = JobDescription(user=User(email="other@example.com"), raw_text="Not yours.")
        db.add(other)
        db.commit()
        other_id = other.id
    assert client.get(f"/job-descriptions/{other_id}/interview-prep").status_code == 404
