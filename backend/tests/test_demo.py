"""Stage 94: deploy-ready. Hosted database URLs, and the public demo (seed, reset, guards).
Every test uses a throwaway in-memory database, never the live one."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app import demo
from app.api import demo as demo_api
from app.db.models import JobDescription, JobRequirement, User, UserSkill
from app.db.models.enums import VerificationStatus
from app.dependencies import get_db
from app.main import app
from database import Base, normalize_database_url


@pytest.mark.parametrize(
    ("url", "expected", "ssl"),
    [
        ("postgres://u:p@host.neon.tech/db?sslmode=require&channel_binding=require",
         "postgresql+pg8000://u:p@host.neon.tech/db", True),
        ("postgresql://u:p@localhost:5432/career_ai", "postgresql+pg8000://u:p@localhost:5432/career_ai", False),
        ("postgresql+pg8000://u:p@localhost:5432/career_ai?sslmode=disable",
         "postgresql+pg8000://u:p@localhost:5432/career_ai", False),
        ("sqlite:///:memory:", "sqlite:///:memory:", False),
    ],
)
def test_hosted_database_urls_are_translated_for_pg8000(url: str, expected: str, ssl: bool) -> None:
    normalized, connect_args = normalize_database_url(url)

    assert normalized == expected
    assert ("ssl_context" in connect_args) is ssl


def test_ssl_can_be_forced() -> None:
    assert "ssl_context" in normalize_database_url("postgresql://u:p@h/db", force_ssl=True)[1]


@pytest.fixture()
def demo_db(monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[Engine, sessionmaker]]:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False)
    monkeypatch.setattr(demo_api, "engine", engine)  # the reset endpoint must never reach the live database
    monkeypatch.setattr(demo_api, "SessionLocal", factory)
    yield engine, factory
    engine.dispose()


def _count(factory, model) -> int:
    with factory() as db:
        return db.scalar(select(func.count()).select_from(model))


def test_the_seed_builds_a_realistic_made_up_career(demo_db) -> None:
    _, factory = demo_db

    assert demo.seed_if_empty(factory) is True
    with factory() as db:
        user = db.scalar(select(User))
        statuses = {c.skill.name: c.status for c in db.scalars(select(UserSkill))}
        jobs = list(db.scalars(select(JobDescription)))
    assert user.full_name == "Alex Demo"  # never a real person
    assert statuses["Python"] == VerificationStatus.VERIFIED and statuses["Docker"] == VerificationStatus.PROVISIONAL
    assert len(jobs) == 3 and any(j.next_interview_at for j in jobs)
    assert _count(factory, JobRequirement) > 0
    assert demo.seed_if_empty(factory) is False  # never seeds over existing data


@pytest.fixture()
def client(demo_db) -> Iterator[TestClient]:
    _, factory = demo_db

    def override_get_db() -> Iterator[Session]:
        db = factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_outside_demo_mode_the_demo_endpoints_do_nothing(client: TestClient, monkeypatch) -> None:
    monkeypatch.delenv("DEMO_MODE", raising=False)

    assert client.get("/demo/status").json() == {"demo": False}
    assert client.post("/demo/reset", headers={"X-Demo-Token": "x"}).status_code == 404
    assert client.post("/import/preview").status_code != 403  # import works locally


def test_the_reset_needs_the_secret_token_and_reseeds(client: TestClient, demo_db, monkeypatch) -> None:
    _, factory = demo_db
    monkeypatch.setenv("DEMO_MODE", "true")
    demo.seed_if_empty(factory)
    client.post("/job-descriptions", json={"raw_text": "A visitor's own posting about Rust."})
    assert _count(factory, JobDescription) == 4

    monkeypatch.delenv("DEMO_RESET_TOKEN", raising=False)
    assert client.post("/demo/reset", headers={"X-Demo-Token": "anything"}).status_code == 503
    monkeypatch.setenv("DEMO_RESET_TOKEN", "s3cret")
    assert client.post("/demo/reset").status_code == 403
    assert client.post("/demo/reset", headers={"X-Demo-Token": "wrong"}).status_code == 403

    response = client.post("/demo/reset", headers={"X-Demo-Token": "s3cret"})

    assert response.status_code == 200 and response.json()["reset"] is True
    assert _count(factory, JobDescription) == 3  # back to the demo career; the visitor's posting is gone


def test_restoring_or_importing_a_backup_is_off_in_the_demo(client: TestClient, monkeypatch) -> None:
    monkeypatch.setenv("DEMO_MODE", "true")

    assert client.get("/demo/status").json() == {"demo": True}
    assert client.post("/import/preview").status_code == 403
    assert client.post("/import").json()["detail"] == "Not available in the public demo."
