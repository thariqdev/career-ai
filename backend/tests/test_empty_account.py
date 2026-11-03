""""Empty my account": removes only your data, keeps your login and name, needs your
password, and then a backup restores into it. In-memory SQLite, real logins."""

import json
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app import demo, dependencies
from app.core.services import auth_service
from app.db.models import JobDescription, LearningResource, User
from app.dependencies import get_db
from app.main import app
from database import Base

PASSWORD = "my-own-password"


@pytest.fixture()
def engine(monkeypatch: pytest.MonkeyPatch) -> Iterator[Engine]:
    monkeypatch.setattr(dependencies, "ALLOW_DEFAULT_USER", False)
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False)
    demo.seed_if_empty(factory)  # someone else's career, already on the site
    with factory() as db:
        auth_service.claim_built_in_user(db, "other@example.com", PASSWORD)
        db.commit()

    def override_get_db() -> Iterator[Session]:
        with factory() as db:
            yield db

    app.dependency_overrides[get_db] = override_get_db
    yield engine
    app.dependency_overrides.clear()
    engine.dispose()


def _count(engine: Engine, model, email: str) -> int:
    with Session(engine) as db:
        uid = db.scalar(select(User.id).where(User.email == email))
        return db.scalar(select(func.count()).select_from(model).where(model.user_id == uid))


def test_emptying_needs_your_password_and_keeps_your_login_and_name(engine: Engine) -> None:
    me = TestClient(app)
    me.post("/auth/signup", json={"email": "me@example.com", "password": PASSWORD, "full_name": "Thariq"})
    me.post("/job-descriptions", json={"raw_text": "Need Python and Docker."})
    skill = me.get("/skills").json()[0]["id"]
    me.post(f"/skills/{skill}/learning-resources", json={"mode": "theory_interview", "title": "x", "url": "https://x.example"})
    other_jobs = _count(engine, JobDescription, "other@example.com")

    wrong = me.post("/me/empty", json={"password": "not-my-password"})
    assert wrong.status_code == 422 and _count(engine, JobDescription, "me@example.com") == 1  # nothing removed

    right = me.post("/me/empty", json={"password": PASSWORD})

    assert right.status_code == 200 and right.json()["removed"]["jobs"] == 1
    assert _count(engine, JobDescription, "me@example.com") == 0
    assert _count(engine, LearningResource, "me@example.com") == 0
    assert me.get("/me").json() == {"id": 2, "email": "me@example.com", "full_name": "Thariq"}  # still logged in
    assert _count(engine, JobDescription, "other@example.com") == other_jobs  # nobody else touched


def test_after_emptying_a_backup_restores(engine: Engine) -> None:
    other = TestClient(app)
    other.post("/auth/login", json={"email": "other@example.com", "password": PASSWORD})
    backup = json.dumps(other.get("/export").json())
    me = TestClient(app)
    me.post("/auth/signup", json={"email": "me@example.com", "password": PASSWORD})
    me.post("/job-descriptions", json={"raw_text": "Something added by mistake."})
    upload = {"file": ("b.json", backup, "application/json")}

    assert me.post("/import/preview", files=upload).json()["app_empty"] is False
    me.post("/me/empty", json={"password": PASSWORD})
    assert me.post("/import/preview", files=upload).json()["app_empty"] is True
    assert me.post("/import", files=upload).status_code == 200
    assert len(me.get("/job-descriptions").json()) == 3


def test_emptying_without_logging_in_is_401(engine: Engine) -> None:
    assert TestClient(app).post("/me/empty", json={"password": PASSWORD}).status_code == 401
