"""Editing (PATCH) evidence and profile records: change only what's sent, keep every rule.

Same TestClient + dependency_overrides[get_db] + StaticPool in-memory SQLite pattern as
the other API tests.
"""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.services import skill_service
from app.db.models import Project, User
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


PROJECT = {
    "name": "FundsApp",
    "role": "Solo dev",
    "url": "https://github.com/me/fundsapp",
    "description": "Budget tracker",
    "start_date": "2024-01-01",
    "end_date": "2024-06-30",
}


def _project(client: TestClient) -> dict:
    return client.post("/projects", json=PROJECT).json()


def _get(client: TestClient, path: str, record_id: int) -> dict:
    return next(r for r in client.get(path).json() if r["id"] == record_id)


# --- profile records: only what's sent changes ---------------------------------------


def test_changing_one_field_leaves_the_rest_alone(client: TestClient) -> None:
    project = _project(client)

    response = client.patch(f"/projects/{project['id']}", json={"role": "  Lead  "})

    assert response.status_code == 200
    assert response.json() == {**project, "role": "Lead"}


def test_null_clears_an_optional_field_and_leaving_it_out_keeps_it(client: TestClient) -> None:
    project = _project(client)

    after = client.patch(f"/projects/{project['id']}", json={"role": None, "description": ""}).json()

    assert (after["role"], after["description"]) == (None, None)
    assert (after["url"], after["name"]) == (project["url"], project["name"])


@pytest.mark.parametrize(
    ("path", "body", "field_change", "message"),
    [
        ("/projects", PROJECT, {"name": "   "}, "Project name must not be blank."),
        ("/projects", PROJECT, {"name": None}, "Project name must not be blank."),
        (
            "/work-experiences",
            {"company": "Acme", "role": "Dev", "start_date": "2022-01-01"},
            {"role": None},
            "Role must not be blank.",
        ),
        (
            "/work-experiences",
            {"company": "Acme", "role": "Dev", "start_date": "2022-01-01"},
            {"start_date": None},
            "Start date must not be blank.",
        ),
        ("/educations", {"institution": "Uni"}, {"institution": ""}, "Institution must not be blank."),
    ],
)
def test_required_fields_cant_be_cleared(client: TestClient, path, body, field_change, message) -> None:
    record = client.post(path, json=body).json()

    response = client.patch(f"{path}/{record['id']}", json=field_change)

    assert response.status_code == 422
    assert response.json()["detail"] == message
    assert _get(client, path, record["id"]) == record


@pytest.mark.parametrize(
    "change",
    [
        {"end_date": "2023-12-31"},  # new end before the existing start
        {"start_date": "2024-07-01"},  # new start after the existing end
    ],
)
def test_date_order_is_checked_on_the_record_as_it_will_be(client: TestClient, change: dict) -> None:
    project = _project(client)

    response = client.patch(f"/projects/{project['id']}", json=change)

    assert response.status_code == 422
    assert _get(client, "/projects", project["id"]) == project


def test_project_link_must_stay_a_web_link(client: TestClient) -> None:
    project = _project(client)

    assert client.patch(f"/projects/{project['id']}", json={"url": "javascript:alert(1)"}).status_code == 422
    good = client.patch(f"/projects/{project['id']}", json={"url": " https://gitlab.com/me/x "})
    assert good.json()["url"] == "https://gitlab.com/me/x"


def test_editing_someone_elses_or_a_missing_record_is_404(client: TestClient, engine: Engine) -> None:
    with Session(engine, autoflush=False) as db:
        other = Project(user=User(email="other@example.com"), name="Not yours")
        db.add(other)
        db.commit()
        other_id = other.id

    assert client.patch(f"/projects/{other_id}", json={"name": "Mine now"}).status_code == 404
    assert client.patch("/projects/999", json={"name": "X"}).status_code == 404
    assert client.patch("/work-experiences/999", json={"role": "X"}).status_code == 404
    assert client.patch("/educations/999", json={"degree": "X"}).status_code == 404


# --- evidence ----------------------------------------------------------------------


def _evidence(client: TestClient, **fields) -> dict:
    body = {"evidence_type": "project", "title": "Repo", "description": "My code", **fields}
    response = client.post("/evidence", json=body)
    assert response.status_code == 201, response.text
    return response.json()


def test_edit_evidence_changes_only_what_is_sent(client: TestClient) -> None:
    evidence = _evidence(client, url="https://github.com/me/repo")

    after = client.patch(f"/evidence/{evidence['id']}", json={"title": " Repo (fixed) ", "description": None}).json()

    assert after == {**evidence, "title": "Repo (fixed)", "description": None}


@pytest.mark.parametrize(
    ("change", "status"),
    [({"title": "  "}, 422), ({"title": None}, 422), ({"evidence_type": None}, 422), ({"url": "ftp://x"}, 422)],
)
def test_edit_evidence_keeps_its_rules(client: TestClient, change: dict, status: int) -> None:
    evidence = _evidence(client)

    assert client.patch(f"/evidence/{evidence['id']}", json=change).status_code == status
    assert client.get("/evidence").json() == [evidence]


def test_creating_evidence_now_checks_title_and_link_too(client: TestClient) -> None:
    assert client.post("/evidence", json={"evidence_type": "project", "title": "  "}).status_code == 422
    assert (
        client.post(
            "/evidence", json={"evidence_type": "project", "title": "X", "url": "javascript:alert(1)"}
        ).status_code
        == 422
    )
    blank_link = _evidence(client, url="   ")
    assert blank_link["url"] is None


def test_switching_source_needs_the_old_one_cleared(client: TestClient) -> None:
    project_id = client.post("/projects", json={"name": "FundsApp"}).json()["id"]
    education_id = client.post("/educations", json={"institution": "Uni"}).json()["id"]
    evidence = _evidence(client, project_id=project_id)

    both = client.patch(f"/evidence/{evidence['id']}", json={"education_id": education_id})
    assert both.status_code == 422
    assert "at most one source" in both.json()["detail"]

    switched = client.patch(f"/evidence/{evidence['id']}", json={"project_id": None, "education_id": education_id})
    assert switched.status_code == 200
    assert (switched.json()["project_id"], switched.json()["education_id"]) == (None, education_id)


def test_pointing_evidence_at_someone_elses_record_is_404(client: TestClient, engine: Engine) -> None:
    with Session(engine, autoflush=False) as db:
        other = Project(user=User(email="other@example.com"), name="Not yours")
        db.add(other)
        db.commit()
        other_id = other.id
    evidence = _evidence(client)

    assert client.patch(f"/evidence/{evidence['id']}", json={"project_id": other_id}).status_code == 404
    assert client.get("/evidence").json() == [evidence]


def test_editing_evidence_never_changes_a_skills_status(client: TestClient, engine: Engine) -> None:
    with Session(engine, autoflush=False) as db:
        skill_id = skill_service.create_skill(db, "Python").id
        db.commit()
    claim_id = client.post("/user-skills", json={"skill_id": skill_id}).json()["id"]
    evidence = _evidence(client)
    client.post(f"/user-skills/{claim_id}/evidence-links", json={"evidence_id": evidence["id"]})
    client.post(f"/user-skills/{claim_id}/status", json={"status": "verified"})

    client.patch(f"/evidence/{evidence['id']}", json={"title": "Renamed", "evidence_type": "certification"})

    claim = client.get("/user-skills").json()[0]
    assert (claim["status"], claim["evidence_ids"]) == ("verified", [evidence["id"]])
