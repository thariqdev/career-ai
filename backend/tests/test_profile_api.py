"""HTTP tests for profile records (projects, work experience, education) and evidence sources.

Same TestClient + dependency_overrides[get_db] + StaticPool in-memory SQLite pattern as
the other API tests.
"""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.models import Education, Evidence, Project, User, WorkExperience
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


# path, model, a minimal valid body, the required field to blank, its error label,
# and the Evidence field that points at this kind of record.
KINDS = [
    ("/projects", Project, {"name": "FundsApp"}, "name", "Project name", "project_id"),
    (
        "/work-experiences",
        WorkExperience,
        {"company": "Acme", "role": "Engineer", "start_date": "2022-01-01"},
        "company",
        "Company",
        "work_experience_id",
    ),
    ("/educations", Education, {"institution": "State University"}, "institution", "Institution", "education_id"),
]
by_kind = pytest.mark.parametrize(
    ("path", "model", "body", "required", "label", "evidence_field"),
    KINDS,
    ids=["project", "work", "education"],
)


def _count(engine: Engine, model: type) -> int:
    with Session(engine, autoflush=False) as db:
        return db.scalar(select(func.count()).select_from(model))


# --- add / list ------------------------------------------------------------------


@by_kind
def test_add_then_list(client: TestClient, path, model, body, required, label, evidence_field) -> None:
    response = client.post(path, json=body)

    assert response.status_code == 201
    assert client.get(path).json() == [response.json()]


@by_kind
def test_blank_required_field_is_422_and_saves_nothing(
    client: TestClient, engine: Engine, path, model, body, required, label, evidence_field
) -> None:
    response = client.post(path, json={**body, required: "   "})

    assert response.status_code == 422
    assert response.json()["detail"] == f"{label} must not be blank."
    assert _count(engine, model) == 0


@by_kind
def test_end_date_before_start_date_is_422(
    client: TestClient, engine: Engine, path, model, body, required, label, evidence_field
) -> None:
    response = client.post(path, json={**body, "start_date": "2023-06-01", "end_date": "2023-05-31"})

    assert response.status_code == 422
    assert "end date" in response.json()["detail"]
    assert _count(engine, model) == 0


def test_same_start_and_end_date_is_fine(client: TestClient) -> None:
    response = client.post("/projects", json={"name": "Hackathon", "start_date": "2024-03-02", "end_date": "2024-03-02"})

    assert response.status_code == 201


def test_work_experience_needs_a_start_date(client: TestClient) -> None:
    assert client.post("/work-experiences", json={"company": "Acme", "role": "Dev"}).status_code == 422


def test_blank_optional_text_is_stored_as_null_and_text_is_trimmed(client: TestClient) -> None:
    body = client.post(
        "/projects", json={"name": "  FundsApp ", "role": "   ", "description": "", "url": "  "}
    ).json()

    assert (body["name"], body["role"], body["description"], body["url"]) == ("FundsApp", None, None, None)


def test_project_link_must_be_a_web_link(client: TestClient, engine: Engine) -> None:
    good = client.post("/projects", json={"name": "A", "url": " https://github.com/me/a "})
    assert good.status_code == 201
    assert good.json()["url"] == "https://github.com/me/a"

    for bad in ["javascript:alert(1)", "ftp://files.example.com", "github.com/me/a"]:
        assert client.post("/projects", json={"name": "B", "url": bad}).status_code == 422
    assert _count(engine, Project) == 1


def test_list_is_most_recent_first_with_undated_last(client: TestClient) -> None:
    for name, start in [("Old", "2019-01-01"), ("Undated", None), ("New", "2024-01-01")]:
        client.post("/projects", json={"name": name, "start_date": start})

    assert [p["name"] for p in client.get("/projects").json()] == ["New", "Old", "Undated"]


# --- scoping -----------------------------------------------------------------------


def _other_users_project(engine: Engine) -> int:
    with Session(engine, autoflush=False) as db:
        project = Project(user=User(email="other@example.com"), name="Not yours")
        db.add(project)
        db.commit()
        return project.id


def test_you_only_see_and_can_remove_your_own_records(client: TestClient, engine: Engine) -> None:
    other_id = _other_users_project(engine)

    assert client.get("/projects").json() == []
    assert client.delete(f"/projects/{other_id}").status_code == 404
    assert _count(engine, Project) == 1


# --- removing ------------------------------------------------------------------------


@by_kind
def test_remove_an_unused_record(
    client: TestClient, engine: Engine, path, model, body, required, label, evidence_field
) -> None:
    record_id = client.post(path, json=body).json()["id"]

    assert client.delete(f"{path}/{record_id}").status_code == 204
    assert client.get(path).json() == []
    assert client.delete(f"{path}/{record_id}").status_code == 404


@by_kind
def test_removing_a_record_evidence_comes_from_is_409(
    client: TestClient, engine: Engine, path, model, body, required, label, evidence_field
) -> None:
    record_id = client.post(path, json=body).json()["id"]
    for title in ["Proof one", "Proof two"]:
        client.post("/evidence", json={"evidence_type": "project", "title": title, evidence_field: record_id})

    response = client.delete(f"{path}/{record_id}")

    assert response.status_code == 409
    assert "2 pieces of evidence" in response.json()["detail"]
    assert _count(engine, model) == 1


def test_in_use_message_is_singular_for_one_piece_of_evidence(client: TestClient) -> None:
    project_id = client.post("/projects", json={"name": "FundsApp"}).json()["id"]
    client.post("/evidence", json={"evidence_type": "project", "title": "Proof", "project_id": project_id})

    detail = client.delete(f"/projects/{project_id}").json()["detail"]

    assert detail == 'Project "FundsApp" can\'t be removed because 1 piece of evidence comes from it.'


# --- evidence sources ---------------------------------------------------------------


@by_kind
def test_evidence_can_come_from_a_record_and_says_so(
    client: TestClient, path, model, body, required, label, evidence_field
) -> None:
    record_id = client.post(path, json=body).json()["id"]

    evidence = client.post(
        "/evidence", json={"evidence_type": "project", "title": "Proof", evidence_field: record_id}
    ).json()

    sources = {f: evidence[f] for f in ["project_id", "work_experience_id", "education_id"]}
    assert sources == {**{f: None for f in sources}, evidence_field: record_id}


def test_evidence_with_two_sources_is_422_and_saves_nothing(client: TestClient, engine: Engine) -> None:
    project_id = client.post("/projects", json={"name": "FundsApp"}).json()["id"]
    education_id = client.post("/educations", json={"institution": "Uni"}).json()["id"]

    response = client.post(
        "/evidence",
        json={"evidence_type": "project", "title": "Proof", "project_id": project_id, "education_id": education_id},
    )

    assert response.status_code == 422
    assert _count(engine, Evidence) == 0


def test_the_database_itself_refuses_two_sources(engine: Engine) -> None:
    """The check constraint is the backstop if a code path ever skips the API schema."""
    with Session(engine, autoflush=False) as db:
        user = User(email="me@example.com")
        project = Project(user=user, name="P")
        education = Education(user=user, institution="E")
        db.add_all([user, project, education])
        db.flush()
        db.add(
            Evidence(
                user=user,
                evidence_type=EvidenceType.PROJECT,
                title="Two sources",
                project=project,
                education=education,
            )
        )
        with pytest.raises(IntegrityError):
            db.flush()
