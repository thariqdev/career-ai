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
from app.db.models import (
    ComparisonResult,
    ComparisonResultEvidence,
    Evidence,
    JobDescription,
    JobRequirement,
    Skill,
    User,
    UserSkill,
)
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


def test_default_extractor_with_no_saved_skills_accepts_and_rejects_nothing(
    client: TestClient, monkeypatch
) -> None:
    """No override and no taxonomy: the skill-list matcher has nothing to find, so it
    proposes nothing rather than guessing."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    body = _create_job(client, "Need Python experience.")

    response = client.post(f"/job-descriptions/{body['id']}/extract")

    assert response.status_code == 200
    assert response.json() == {"accepted": [], "rejected": [], "linked": [], "note": None}


def test_default_extractor_finds_saved_skills_and_maps_them(
    client: TestClient, engine: Engine, monkeypatch
) -> None:
    """No override: the real default wiring reads the taxonomy and links each skill."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with _session(engine) as db:
        skill_service.create_skill(db, "Python")
        skill_service.create_skill(db, "Java")
        postgres = skill_service.create_skill(db, "PostgreSQL")
        skill_service.add_alias(db, postgres, "Postgres")
        db.commit()
    body = _create_job(client, "Need Postgres and Python; JavaScript is a plus.")

    response = client.post(f"/job-descriptions/{body['id']}/extract")

    assert response.status_code == 200
    result = response.json()
    assert [(r["requirement_text"], r["skill_name"]) for r in result["accepted"]] == [
        ("Postgres", "PostgreSQL"),
        ("Python", "Python"),
    ]
    assert result["rejected"] == []


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


# --- extract-new: look again for requirements this job doesn't have yet -------------


def _texts(body: dict) -> list[str]:
    return [r["requirement_text"] for r in body["accepted"]]


def test_extract_new_adds_only_a_newly_saved_skill_and_leaves_existing_rows_alone(
    client: TestClient, engine: Engine, monkeypatch
) -> None:
    """Real default wiring (the skill-list matcher), as the user would hit it."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with _session(engine) as db:
        skill_service.create_skill(db, "Python")
        db.commit()
    body = _create_job(client, "Need Python and Docker.")
    first = client.post(f"/job-descriptions/{body['id']}/extract").json()
    client.post(f"/job-descriptions/{body['id']}/compare")
    with _session(engine) as db:
        skill_service.create_skill(db, "Docker")  # saved AFTER the job was analyzed
        db.commit()

    response = client.post(f"/job-descriptions/{body['id']}/extract-new")

    assert response.status_code == 200
    assert _texts(response.json()) == ["Docker"]
    assert [(r["text"], r["reason"]) for r in response.json()["rejected"]] == [
        ("Python", "already a requirement")
    ]
    requirements = client.get(f"/job-descriptions/{body['id']}").json()["requirements"]
    assert [(r["id"], r["requirement_text"]) for r in requirements][0] == (
        first["accepted"][0]["id"],
        "Python",
    )
    assert [r["requirement_text"] for r in requirements] == ["Python", "Docker"]
    with _session(engine) as db:
        assert db.scalar(select(func.count()).select_from(ComparisonResult)) == 1  # untouched
    results = client.get(f"/job-descriptions/{body['id']}/results").json()
    assert [r["job_requirement_id"] for r in results] == [first["accepted"][0]["id"]]


def test_extract_new_skips_the_same_text_and_the_same_skill_under_other_words(
    client: TestClient, engine: Engine
) -> None:
    with _session(engine) as db:
        postgres = skill_service.create_skill(db, "PostgreSQL")
        skill_service.add_alias(db, postgres, "Postgres")
        db.commit()
    body = _create_job(client, "PostgreSQL experience and Postgres tuning and Rust.")
    _with_extractor(client, FakeExtractor(_proposal("PostgreSQL experience", mention="PostgreSQL")))
    client.post(f"/job-descriptions/{body['id']}/extract")
    _with_extractor(
        client,
        FakeExtractor(
            _proposal("postgresql   EXPERIENCE"),  # same text, differently written
            _proposal("Postgres tuning", mention="Postgres"),  # same skill, other words
            _proposal("Rust"),  # genuinely new (unmapped)
            _proposal("Kubernetes"),  # invented: grounding still applies
        ),
    )

    body_after = client.post(f"/job-descriptions/{body['id']}/extract-new").json()

    assert _texts(body_after) == ["Rust"]
    assert [(r["text"], r["reason"]) for r in body_after["rejected"]] == [
        ("postgresql   EXPERIENCE", "already a requirement"),
        ("Postgres tuning", "already a requirement"),
        ("Kubernetes", "not found in job description text"),
    ]


def test_extract_new_with_nothing_new_adds_nothing(client: TestClient) -> None:
    body = _create_job(client, "Need Python experience.")
    _with_extractor(client, FakeExtractor(_proposal("Python experience")))
    client.post(f"/job-descriptions/{body['id']}/extract")

    response = client.post(f"/job-descriptions/{body['id']}/extract-new")

    assert response.status_code == 200
    assert response.json()["accepted"] == []
    assert len(client.get(f"/job-descriptions/{body['id']}").json()["requirements"]) == 1


def test_extract_new_works_on_a_job_with_no_requirements_yet(client: TestClient) -> None:
    body = _create_job(client, "Need Python experience.")
    _with_extractor(client, FakeExtractor(_proposal("Python experience")))

    response = client.post(f"/job-descriptions/{body['id']}/extract-new")

    assert _texts(response.json()) == ["Python experience"]


def test_extract_new_on_a_nonexistent_or_not_owned_id_is_404(client: TestClient, engine: Engine) -> None:
    assert client.post("/job-descriptions/999/extract-new").status_code == 404

    with _session(engine) as db:
        other_job = JobDescription(user=User(email="other@example.com"), raw_text="Not yours.")
        db.add(other_job)
        db.commit()
        other_job_id = other_job.id
    assert client.post(f"/job-descriptions/{other_job_id}/extract-new").status_code == 404


def test_extractor_info_says_whether_extraction_would_be_paid(client: TestClient, monkeypatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert client.get("/job-descriptions/extractor").json() == {"name": "skill_list", "paid": False, "model": None}

    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-not-real")  # never used to call anything
    assert client.get("/job-descriptions/extractor").json() == {"name": "claude", "paid": True, "model": None}


# --- delete -------------------------------------------------------------------------


def _counts(engine: Engine) -> dict[str, int]:
    with _session(engine) as db:
        return {
            model.__tablename__: db.scalar(select(func.count()).select_from(model))
            for model in [JobDescription, JobRequirement, ComparisonResult, ComparisonResultEvidence, Evidence, UserSkill, Skill]
        }


def test_delete_removes_the_job_with_its_own_history_and_nothing_else(
    client: TestClient, engine: Engine
) -> None:
    body = _create_job(client, "Need Python experience.")
    _claim_python(engine, body["id"], verified=True)
    _with_extractor(client, FakeExtractor(_proposal("Python experience", mention="Python")))
    client.post(f"/job-descriptions/{body['id']}/extract")
    client.post(f"/job-descriptions/{body['id']}/compare")
    before = _counts(engine)
    assert before["comparison_result_evidence"] == 1  # the verified result cites its evidence

    response = client.delete(f"/job-descriptions/{body['id']}")

    assert response.status_code == 204
    assert client.get(f"/job-descriptions/{body['id']}").status_code == 404
    after = _counts(engine)
    assert {k: after[k] for k in ["job_descriptions", "job_requirements", "comparison_results", "comparison_result_evidence"]} == {
        "job_descriptions": 0,
        "job_requirements": 0,
        "comparison_results": 0,
        "comparison_result_evidence": 0,
    }
    # Skills, claims and evidence belong to the user, not the job: untouched.
    assert {k: after[k] for k in ["evidence", "user_skills", "skills"]} == {
        k: before[k] for k in ["evidence", "user_skills", "skills"]
    }


def test_delete_only_touches_that_job(client: TestClient) -> None:
    keep = _create_job(client, "Need Python experience.")
    drop = _create_job(client, "Need Python experience too.")
    _with_extractor(client, FakeExtractor(_proposal("Python experience")))
    for job in (keep, drop):
        client.post(f"/job-descriptions/{job['id']}/extract")
        client.post(f"/job-descriptions/{job['id']}/compare")

    assert client.delete(f"/job-descriptions/{drop['id']}").status_code == 204

    assert [j["id"] for j in client.get("/job-descriptions").json()] == [keep["id"]]
    kept = client.get(f"/job-descriptions/{keep['id']}").json()
    assert [r["requirement_text"] for r in kept["requirements"]] == ["Python experience"]
    assert len(client.get(f"/job-descriptions/{keep['id']}/results").json()) == 1


def test_delete_a_missing_or_another_users_job_is_404(client: TestClient, engine: Engine) -> None:
    assert client.delete("/job-descriptions/999").status_code == 404
    with _session(engine) as db:
        other = JobDescription(user=User(email="other@example.com"), raw_text="Not yours.")
        db.add(other)
        db.commit()
        other_id = other.id

    assert client.delete(f"/job-descriptions/{other_id}").status_code == 404
    assert _counts(engine)["job_descriptions"] == 1


# --- latest results -----------------------------------------------------------------


def _claim_python(engine: Engine, job_id: int, verified: bool) -> None:
    """Give the job's owner a Python claim, VERIFIED (with evidence) or left PROVISIONAL."""
    with _session(engine) as db:
        python = skill_service.resolve_skill(db, "Python") or skill_service.create_skill(db, "Python")
        job = db.get(JobDescription, job_id)
        user_skill = db.scalar(select(UserSkill)) or UserSkill(user=job.user, skill=python)
        db.add(user_skill)
        db.flush()
        if verified:
            evidence = Evidence(user=job.user, evidence_type=EvidenceType.PROJECT, title="repo")
            db.add(evidence)
            db.flush()
            verification_service.link_evidence(db, user_skill, evidence)
            verification_service.set_status(db, user_skill, VerificationStatus.VERIFIED)
        db.commit()


def test_results_are_empty_before_any_comparison(client: TestClient) -> None:
    body = _create_job(client, "Need Python experience.")
    _with_extractor(client, FakeExtractor(_proposal("Python experience")))
    client.post(f"/job-descriptions/{body['id']}/extract")

    response = client.get(f"/job-descriptions/{body['id']}/results")

    assert response.status_code == 200
    assert response.json() == []


def test_results_include_verified_requirements_that_gaps_leave_out(
    client: TestClient, engine: Engine
) -> None:
    body = _create_job(client, "Need Python experience and some obscure tooling.")
    _claim_python(engine, body["id"], verified=True)
    _with_extractor(
        client,
        FakeExtractor(_proposal("Python experience", mention="Python"), _proposal("some obscure tooling")),
    )
    requirement_ids = [r["id"] for r in client.post(f"/job-descriptions/{body['id']}/extract").json()["accepted"]]
    client.post(f"/job-descriptions/{body['id']}/compare")

    results = client.get(f"/job-descriptions/{body['id']}/results").json()
    gaps = client.get(f"/job-descriptions/{body['id']}/gaps").json()

    assert [(r["job_requirement_id"], r["knowledge_status"]) for r in results] == [
        (requirement_ids[0], "verified"),
        (requirement_ids[1], "not_verified"),
    ]
    assert [g["requirement"]["id"] for g in gaps] == [requirement_ids[1]]


def test_comparing_again_makes_the_newer_result_win_and_keeps_the_older_one(
    client: TestClient, engine: Engine
) -> None:
    body = _create_job(client, "Need Python experience.")
    _claim_python(engine, body["id"], verified=False)
    _with_extractor(client, FakeExtractor(_proposal("Python experience", mention="Python")))
    client.post(f"/job-descriptions/{body['id']}/extract")
    first = client.post(f"/job-descriptions/{body['id']}/compare").json()
    assert [r["knowledge_status"] for r in first] == ["provisional"]

    _claim_python(engine, body["id"], verified=True)  # the user proves the skill
    second = client.post(f"/job-descriptions/{body['id']}/compare").json()
    results = client.get(f"/job-descriptions/{body['id']}/results").json()

    assert [(r["id"], r["knowledge_status"]) for r in results] == [(second[0]["id"], "verified")]
    assert second[0]["id"] != first[0]["id"]
    assert client.get(f"/job-descriptions/{body['id']}/gaps").json() == []
    with _session(engine) as db:
        assert db.scalar(select(func.count()).select_from(ComparisonResult)) == 2


def test_results_on_a_nonexistent_or_not_owned_id_is_404(client: TestClient, engine: Engine) -> None:
    assert client.get("/job-descriptions/999/results").status_code == 404

    with _session(engine) as db:
        other_user = User(email="other@example.com")
        other_job = JobDescription(user=other_user, raw_text="Not yours.")
        db.add_all([other_user, other_job])
        db.commit()
        other_job_id = other_job.id
    assert client.get(f"/job-descriptions/{other_job_id}/results").status_code == 404


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


# --- duplicates ---------------------------------------------------------------------------


def test_the_same_posting_twice_is_refused(client: TestClient) -> None:
    first = client.post("/job-descriptions", json={"raw_text": "We need Python.\n\nAnd Docker."})
    assert first.status_code == 201

    again = client.post(
        "/job-descriptions", json={"raw_text": "  we NEED python.  and docker. ", "title": "Other title"}
    )

    assert again.status_code == 409
    assert again.json()["detail"].startswith("You already added this exact job description on ")
    assert len(client.get("/job-descriptions").json()) == 1


def test_a_different_posting_is_fine(client: TestClient) -> None:
    client.post("/job-descriptions", json={"raw_text": "We need Python."})

    assert client.post("/job-descriptions", json={"raw_text": "We need Python and Go."}).status_code == 201


def test_another_users_identical_posting_is_not_a_duplicate(client: TestClient, engine) -> None:
    from sqlalchemy.orm import Session as _Session

    from app.db.models import JobDescription as _Job, User as _User

    with _Session(engine) as db:
        db.add(_Job(user=_User(email="other@example.com"), raw_text="We need Python."))
        db.commit()

    assert client.post("/job-descriptions", json={"raw_text": "We need Python."}).status_code == 201
