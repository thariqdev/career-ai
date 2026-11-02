"""Stage 97: one account can never see or change another account's career.

Account A has a full career (the demo seed: CV skills, proof, verified skills, profile,
three jobs with requirements and comparisons, learning progress) plus a private study
link and an answer rating. Account B is brand new. B must see none of A's data in any
list, get 404 for every one of A's records by id, and leave A's data untouched.
In-memory SQLite only; real logins (the built-in-user test seam is switched off).
"""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app import demo, dependencies
from app.core.services import auth_service
from app.db.models import (
    Education,
    Evidence,
    JobDescription,
    LearningResource,
    Project,
    Skill,
    User,
    UserSkill,
    WorkExperience,
)
from app.dependencies import get_db
from app.main import app
from database import Base

PASSWORD = "a-good-password"


@pytest.fixture()
def engine(monkeypatch: pytest.MonkeyPatch) -> Iterator[Engine]:
    monkeypatch.setattr(dependencies, "ALLOW_DEFAULT_USER", False)
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False)
    demo.seed_if_empty(factory)  # A's career, on the built-in user
    with factory() as db:
        a = db.scalar(select(User))
        a.email, a.password_hash = "a@example.com", auth_service.hash_password(PASSWORD)
        db.commit()

    def override_get_db() -> Iterator[Session]:
        with factory() as db:
            yield db

    app.dependency_overrides[get_db] = override_get_db
    yield engine
    app.dependency_overrides.clear()
    engine.dispose()


@pytest.fixture()
def a(engine: Engine) -> TestClient:
    client = TestClient(app)
    assert client.post("/auth/login", json={"email": "a@example.com", "password": PASSWORD}).status_code == 200
    python = client.get("/skills").json()
    python_id = next(s["id"] for s in python if s["name"] == "Python")
    link = client.post(f"/skills/{python_id}/learning-resources",
                       json={"mode": "theory_interview", "title": "A's notes", "url": "https://example.com/a"})
    assert link.status_code == 201
    return client


@pytest.fixture()
def b(engine: Engine) -> TestClient:
    client = TestClient(app)
    assert client.post("/auth/signup", json={"email": "b@example.com", "password": PASSWORD}).status_code == 201
    return client


def _ids(engine: Engine) -> dict[str, int]:
    with Session(engine) as db:
        a_id = db.scalar(select(User.id).where(User.email == "a@example.com"))
        first = lambda model: db.scalar(select(model.id).where(model.user_id == a_id).order_by(model.id))  # noqa: E731
        return {
            "job": first(JobDescription), "evidence": first(Evidence), "project": first(Project),
            "work": first(WorkExperience), "education": first(Education), "claim": first(UserSkill),
            "link": first(LearningResource), "python": db.scalar(select(Skill.id).where(Skill.name == "Python")),
        }


def _counts(engine: Engine) -> dict[str, int]:
    with Session(engine) as db:
        return {m.__name__: db.scalar(select(func.count()).select_from(m)) for m in
                (JobDescription, Evidence, Project, WorkExperience, Education, UserSkill, LearningResource)}


def test_a_new_account_sees_none_of_another_accounts_career(a: TestClient, b: TestClient) -> None:
    assert b.get("/me").json()["email"] == "b@example.com"
    for path in ["/user-skills", "/job-descriptions", "/evidence", "/projects", "/work-experiences",
                 "/educations", "/cv/status", "/learning-progress", "/assistant/feedback", "/practice/job-questions"]:
        assert b.get(path).json() == [], path
    export = b.get("/export").json()
    assert export["user"]["email"] == "b@example.com"
    for key in ("claims", "evidence", "projects", "work_experiences", "educations", "job_descriptions",
                "cv_marks", "learning_progress", "learning_resources"):
        assert export[key] == [], key
    assert a.get("/job-descriptions").json() != []  # A still sees A's own


def test_every_one_of_another_accounts_records_is_not_found(a: TestClient, b: TestClient, engine: Engine) -> None:
    ids = _ids(engine)
    before = _counts(engine)
    job, skill = ids["job"], ids["python"]
    attempts = [
        ("get", f"/job-descriptions/{job}"), ("get", f"/job-descriptions/{job}/match"),
        ("get", f"/job-descriptions/{job}/gaps"), ("get", f"/job-descriptions/{job}/results"),
        ("get", f"/job-descriptions/{job}/interview-prep"), ("get", f"/job-descriptions/{job}/suggestions"),
        ("get", f"/job-descriptions/{job}/dismissed"), ("post", f"/job-descriptions/{job}/compare"),
        ("post", f"/job-descriptions/{job}/extract"), ("post", f"/job-descriptions/{job}/extract-new"),
        ("patch", f"/job-descriptions/{job}/application"), ("delete", f"/job-descriptions/{job}/dismissed/{skill}"),
        ("delete", f"/job-descriptions/{job}/requirements/1"), ("delete", f"/job-descriptions/{job}"),
        ("patch", f"/evidence/{ids['evidence']}"), ("delete", f"/evidence/{ids['evidence']}"),
        ("patch", f"/projects/{ids['project']}"), ("delete", f"/projects/{ids['project']}"),
        ("patch", f"/work-experiences/{ids['work']}"), ("delete", f"/work-experiences/{ids['work']}"),
        ("patch", f"/educations/{ids['education']}"), ("delete", f"/educations/{ids['education']}"),
        ("delete", f"/user-skills/{ids['claim']}"), ("post", f"/user-skills/{ids['claim']}/status"),
        ("post", f"/user-skills/{ids['claim']}/evidence-links"),
        ("delete", f"/user-skills/{ids['claim']}/evidence-links/{ids['evidence']}"),
        ("delete", f"/learning-resources/{ids['link']}"),
    ]
    bodies = {"post": {"status": "verified", "evidence_id": ids["evidence"]}, "patch": {"status": "applied", "title": "x"}}
    for method, path in attempts:
        kwargs = {"json": bodies[method]} if method in bodies else {}
        response = getattr(b, method)(path, **kwargs)
        assert response.status_code == 404, f"{method.upper()} {path} -> {response.status_code}"
    assert _counts(engine) == before  # nothing of A's changed


def test_shared_skills_show_only_your_own_status_links_and_path(a: TestClient, b: TestClient, engine: Engine) -> None:
    python = _ids(engine)["python"]

    links = b.get(f"/skills/{python}/learning-resources").json()
    path = b.get(f"/skills/{python}/learning-path").json()

    assert all(mode["resources"] == [] for mode in links["modes"])  # A's link is private
    assert b.get(f"/skills/{python}/cv-status").json()["knowledge_status"] is None  # B has no claim
    assert a.get(f"/skills/{python}/cv-status").json()["knowledge_status"] is not None  # A's is A's
    assert not any(step["state"] == "done" for step in path["steps"])
    a_links = a.get(f"/skills/{python}/learning-resources").json()
    assert any(r["title"] == "A's notes" for mode in a_links["modes"] for r in mode["resources"])


def test_the_assistant_answers_from_your_data_only(a: TestClient, b: TestClient) -> None:
    verified = b.post("/assistant/ask", json={"question": "Which skills are verified?"}).json()["answer"]
    name = b.post("/assistant/ask", json={"question": "What is my name?"}).json()["answer"]
    jobs = b.post("/assistant/ask", json={"question": "What am I missing for my jobs?"}).json()["answer"]

    for answer in (verified, name, jobs):  # nothing of A's: name, proof, jobs, or A's skills as "yours"
        for word in ("Alex", "Northwind", "TaskFlow", "Brightlane", "FastAPI", "Docker"):
            assert word not in answer, (word, answer)
    assert "Verified (proven) skills: 0" in verified
    assert "Northwind" in a.post("/assistant/ask", json={"question": "What am I missing for my jobs?"}).json()["answer"]


def test_a_skill_another_account_uses_cant_be_renamed_but_your_own_can(a: TestClient, b: TestClient, engine: Engine) -> None:
    python = _ids(engine)["python"]

    assert b.patch(f"/skills/{python}", json={"name": "Snake"}).status_code == 409
    assert b.post(f"/skills/{python}/aliases", json={"alias": "py3"}).status_code == 409
    assert b.delete(f"/skills/{python}").status_code == 409
    mine = b.post("/skills", json={"name": "Elixir"}).json()["id"]
    assert b.patch(f"/skills/{mine}", json={"name": "Elixir Lang"}).status_code == 200
    with Session(engine) as db:
        assert db.get(Skill, python).name == "Python"
