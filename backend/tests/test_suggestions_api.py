"""Tests for skill suggestions: catalogue skills a CV or posting mentions that aren't saved.

Suggestions are read-only and never add anything. Same TestClient + StaticPool
in-memory SQLite pattern as the other API tests.
"""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.services import skill_service, suggestion_service
from app.core.skill_catalog import CATALOG, EXACT_CASE
from app.db.models import JobDescription, Skill, User
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


def _skill(engine: Engine, name: str, *aliases: str) -> None:
    with Session(engine, autoflush=False) as db:
        skill = skill_service.create_skill(db, name)
        for alias in aliases:
            skill_service.add_alias(db, skill, alias)
        db.commit()


def _suggest(engine: Engine, text: str) -> list[tuple[str, str]]:
    with Session(engine) as db:
        return [(s.name, s.matched_text) for s in suggestion_service.suggest(db, text)]


CV = (
    "Backend developer. Built REST APIs with FastAPI and Node.js; front ends in React and JS.\n"
    "Deployed on AWS with Docker and K8s. Version control with Git. I go running daily,\n"
    "enjoy a swift response, and like to express ideas clearly. Spring semester intern at R&D lab."
)


# --- the matcher --------------------------------------------------------------------------


def test_finds_catalogue_skills_in_text_order_with_the_texts_own_words(engine: Engine) -> None:
    found = _suggest(engine, CV)

    assert found == [
        ("REST APIs", "REST APIs"),
        ("FastAPI", "FastAPI"),
        ("Node.js", "Node.js"),
        ("React", "React"),
        ("JavaScript", "JS"),
        ("AWS", "AWS"),
        ("Docker", "Docker"),
        ("Kubernetes", "K8s"),
        ("Git", "Git"),
    ]


def test_everyday_words_are_not_skills(engine: Engine) -> None:
    """"go running", "swift response", "express ideas", "Spring semester", "R&D"."""
    names = {name for name, _ in _suggest(engine, CV)}

    assert names.isdisjoint({"Go", "Swift", "Express", "Spring Boot"})


def test_everyday_words_match_when_written_as_the_skill(engine: Engine) -> None:
    names = [name for name, _ in _suggest(engine, "Services in Go and Swift; Express APIs.")]

    assert names == ["Go", "Swift", "Express"]


def test_whole_terms_only(engine: Engine) -> None:
    names = [name for name, _ in _suggest(engine, "JavaScript, Pythonic code, C++ and C#.")]

    assert names == ["JavaScript", "C++", "C#"]  # not Java inside JavaScript, not Python


def test_saved_skills_and_their_nicknames_are_never_suggested(engine: Engine) -> None:
    _skill(engine, "Python")
    _skill(engine, "Kube", "K8s")  # saved under another name, but owns the spelling "K8s"

    names = [name for name, _ in _suggest(engine, "Python, K8s, Kubernetes and Docker.")]

    assert names == ["Docker"]  # Kubernetes is skipped too: one of its spellings is yours


def test_suggesting_never_adds_anything(engine: Engine) -> None:
    _suggest(engine, CV)

    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(Skill)) == 0


def test_the_catalogue_is_well_formed() -> None:
    names = [skill.name for skill in CATALOG]
    assert len(names) == len(set(names))
    spellings = [skill_service.normalize_text(t) for skill in CATALOG for t in skill.terms]
    assert len(spellings) == len(set(spellings)), "a spelling may belong to one skill only"
    assert all(skill.category for skill in CATALOG)
    every_term = {t for skill in CATALOG for t in skill.terms}
    assert EXACT_CASE <= every_term
    # Left out on purpose: they match too much ordinary text.
    assert {"C", "R", "Less", "Spring"}.isdisjoint(every_term)


# --- through the API ----------------------------------------------------------------------


def test_cv_scan_returns_suggestions_alongside_saved_matches(client: TestClient, engine: Engine) -> None:
    _skill(engine, "Python")

    body = client.post("/cv/scan", data={"text": "Python and Django developer, some JS."}).json()

    assert [f["skill_name"] for f in body["found"]] == ["Python"]
    assert body["suggestions"] == [
        {"name": "Django", "category": "Backend", "matched_text": "Django"},
        {"name": "JavaScript", "category": "Languages", "matched_text": "JS"},
    ]


def test_adding_a_suggestion_then_rescanning_finds_it(client: TestClient) -> None:
    """The page adds the skill, plus the CV's own spelling as a nickname when different."""
    text = "Frontend work in JS and React."
    client.post("/skills", json={"name": "JavaScript", "category": "Languages"})
    skill_id = next(s["id"] for s in client.get("/skills").json() if s["name"] == "JavaScript")
    client.post(f"/skills/{skill_id}/aliases", json={"alias": "JS"})

    body = client.post("/cv/scan", data={"text": text}).json()

    assert [(f["skill_name"], f["matched_text"]) for f in body["found"]] == [("JavaScript", "JS")]
    assert [s["name"] for s in body["suggestions"]] == ["React"]


def test_job_suggestions_endpoint(client: TestClient, engine: Engine) -> None:
    job_id = client.post("/job-descriptions", json={"raw_text": "Need Kotlin and GraphQL."}).json()["id"]

    response = client.get(f"/job-descriptions/{job_id}/suggestions")

    assert response.status_code == 200
    assert [s["name"] for s in response.json()] == ["Kotlin", "GraphQL"]


def test_job_suggestions_of_another_users_job_are_404(client: TestClient, engine: Engine) -> None:
    with Session(engine, autoflush=False) as db:
        job = JobDescription(user=User(email="other@example.com"), raw_text="Kotlin")
        db.add(job)
        db.commit()
        job_id = job.id

    assert client.get(f"/job-descriptions/{job_id}/suggestions").status_code == 404
    assert client.get("/job-descriptions/999/suggestions").status_code == 404
