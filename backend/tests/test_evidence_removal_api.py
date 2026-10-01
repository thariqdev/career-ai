"""Unlinking and deleting evidence, without ever breaking "VERIFIED needs proof".

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
from app.db.models import Evidence, Skill, User, UserSkill, UserSkillEvidence
from app.db.models.enums import EvidenceType
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


def _claim(client: TestClient, engine: Engine, name: str = "Python") -> int:
    with Session(engine, autoflush=False) as db:
        skill_id = skill_service.create_skill(db, name).id
        db.commit()
    return client.post("/user-skills", json={"skill_id": skill_id}).json()["id"]


def _evidence(client: TestClient, title: str) -> int:
    return client.post("/evidence", json={"evidence_type": "project", "title": title}).json()["id"]


def _link(client: TestClient, claim_id: int, evidence_id: int) -> None:
    assert client.post(f"/user-skills/{claim_id}/evidence-links", json={"evidence_id": evidence_id}).status_code == 201


def _status(client: TestClient, claim_id: int, status: str) -> None:
    assert client.post(f"/user-skills/{claim_id}/status", json={"status": status}).status_code == 200


def _unlink(client: TestClient, claim_id: int, evidence_id: int):
    return client.delete(f"/user-skills/{claim_id}/evidence-links/{evidence_id}")


def _claim_view(client: TestClient, claim_id: int) -> dict:
    return next(c for c in client.get("/user-skills").json() if c["id"] == claim_id)


# --- unlinking ---------------------------------------------------------------------


def test_unlink_from_a_provisional_claim_keeps_the_evidence(client: TestClient, engine: Engine) -> None:
    claim_id = _claim(client, engine)
    evidence_id = _evidence(client, "Repo")
    _link(client, claim_id, evidence_id)

    response = _unlink(client, claim_id, evidence_id)

    assert response.status_code == 200
    assert response.json()["evidence_ids"] == []
    assert [e["id"] for e in client.get("/evidence").json()] == [evidence_id]  # not deleted


@pytest.mark.parametrize("status", ["verified", "partial"])
def test_unlinking_the_last_evidence_of_a_proven_claim_is_409_and_changes_nothing(
    client: TestClient, engine: Engine, status: str
) -> None:
    claim_id = _claim(client, engine)
    evidence_id = _evidence(client, "Repo")
    _link(client, claim_id, evidence_id)
    _status(client, claim_id, status)

    response = _unlink(client, claim_id, evidence_id)

    assert response.status_code == 409
    assert "last piece of evidence for Python" in response.json()["detail"]
    assert "change its status first" in response.json()["detail"]
    after = _claim_view(client, claim_id)
    assert (after["status"], after["evidence_ids"]) == (status, [evidence_id])


def test_unlinking_one_of_two_from_a_verified_claim_is_fine(client: TestClient, engine: Engine) -> None:
    claim_id = _claim(client, engine)
    first, second = _evidence(client, "Repo"), _evidence(client, "Certificate")
    _link(client, claim_id, first)
    _link(client, claim_id, second)
    _status(client, claim_id, "verified")

    response = _unlink(client, claim_id, first)

    assert response.status_code == 200
    assert (response.json()["status"], response.json()["evidence_ids"]) == ("verified", [second])


def test_lowering_the_status_first_then_unlinking_the_last_evidence_works(
    client: TestClient, engine: Engine
) -> None:
    """The path the 409 message tells the user to take."""
    claim_id = _claim(client, engine)
    evidence_id = _evidence(client, "Repo")
    _link(client, claim_id, evidence_id)
    _status(client, claim_id, "verified")

    _status(client, claim_id, "provisional")
    response = _unlink(client, claim_id, evidence_id)

    assert response.status_code == 200
    assert (response.json()["status"], response.json()["evidence_ids"]) == ("provisional", [])


def test_unlinking_evidence_that_is_not_linked_is_404(client: TestClient, engine: Engine) -> None:
    claim_id = _claim(client, engine)
    evidence_id = _evidence(client, "Repo")

    assert _unlink(client, claim_id, evidence_id).status_code == 404
    assert _unlink(client, claim_id, 999).status_code == 404
    assert _unlink(client, 999, evidence_id).status_code == 404


def test_unlinking_from_another_users_claim_is_404(client: TestClient, engine: Engine) -> None:
    with Session(engine, autoflush=False) as db:
        other = User(email="other@example.com")
        evidence = Evidence(user=other, evidence_type=EvidenceType.PROJECT, title="Not yours")
        claim = UserSkill(user=other, skill=Skill(name="Rust"))
        db.add_all([other, evidence, claim])
        db.flush()
        db.add(UserSkillEvidence(user_skill_id=claim.id, evidence_id=evidence.id))
        db.commit()
        claim_id, evidence_id = claim.id, evidence.id

    assert _unlink(client, claim_id, evidence_id).status_code == 404
    with Session(engine, autoflush=False) as db:
        assert db.scalar(select(func.count()).select_from(UserSkillEvidence)) == 1


# --- deleting ------------------------------------------------------------------------


def test_delete_unused_evidence(client: TestClient) -> None:
    evidence_id = _evidence(client, "Typo")

    assert client.delete(f"/evidence/{evidence_id}").status_code == 204
    assert client.get("/evidence").json() == []
    assert client.delete(f"/evidence/{evidence_id}").status_code == 404


def test_deleting_linked_evidence_is_409(client: TestClient, engine: Engine) -> None:
    claim_id = _claim(client, engine)
    evidence_id = _evidence(client, "Repo")
    _link(client, claim_id, evidence_id)

    response = client.delete(f"/evidence/{evidence_id}")

    assert response.status_code == 409
    assert "linked to 1 skill (unlink it first)" in response.json()["detail"]
    assert len(client.get("/evidence").json()) == 1


def test_deleting_evidence_from_comparison_history_is_409(
    client: TestClient, engine: Engine, monkeypatch
) -> None:
    """Past comparison results cite their evidence; deleting it would rewrite history."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)  # use the free skill-list reader
    claim_id = _claim(client, engine, "Python")
    evidence_id = _evidence(client, "Repo")
    _link(client, claim_id, evidence_id)
    _status(client, claim_id, "verified")
    job_id = client.post("/job-descriptions", json={"raw_text": "Need Python."}).json()["id"]
    client.post(f"/job-descriptions/{job_id}/extract")
    results = client.post(f"/job-descriptions/{job_id}/compare").json()
    assert results[0]["evidence_ids"] == [evidence_id]
    _status(client, claim_id, "provisional")
    assert _unlink(client, claim_id, evidence_id).status_code == 200  # no longer linked

    response = client.delete(f"/evidence/{evidence_id}")

    assert response.status_code == 409
    assert "part of 1 past comparison result" in response.json()["detail"]
    assert len(client.get("/evidence").json()) == 1


def test_deleting_another_users_evidence_is_404(client: TestClient, engine: Engine) -> None:
    with Session(engine, autoflush=False) as db:
        evidence = Evidence(user=User(email="other@example.com"), evidence_type=EvidenceType.PROJECT, title="X")
        db.add(evidence)
        db.commit()
        evidence_id = evidence.id

    assert client.delete(f"/evidence/{evidence_id}").status_code == 404
