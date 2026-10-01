"""HTTP tests for removing a claim: its links go, evidence and skill stay, history is protected.

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
from app.db.models import Skill, User, UserSkill, UserSkillEvidence
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


def _skill(engine: Engine, name: str = "Python") -> int:
    with Session(engine, autoflush=False) as db:
        skill_id = skill_service.create_skill(db, name).id
        db.commit()
    return skill_id


def _claim(client: TestClient, skill_id: int) -> int:
    return client.post("/user-skills", json={"skill_id": skill_id}).json()["id"]


def _evidence(client: TestClient, title: str = "Repo") -> int:
    return client.post("/evidence", json={"evidence_type": "project", "title": title}).json()["id"]


def _link(client: TestClient, claim_id: int, evidence_id: int) -> None:
    response = client.post(f"/user-skills/{claim_id}/evidence-links", json={"evidence_id": evidence_id})
    assert response.status_code == 201


def _compare(client: TestClient, raw_text: str, title: str | None = None) -> int:
    job_id = client.post("/job-descriptions", json={"raw_text": raw_text, "title": title}).json()["id"]
    client.post(f"/job-descriptions/{job_id}/extract")
    assert client.post(f"/job-descriptions/{job_id}/compare").status_code == 200
    return job_id


def _link_rows(engine: Engine) -> int:
    with Session(engine) as db:
        return db.scalar(select(func.count()).select_from(UserSkillEvidence))


# --- removing ------------------------------------------------------------------------------


def test_removing_a_claim_keeps_its_evidence_and_the_skill(client: TestClient, engine: Engine) -> None:
    skill_id = _skill(engine)
    claim_id = _claim(client, skill_id)
    evidence_id = _evidence(client)
    _link(client, claim_id, evidence_id)

    response = client.delete(f"/user-skills/{claim_id}")

    assert response.status_code == 204
    assert client.get("/user-skills").json() == []
    assert _link_rows(engine) == 0
    assert [e["id"] for e in client.get("/evidence").json()] == [evidence_id]
    assert [s["id"] for s in client.get("/skills").json()] == [skill_id]
    # Unclaimed again, so it can be claimed afresh.
    assert client.post("/user-skills", json={"skill_id": skill_id}).status_code == 201


def test_a_verified_claim_can_be_removed_outright(client: TestClient, engine: Engine) -> None:
    """Unlinking its last proof is refused, but removing the whole claim leaves nothing
    'verified' behind, so it's allowed."""
    claim_id = _claim(client, _skill(engine))
    evidence_id = _evidence(client)
    _link(client, claim_id, evidence_id)
    client.post(f"/user-skills/{claim_id}/status", json={"status": "verified"})
    assert client.delete(f"/user-skills/{claim_id}/evidence-links/{evidence_id}").status_code == 409

    assert client.delete(f"/user-skills/{claim_id}").status_code == 204
    assert client.get("/user-skills").json() == []


def test_removing_one_claim_leaves_the_others(client: TestClient, engine: Engine) -> None:
    keep_id = _claim(client, _skill(engine, "Python"))
    drop_id = _claim(client, _skill(engine, "Docker"))
    evidence_id = _evidence(client)
    _link(client, keep_id, evidence_id)
    _link(client, drop_id, evidence_id)

    assert client.delete(f"/user-skills/{drop_id}").status_code == 204

    [kept] = client.get("/user-skills").json()
    assert kept["id"] == keep_id
    assert kept["evidence_ids"] == [evidence_id]


# --- history is protected ------------------------------------------------------------------


def test_a_claim_used_in_a_past_comparison_is_refused(client: TestClient, engine: Engine) -> None:
    claim_id = _claim(client, _skill(engine))
    evidence_id = _evidence(client)
    _link(client, claim_id, evidence_id)
    _compare(client, "Need Python.", title="Backend")
    _compare(client, "Python again.")

    response = client.delete(f"/user-skills/{claim_id}")

    assert response.status_code == 409
    detail = response.json()["detail"]
    assert "2 past comparison results use it" in detail
    assert '(jobs: "Backend", "Untitled"). Delete those jobs first' in detail
    [claim] = client.get("/user-skills").json()
    assert claim["evidence_ids"] == [evidence_id]


def test_deleting_the_jobs_frees_the_claim(client: TestClient, engine: Engine) -> None:
    claim_id = _claim(client, _skill(engine))
    job_id = _compare(client, "Need Python.", title="Backend")
    refused = client.delete(f"/user-skills/{claim_id}")
    assert refused.status_code == 409
    assert '1 past comparison result uses it (job: "Backend"). Delete that job first' in refused.json()["detail"]

    assert client.delete(f"/job-descriptions/{job_id}").status_code == 204

    assert client.delete(f"/user-skills/{claim_id}").status_code == 204


def test_removing_a_claim_unblocks_a_merge(client: TestClient, engine: Engine) -> None:
    target_id = _skill(engine, "Python")
    source_id = _skill(engine, "Pythonn")
    _claim(client, target_id)
    source_claim_id = _claim(client, source_id)
    assert client.post(f"/skills/{source_id}/merge-into/{target_id}").status_code == 409

    assert client.delete(f"/user-skills/{source_claim_id}").status_code == 204

    assert client.post(f"/skills/{source_id}/merge-into/{target_id}").status_code == 200


# --- not yours / not there ---------------------------------------------------------------


def test_another_users_claim_is_404_and_untouched(client: TestClient, engine: Engine) -> None:
    skill_id = _skill(engine)
    with Session(engine, autoflush=False) as db:
        other = UserSkill(user=User(email="other@example.com"), skill_id=skill_id)
        db.add(other)
        db.commit()
        other_id = other.id

    assert client.delete(f"/user-skills/{other_id}").status_code == 404
    with Session(engine) as db:
        assert db.get(UserSkill, other_id) is not None
        assert db.get(Skill, skill_id) is not None


def test_unknown_claim_is_404(client: TestClient) -> None:
    assert client.delete("/user-skills/999").status_code == 404
