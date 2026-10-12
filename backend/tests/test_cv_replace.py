"""Stage 95: "Start fresh with this CV" replaces one person's career with another's.

Person A is the demo career (proof, verified skills, jobs with comparison history,
learning progress), seeded into a throwaway in-memory database; never the live one.
"""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app import demo
from app.db.models import (
    AssistantFeedback,
    ComparisonResult,
    CVSkillPresence,
    Education,
    Evidence,
    JobDescription,
    JobRequirement,
    LearningProgress,
    LearningResource,
    Project,
    Skill,
    SkillAlias,
    User,
    UserSkill,
    WorkExperience,
)
from app.db.models.enums import LearningMode
from app.dependencies import get_db
from app.main import app
from database import Base

FRIEND_CV = """Priya Raman
Java and Spring Boot developer, also AWS and Kotlin.

Experience
Software Engineer, Acme Payments
Jan 2021 - Present
Built payment services in Java and Spring Boot on AWS.

Education
BSc Computer Science, Riverdale College
2016 - 2020
"""


@pytest.fixture()
def engine() -> Iterator[Engine]:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False)
    demo.seed_if_empty(factory)  # person A: a full career
    with factory() as db:
        python = db.scalar(select(Skill).where(Skill.name == "Python"))
        db.add(LearningResource(skill=python, mode=LearningMode.THEORY_INTERVIEW, title="Python docs",
                                url="https://docs.python.org"))
        db.add(AssistantFeedback(user_id=db.scalar(select(User.id)), message_id="m1", rating="up",
                                 question="q", answer="a", sources=[], retrieval="bm25", written_by="notes"))
        db.commit()
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


def _count(engine: Engine, model) -> int:
    with Session(engine) as db:
        return db.scalar(select(func.count()).select_from(model))


def test_a_new_cv_replaces_the_previous_person_completely(client: TestClient, engine: Engine) -> None:
    before = {m: _count(engine, m) for m in (JobDescription, UserSkill, Evidence, Project, ComparisonResult)}
    assert all(before.values())  # person A really has data of every kind

    response = client.post("/cv/replace", data={"text": FRIEND_CV})

    assert response.status_code == 200, response.json()
    body = response.json()
    assert body["removed"]["jobs"] == 3 and body["removed"]["evidence"] == 2
    for model in (JobDescription, JobRequirement, ComparisonResult, Evidence, Project, WorkExperience,
                  Education, LearningProgress, AssistantFeedback):
        assert _count(engine, model) == 0, model.__name__  # nothing of person A is left
    assert client.get("/me").json()["full_name"] == "Priya Raman"
    claims = {c["skill_id"]: c["status"] for c in client.get("/user-skills").json()}
    names = {s["id"]: s["name"] for s in client.get("/skills").json()}
    claimed = {names[i] for i in claims}
    assert {"Java", "AWS", "Kotlin"} <= claimed and "Python" not in claimed and "React" not in claimed
    assert set(claims.values()) == {"provisional"}  # a CV is never proof
    on_cv = {p["skill_name"] for p in client.get("/cv/status").json() if p["cv_status"] == "present"}
    assert "Python" not in on_cv and "Java" in on_cv


def test_the_new_cvs_profile_comes_back_as_drafts_not_saved(client: TestClient, engine: Engine) -> None:
    drafts = client.post("/cv/replace", data={"text": FRIEND_CV}).json()["drafts"]

    assert [w["company"] for w in drafts["work_experiences"]] == ["Acme Payments"]
    assert [e["institution"] for e in drafts["educations"]] == ["Riverdale College"]
    assert not any(d["duplicate"] for d in drafts["work_experiences"] + drafts["educations"])
    assert _count(engine, WorkExperience) == 0 and _count(engine, Education) == 0  # the user reviews first


def test_the_skill_dictionary_and_study_links_are_kept(client: TestClient, engine: Engine) -> None:
    skills, aliases = _count(engine, Skill), _count(engine, SkillAlias)

    client.post("/cv/replace", data={"text": FRIEND_CV})

    assert _count(engine, Skill) >= skills and _count(engine, SkillAlias) >= aliases
    assert _count(engine, LearningResource) == 1  # links describe a skill, not a person
    assert _count(engine, User) == 1


def test_an_unreadable_cv_changes_nothing(client: TestClient, engine: Engine) -> None:
    before = _count(engine, CVSkillPresence), _count(engine, JobDescription)

    bad = client.post("/cv/replace", files={"file": ("cv.exe", b"MZ...", "application/octet-stream")})
    empty = client.post("/cv/replace", data={})

    assert bad.status_code in (415, 422) and empty.status_code == 422
    assert (_count(engine, CVSkillPresence), _count(engine, JobDescription)) == before
    assert client.get("/me").json()["full_name"] == "Alex Demo"
