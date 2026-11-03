"""Stage 102: the job list and job matches read the skill dictionary once per request,
instead of hundreds of tiny queries (the "N+1" problem). Same answers, far fewer trips to
the database. In-memory SQLite only."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, event, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app import demo
from app.core.exceptions import AmbiguousSkillMatchError
from app.core.services import match_service, skill_service
from app.core.services.user_service import get_or_create_default_user
from app.db.models import JobDescription, SkillAlias
from app.dependencies import get_db
from app.main import app
from database import Base

EXTRA = ["Kotlin", "Swift", "Rust", "Go", "Scala", "Elixir", "Ruby", "PHP", "Perl", "Haskell"]


@pytest.fixture()
def engine() -> Iterator[Engine]:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    demo.seed_if_empty(sessionmaker(bind=engine, autoflush=False))
    yield engine
    engine.dispose()


def _add_skills(engine: Engine, names: list[str]) -> None:
    with Session(engine, autoflush=False) as db:
        for name in names:
            skill_service.add_alias(db, skill_service.create_skill(db, name), f"{name.lower()}-lang")
        db.commit()


def _queries_for_job_list(engine: Engine) -> int:
    count = [0]

    def counter(*args) -> None:
        count[0] += 1

    def override_get_db() -> Iterator[Session]:
        with Session(engine, autoflush=False) as db:
            yield db

    app.dependency_overrides[get_db] = override_get_db
    event.listen(engine, "before_cursor_execute", counter)
    try:
        response = TestClient(app).get("/job-descriptions")
    finally:
        event.remove(engine, "before_cursor_execute", counter)
        app.dependency_overrides.clear()
    assert response.status_code == 200 and len(response.json()) == 3
    return count[0]


def test_the_job_list_uses_a_handful_of_queries_however_many_skills_exist(engine: Engine) -> None:
    few = _queries_for_job_list(engine)
    _add_skills(engine, EXTRA)
    many = _queries_for_job_list(engine)

    assert few <= 25, few  # was 200+ before stage 102
    assert many == few  # more skills in the dictionary must not mean more queries


def test_sharing_the_context_gives_exactly_the_same_matches(engine: Engine) -> None:
    _add_skills(engine, EXTRA)
    with Session(engine, autoflush=False) as db:
        python = skill_service.resolve_skill(db, "Python")
        skill_service.add_alias(db, python, "py3")
        db.commit()
        user = get_or_create_default_user(db)
        jobs = list(db.scalars(select(JobDescription)))
        context = match_service.match_context(db, user)
        for job in jobs:
            alone = match_service.job_match(db, user, job)
            shared = match_service.job_match(db, user, job, context)
            assert shared == alone, job.title


def test_the_index_resolves_exactly_like_resolve_skill(engine: Engine) -> None:
    _add_skills(engine, EXTRA)
    with Session(engine, autoflush=False) as db:
        go = skill_service.resolve_skill(db, "Go")
        db.add(SkillAlias(skill_id=skill_service.resolve_skill(db, "Rust").id, alias="go-lang"))  # an ambiguous spelling
        db.flush()
        index = skill_service.SkillIndex(db)
        for text in ["Python", "  python ", "PY3", "rust-lang", "Unknown", "", "Go", "FastAPI"]:
            assert index.resolve(text) == skill_service.resolve_skill(db, text), text
        with pytest.raises(AmbiguousSkillMatchError):
            skill_service.resolve_skill(db, "go-lang")
        with pytest.raises(AmbiguousSkillMatchError):
            index.resolve("go-lang")
        assert index.terms == skill_service.skill_terms(db)
        assert go is not None
