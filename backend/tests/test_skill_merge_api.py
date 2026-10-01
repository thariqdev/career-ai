"""HTTP tests for merging a duplicate skill into another: everything moves, nothing is invented.

Same TestClient + dependency_overrides[get_db] + StaticPool in-memory SQLite pattern as
the other API tests.
"""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.services import skill_service
from app.db.models import CVSkillPresence, JobRequirement, LearningResource, Skill, User, UserSkill
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


def _skill(engine: Engine, name: str) -> int:
    with Session(engine, autoflush=False) as db:
        skill_id = skill_service.create_skill(db, name).id
        db.commit()
    return skill_id


def _merge(client: TestClient, source_id: int, target_id: int):
    return client.post(f"/skills/{source_id}/merge-into/{target_id}")


def _claim(client: TestClient, skill_id: int) -> int:
    return client.post("/user-skills", json={"skill_id": skill_id}).json()["id"]


def _progress(client: TestClient, skill_id: int, status: str) -> None:
    assert client.put(f"/skills/{skill_id}/learning-progress", json={"status": status}).status_code == 200


def _progress_by_skill(client: TestClient) -> dict[int, str]:
    return {p["skill_id"]: p["status"] for p in client.get("/learning-progress").json()}


def _cv(client: TestClient, skill_id: int, present: bool) -> None:
    assert client.patch(f"/skills/{skill_id}/cv-presence", json={"present": present}).status_code == 200


def _skill_names(client: TestClient) -> list[str]:
    return [s["name"] for s in client.get("/skills").json()]


# --- what moves -----------------------------------------------------------------------


def test_merge_moves_aliases_and_keeps_the_old_name_as_an_alias(client: TestClient, engine: Engine) -> None:
    target_id = _skill(engine, "Python")
    source_id = _skill(engine, "pytho n")
    client.post(f"/skills/{source_id}/aliases", json={"alias": "py3"})

    response = _merge(client, source_id, target_id)

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == target_id
    assert body["name"] == "Python"
    assert sorted(body["aliases"]) == ["py3", "pytho n"]
    assert _skill_names(client) == ["Python"]
    # The old spelling now resolves to the target, so later postings still match.
    assert client.get("/skills/resolve", params={"text": "Pytho N"}).json()["id"] == target_id


def test_merge_repoints_job_requirements_and_their_gaps(client: TestClient, engine: Engine) -> None:
    target_id = _skill(engine, "Python")
    source_id = _skill(engine, "Pythonn")
    job_id = client.post("/job-descriptions", json={"raw_text": "Need Pythonn."}).json()["id"]
    client.post(f"/job-descriptions/{job_id}/extract")
    with Session(engine) as db:
        assert db.scalars(select(JobRequirement.skill_id)).all() == [source_id]

    assert _merge(client, source_id, target_id).status_code == 200

    with Session(engine) as db:
        assert db.scalars(select(JobRequirement.skill_id)).all() == [target_id]
    client.post(f"/job-descriptions/{job_id}/compare")
    gaps = client.get(f"/job-descriptions/{job_id}/gaps").json()
    assert [g["requirement"]["skill_name"] for g in gaps] == ["Python"]


def test_a_claim_moves_with_its_status_evidence_and_comparison_history(
    client: TestClient, engine: Engine
) -> None:
    target_id = _skill(engine, "Python")
    source_id = _skill(engine, "Pythonn")
    claim_id = _claim(client, source_id)
    evidence_id = client.post("/evidence", json={"evidence_type": "project", "title": "Repo"}).json()["id"]
    client.post(f"/user-skills/{claim_id}/evidence-links", json={"evidence_id": evidence_id})
    client.post(f"/user-skills/{claim_id}/status", json={"status": "verified"})
    job_id = client.post("/job-descriptions", json={"raw_text": "Need Pythonn."}).json()["id"]
    client.post(f"/job-descriptions/{job_id}/extract")
    before = client.post(f"/job-descriptions/{job_id}/compare").json()

    assert _merge(client, source_id, target_id).status_code == 200

    [claim] = client.get("/user-skills").json()
    assert claim["id"] == claim_id
    assert claim["skill_id"] == target_id
    assert claim["status"] == "verified"
    assert claim["evidence_ids"] == [evidence_id]
    assert client.get(f"/job-descriptions/{job_id}/results").json() == before


def test_saved_links_move_and_exact_duplicates_are_dropped(client: TestClient, engine: Engine) -> None:
    target_id = _skill(engine, "Python")
    source_id = _skill(engine, "Pythonn")
    shared = {"mode": "theory_interview", "title": "Docs", "url": "https://docs.python.org/"}
    client.post(f"/skills/{target_id}/learning-resources", json=shared)
    client.post(f"/skills/{source_id}/learning-resources", json={**shared, "title": "Docs again"})
    client.post(
        f"/skills/{source_id}/learning-resources",
        json={"mode": "technical_practical", "title": "Kata", "url": "https://example.com/kata"},
    )

    assert _merge(client, source_id, target_id).status_code == 200

    with Session(engine) as db:
        rows = db.scalars(select(LearningResource).order_by(LearningResource.url)).all()
        assert [(r.skill_id, r.title, r.url) for r in rows] == [
            (target_id, "Docs", "https://docs.python.org/"),  # the target's own copy is kept
            (target_id, "Kata", "https://example.com/kata"),
        ]


# --- where both skills hold a row --------------------------------------------------------


@pytest.mark.parametrize(
    ("source_status", "target_status"),
    [("finished", "studying"), ("studying", "finished"), ("studying", "studying")],
)
def test_progress_keeps_the_further_along_one(
    client: TestClient, engine: Engine, source_status: str, target_status: str
) -> None:
    target_id = _skill(engine, "Python")
    source_id = _skill(engine, "Pythonn")
    _progress(client, source_id, source_status)
    _progress(client, target_id, target_status)

    assert _merge(client, source_id, target_id).status_code == 200

    expected = "finished" if "finished" in (source_status, target_status) else "studying"
    assert _progress_by_skill(client) == {target_id: expected}


def test_progress_only_on_the_duplicate_moves(client: TestClient, engine: Engine) -> None:
    target_id = _skill(engine, "Python")
    source_id = _skill(engine, "Pythonn")
    _progress(client, source_id, "studying")

    assert _merge(client, source_id, target_id).status_code == 200

    assert _progress_by_skill(client) == {target_id: "studying"}


@pytest.mark.parametrize(
    ("source_present", "target_present", "expected"),
    [(True, False, True), (False, True, True), (False, False, False), (True, None, True)],
)
def test_cv_mark_is_present_if_either_was(
    client: TestClient,
    engine: Engine,
    source_present: bool,
    target_present: bool | None,
    expected: bool,
) -> None:
    target_id = _skill(engine, "Python")
    source_id = _skill(engine, "Pythonn")
    _cv(client, source_id, source_present)
    if target_present is not None:
        _cv(client, target_id, target_present)

    assert _merge(client, source_id, target_id).status_code == 200

    with Session(engine) as db:
        rows = db.scalars(select(CVSkillPresence)).all()
        assert [(r.skill_id, r.present) for r in rows] == [(target_id, expected)]


# --- refused ------------------------------------------------------------------------------


def test_both_claimed_is_refused_and_nothing_changes(client: TestClient, engine: Engine) -> None:
    target_id = _skill(engine, "Python")
    source_id = _skill(engine, "Pythonn")
    _claim(client, target_id)
    _claim(client, source_id)
    _progress(client, source_id, "finished")

    response = _merge(client, source_id, target_id)

    assert response.status_code == 409
    assert "Both" in response.json()["detail"]
    assert _skill_names(client) == ["Python", "Pythonn"]
    assert sorted(c["skill_id"] for c in client.get("/user-skills").json()) == [target_id, source_id]
    assert _progress_by_skill(client) == {source_id: "finished"}


def test_claims_by_different_users_are_not_a_conflict(client: TestClient, engine: Engine) -> None:
    target_id = _skill(engine, "Python")
    source_id = _skill(engine, "Pythonn")
    my_claim_id = _claim(client, source_id)
    with Session(engine, autoflush=False) as db:
        db.add(UserSkill(user=User(email="other@example.com"), skill_id=target_id))
        db.commit()

    assert _merge(client, source_id, target_id).status_code == 200

    with Session(engine) as db:
        assert {c.skill_id for c in db.scalars(select(UserSkill))} == {target_id}
        assert db.get(UserSkill, my_claim_id).skill_id == target_id


def test_merging_into_itself_is_refused(client: TestClient, engine: Engine) -> None:
    skill_id = _skill(engine, "Python")

    response = _merge(client, skill_id, skill_id)

    assert response.status_code == 422
    assert _skill_names(client) == ["Python"]


def test_unknown_skills_are_404(client: TestClient, engine: Engine) -> None:
    skill_id = _skill(engine, "Python")

    assert _merge(client, 999, skill_id).status_code == 404
    assert _merge(client, skill_id, 999).status_code == 404
    with Session(engine) as db:
        assert db.scalars(select(Skill.name)).all() == ["Python"]
