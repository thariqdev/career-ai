"""HTTP tests for the job-descriptions endpoints.

Same TestClient + dependency_overrides[get_db] + StaticPool in-memory SQLite pattern
as test_skills_api.py, plus dependency_overrides[get_requirement_extractor] with a
fake extractor (same style as test_requirement_service.py's FakeExtractor) so
extraction has real content to accept/reject over HTTP.
"""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.ai.schemas import ExtractedRequirement, ExtractionResult
from app.core.services import skill_service, verification_service
from app.db.models import ComparisonResult, Evidence, JobDescription, JobRequirement, User, UserSkill
from app.db.models.enums import EvidenceType, VerificationStatus
from app.dependencies import get_db, get_requirement_extractor
from app.main import app
from database import Base


class FakeExtractor:
    """Returns canned proposals and records every call it receives."""

    def __init__(self, *proposals: ExtractedRequirement) -> None:
        self._result = ExtractionResult(requirements=list(proposals))
        self.calls: list[str] = []

    def extract_requirements(self, raw_text: str) -> ExtractionResult:
        self.calls.append(raw_text)
        return self._result


def _proposal(text: str, is_required: bool = True, mention: str | None = None) -> ExtractedRequirement:
    return ExtractedRequirement(text=text, is_required=is_required, skill_mention=mention)


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


def _with_extractor(client: TestClient, extractor: object) -> None:
    app.dependency_overrides[get_requirement_extractor] = lambda: extractor


def _create_job(client: TestClient, raw_text: str) -> dict:
    response = client.post("/job-descriptions", json={"raw_text": raw_text})
    assert response.status_code == 201, response.text
    return response.json()


def _session(engine: Engine) -> Session:
    return Session(engine, autoflush=False)


# --- list -------------------------------------------------------------------------


def test_list_is_empty_on_a_fresh_database(client: TestClient) -> None:
    response = client.get("/job-descriptions")

    assert response.status_code == 200
    assert response.json() == []


def test_list_returns_most_recent_first(client: TestClient) -> None:
    first = _create_job(client, "First posting.")
    second = _create_job(client, "Second posting.")
    third = _create_job(client, "Third posting.")

    response = client.get("/job-descriptions")

    assert response.status_code == 200
    ids = [item["id"] for item in response.json()]
    assert ids == [third["id"], second["id"], first["id"]]


def test_list_is_scoped_to_the_current_user(client: TestClient, engine: Engine) -> None:
    mine = _create_job(client, "Mine.")
    with _session(engine) as db:
        other_user = User(email="other@example.com")
        other_job = JobDescription(user=other_user, raw_text="Not yours.")
        db.add_all([other_user, other_job])
        db.commit()

    response = client.get("/job-descriptions")

    assert response.status_code == 200
    ids = [item["id"] for item in response.json()]
    assert ids == [mine["id"]]


# --- create / read -------------------------------------------------------------


def test_create_persists_and_get_returns_it_with_empty_requirements(
    client: TestClient, engine: Engine
) -> None:
    body = _create_job(client, "Need Python and PostgreSQL.")
    assert body["requirements"] == []
    assert isinstance(body["id"], int)

    response = client.get(f"/job-descriptions/{body['id']}")

    assert response.status_code == 200
    assert response.json() == body
    with _session(engine) as db:
        assert db.scalar(select(func.count()).select_from(JobDescription)) == 1


def test_get_on_a_nonexistent_id_is_404(client: TestClient) -> None:
    assert client.get("/job-descriptions/999").status_code == 404


def test_get_on_another_users_job_description_is_404(client: TestClient, engine: Engine) -> None:
    """Bypass the API to create a row owned by a different user, proving the check filters."""
    with _session(engine) as db:
        other_user = User(email="other@example.com")
        other_job = JobDescription(user=other_user, raw_text="Not yours.")
        db.add_all([other_user, other_job])
        db.commit()
        other_job_id = other_job.id

    response = client.get(f"/job-descriptions/{other_job_id}")

    assert response.status_code == 404


# --- extract --------------------------------------------------------------------


def test_extract_splits_accepted_and_rejected_and_accepted_are_visible_via_get(
    client: TestClient, engine: Engine
) -> None:
    body = _create_job(client, "Need Python experience and PostgreSQL knowledge.")
    with _session(engine) as db:
        skill_service.create_skill(db, "Python")
        db.commit()
    extractor = FakeExtractor(
        _proposal("Python experience", mention="Python"),
        _proposal("Kubernetes expertise"),  # invented -> rejected
        _proposal("  PYTHON   experience "),  # duplicate of the first -> rejected
        _proposal("PostgreSQL knowledge", mention="Zorblax"),  # unmapped skill -> accepted, skill None
    )
    _with_extractor(client, extractor)

    response = client.post(f"/job-descriptions/{body['id']}/extract")

    assert response.status_code == 200
    result = response.json()
    assert [r["requirement_text"] for r in result["accepted"]] == [
        "Python experience",
        "PostgreSQL knowledge",
    ]
    assert [r["skill_name"] for r in result["accepted"]] == ["Python", None]
    assert [r["skill_id"] for r in result["accepted"]] == [result["accepted"][0]["skill_id"], None]
    assert [(r["text"], r["reason"]) for r in result["rejected"]] == [
        ("Kubernetes expertise", "not found in job description text"),
        ("  PYTHON   experience ", "duplicate requirement text"),  # raw proposal text, unstripped
    ]

    fetched = client.get(f"/job-descriptions/{body['id']}").json()
    assert [r["requirement_text"] for r in fetched["requirements"]] == [
        "Python experience",
        "PostgreSQL knowledge",
    ]


def test_extract_twice_is_409_and_the_extractor_is_not_called_again(
    client: TestClient, engine: Engine
) -> None:
    body = _create_job(client, "Need Python experience.")
    extractor = FakeExtractor(_proposal("Python experience"))
    _with_extractor(client, extractor)
    first = client.post(f"/job-descriptions/{body['id']}/extract")
    assert first.status_code == 200
    assert extractor.calls == ["Need Python experience."]

    second = client.post(f"/job-descriptions/{body['id']}/extract")

    assert second.status_code == 409
    assert extractor.calls == ["Need Python experience."]  # not called a second time


def test_extract_with_the_default_stub_extractor_accepts_and_rejects_nothing(
    client: TestClient,
) -> None:
    """Proves the safe placeholder is actually wired: no override, no fabrication."""
    body = _create_job(client, "Need Python experience.")

    response = client.post(f"/job-descriptions/{body['id']}/extract")

    assert response.status_code == 200
    assert response.json() == {"accepted": [], "rejected": []}


def test_extract_on_a_nonexistent_or_not_owned_id_is_404(client: TestClient, engine: Engine) -> None:
    assert client.post("/job-descriptions/999/extract").status_code == 404

    with _session(engine) as db:
        other_user = User(email="other@example.com")
        other_job = JobDescription(user=other_user, raw_text="Not yours.")
        db.add_all([other_user, other_job])
        db.commit()
        other_job_id = other_job.id
    assert client.post(f"/job-descriptions/{other_job_id}/extract").status_code == 404


# --- compare ---------------------------------------------------------------------


def test_compare_produces_correct_statuses_including_verified_and_unmapped(
    client: TestClient, engine: Engine
) -> None:
    body = _create_job(client, "Need Python experience and some obscure tooling.")
    with _session(engine) as db:
        python = skill_service.create_skill(db, "Python")
        job = db.get(JobDescription, body["id"])
        user_skill = UserSkill(user=job.user, skill=python)
        db.add(user_skill)
        db.flush()
        evidence = Evidence(user=job.user, evidence_type=EvidenceType.PROJECT, title="FundsApp repo")
        db.add(evidence)
        db.flush()
        verification_service.link_evidence(db, user_skill, evidence)
        verification_service.set_status(db, user_skill, VerificationStatus.VERIFIED)
        db.commit()
    extractor = FakeExtractor(
        _proposal("Python experience", mention="Python"),
        _proposal("some obscure tooling"),
    )
    _with_extractor(client, extractor)
    client.post(f"/job-descriptions/{body['id']}/extract")

    response = client.post(f"/job-descriptions/{body['id']}/compare")

    assert response.status_code == 200
    results = response.json()
    assert len(results) == 2
    assert results[0]["knowledge_status"] == "verified"
    assert results[0]["evidence_ids"] != []
    assert results[1]["knowledge_status"] == "not_verified"
    assert results[1]["evidence_ids"] == []


def test_compare_twice_doubles_the_result_count(client: TestClient, engine: Engine) -> None:
    body = _create_job(client, "Need Python experience.")
    _with_extractor(client, FakeExtractor(_proposal("Python experience")))
    client.post(f"/job-descriptions/{body['id']}/extract")

    first = client.post(f"/job-descriptions/{body['id']}/compare")
    second = client.post(f"/job-descriptions/{body['id']}/compare")

    assert len(first.json()) == 1
    assert len(second.json()) == 1
    with _session(engine) as db:
        assert db.scalar(select(func.count()).select_from(ComparisonResult)) == 2


def test_compare_on_a_nonexistent_or_not_owned_id_is_404(client: TestClient, engine: Engine) -> None:
    assert client.post("/job-descriptions/999/compare").status_code == 404

    with _session(engine) as db:
        other_user = User(email="other@example.com")
        other_job = JobDescription(user=other_user, raw_text="Not yours.")
        db.add_all([other_user, other_job])
        db.commit()
        other_job_id = other_job.id
    assert client.post(f"/job-descriptions/{other_job_id}/compare").status_code == 404


# --- gaps -------------------------------------------------------------------------


def test_gaps_before_compare_is_empty(client: TestClient) -> None:
    body = _create_job(client, "Need Python experience.")
    _with_extractor(client, FakeExtractor(_proposal("Python experience")))
    client.post(f"/job-descriptions/{body['id']}/extract")

    response = client.get(f"/job-descriptions/{body['id']}/gaps")

    assert response.status_code == 200
    assert response.json() == []


def test_gaps_reflect_non_verified_requirements_then_disappear_once_verified(
    client: TestClient, engine: Engine
) -> None:
    body = _create_job(client, "Need Python experience.")
    with _session(engine) as db:
        python = skill_service.create_skill(db, "Python")
        job = db.get(JobDescription, body["id"])
        user_skill = UserSkill(user=job.user, skill=python)
        db.add(user_skill)
        db.commit()
    _with_extractor(client, FakeExtractor(_proposal("Python experience", mention="Python")))
    client.post(f"/job-descriptions/{body['id']}/extract")
    client.post(f"/job-descriptions/{body['id']}/compare")

    before = client.get(f"/job-descriptions/{body['id']}/gaps").json()
    assert len(before) == 1
    assert before[0]["result"]["knowledge_status"] == "provisional"

    with _session(engine) as db:
        user_skill = db.scalar(select(UserSkill))
        evidence = Evidence(user=user_skill.user, evidence_type=EvidenceType.PROJECT, title="repo")
        db.add(evidence)
        db.flush()
        verification_service.link_evidence(db, user_skill, evidence)
        verification_service.set_status(db, user_skill, VerificationStatus.VERIFIED)
        db.commit()
        stored_results_before = db.scalar(select(func.count()).select_from(ComparisonResult))

    client.post(f"/job-descriptions/{body['id']}/compare")
    after = client.get(f"/job-descriptions/{body['id']}/gaps").json()

    assert after == []
    with _session(engine) as db:
        stored_results_after = db.scalar(select(func.count()).select_from(ComparisonResult))
    assert stored_results_after == stored_results_before + 1  # older result untouched, new one added


def test_gaps_on_a_nonexistent_or_not_owned_id_is_404(client: TestClient, engine: Engine) -> None:
    assert client.get("/job-descriptions/999/gaps").status_code == 404

    with _session(engine) as db:
        other_user = User(email="other@example.com")
        other_job = JobDescription(user=other_user, raw_text="Not yours.")
        db.add_all([other_user, other_job])
        db.commit()
        other_job_id = other_job.id
    assert client.get(f"/job-descriptions/{other_job_id}/gaps").status_code == 404


# --- docs -------------------------------------------------------------------------


def test_openapi_and_docs_include_the_job_description_routes(client: TestClient) -> None:
    schema = client.get("/openapi.json")

    assert schema.status_code == 200
    paths = set(schema.json()["paths"])
    assert {
        "/job-descriptions",
        "/job-descriptions/{job_description_id}",
        "/job-descriptions/{job_description_id}/extract",
        "/job-descriptions/{job_description_id}/compare",
        "/job-descriptions/{job_description_id}/gaps",
    } <= paths
    assert client.get("/docs").status_code == 200
