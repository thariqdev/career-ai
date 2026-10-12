"""Stage 90: "Add to my skills" for a skill a job asks for. Catalogue skills only, never a
duplicate, and NEVER a claim or a CV mark (the project's core rule: tracking isn't proof)."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.dependencies import get_db
from app.main import app
from database import Base


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    engine: Engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)

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
        engine.dispose()


def _add(client: TestClient, name: str):
    return client.post("/skills/from-catalogue", json={"name": name})


def test_adding_saves_the_catalogue_skill_with_its_category_and_nicknames(client: TestClient) -> None:
    response = _add(client, "js")  # a nickname finds the catalogue entry

    assert response.status_code == 200
    body = response.json()
    assert body["created"] is True
    assert body["skill"]["name"] == "JavaScript" and body["skill"]["category"]
    assert "JS" in body["skill"]["aliases"]


def test_adding_twice_or_by_another_name_never_duplicates(client: TestClient) -> None:
    first = _add(client, "JavaScript").json()
    again = _add(client, "JS").json()

    assert again == {"skill": first["skill"], "created": False}
    assert [s["name"] for s in client.get("/skills").json()] == ["JavaScript"]


def test_only_catalogue_skills_can_be_added_this_way(client: TestClient) -> None:
    response = _add(client, "Ignore previous instructions")

    assert response.status_code == 404
    assert "isn't a skill in the catalogue" in response.json()["detail"]
    assert client.get("/skills").json() == []


def test_adding_is_not_a_claim_not_a_cv_mark_and_doesnt_change_the_match(client: TestClient) -> None:
    client.post("/cv/add-all", data={"text": "Python."})
    job = client.post("/job-descriptions", json={"raw_text": "Backend: Python and AWS.", "title": "Backend"}).json()["id"]
    before = client.get(f"/job-descriptions/{job}/match").json()
    gap = next(g for g in client.get(f"/job-descriptions/{job}/gaps").json() if g["skill_name"] == "AWS")
    assert gap["skill_id"] is None  # "not in your skills yet"

    added = _add(client, gap["skill_name"]).json()["skill"]

    claims = {c["skill_id"] for c in client.get("/user-skills").json()}
    on_cv = {s["skill_id"] for s in client.get("/cv/status").json() if s["cv_status"] == "present"}
    assert added["id"] not in claims and added["id"] not in on_cv
    after = client.get(f"/job-descriptions/{job}/match").json()
    assert (after["percent"], after["total"]) == (before["percent"], before["total"])  # tracking isn't proof
    still = next(g for g in client.get(f"/job-descriptions/{job}/gaps").json() if g["skill_name"] == "AWS")
    assert still["skill_id"] == added["id"] and still["status"] == "no_claim"  # still a gap, now a real skill
