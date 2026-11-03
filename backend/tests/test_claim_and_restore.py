"""Stage 100: your pre-accounts data becomes your account (claim), and "Restore from
backup" works on a site where other accounts already exist. In-memory SQLite only."""

import json
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app import demo, dependencies
from app.core.exceptions import AccountClaimError, EmailTakenError, WeakPasswordError
from app.core.services import auth_service
from app.db.models import JobDescription, Skill, SkillAlias, User, UserSkill
from app.dependencies import get_db
from app.main import app
from database import Base
from scripts import claim_account

PASSWORD = "my-own-password"


def _engine() -> Engine:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    return engine


def _use(engine: Engine) -> None:
    factory = sessionmaker(bind=engine, autoflush=False)

    def override_get_db() -> Iterator[Session]:
        with factory() as db:
            yield db

    app.dependency_overrides[get_db] = override_get_db


@pytest.fixture()
def old_data(monkeypatch: pytest.MonkeyPatch) -> Iterator[Engine]:
    """A database from before accounts: the built-in user (no password) with a career."""
    monkeypatch.setattr(dependencies, "ALLOW_DEFAULT_USER", False)
    engine = _engine()
    demo.seed_if_empty(sessionmaker(bind=engine, autoflush=False))
    yield engine
    app.dependency_overrides.clear()
    engine.dispose()


def test_claiming_keeps_every_record_and_lets_you_log_in(old_data: Engine) -> None:
    with Session(old_data) as db:
        jobs_before = db.scalar(select(func.count()).select_from(JobDescription))
        user = auth_service.claim_built_in_user(db, "Thariq@Example.com", PASSWORD, "Mohammed Thariq")
        db.commit()
        assert user.email == "thariq@example.com" and user.password_hash.startswith("scrypt$")
    _use(old_data)
    client = TestClient(app)

    assert client.post("/auth/login", json={"email": "thariq@example.com", "password": PASSWORD}).status_code == 200
    assert len(client.get("/job-descriptions").json()) == jobs_before  # all of it, now yours
    assert client.get("/me").json()["full_name"] == "Mohammed Thariq"


def test_claiming_is_refused_when_it_would_be_wrong(old_data: Engine) -> None:
    with Session(old_data) as db:
        db.add(User(email="taken@example.com", password_hash=auth_service.hash_password(PASSWORD)))
        db.commit()
        with pytest.raises(EmailTakenError):
            auth_service.claim_built_in_user(db, "taken@example.com", PASSWORD)
        with pytest.raises(WeakPasswordError):
            auth_service.claim_built_in_user(db, "me@example.com", "short")
        auth_service.claim_built_in_user(db, "me@example.com", PASSWORD)
        db.commit()
        with pytest.raises(AccountClaimError):  # nothing left to claim
            auth_service.claim_built_in_user(db, "again@example.com", PASSWORD)


def test_the_script_asks_twice_and_changes_nothing_on_a_mismatch(old_data: Engine, monkeypatch, capsys) -> None:
    monkeypatch.setattr(claim_account, "engine", old_data)  # never the live database
    answers = iter(["first-password", "different-one"])

    assert claim_account.main(["--email", "me@example.com"], ask=lambda prompt: next(answers)) == 1
    assert "don't match" in capsys.readouterr().out
    with Session(old_data) as db:
        assert db.scalar(select(User.password_hash)) is None

    same = iter([PASSWORD, PASSWORD])
    assert claim_account.main(["--email", "me@example.com"], ask=lambda prompt: next(same)) == 0
    with Session(old_data) as db:
        assert db.scalar(select(User.email)) == "me@example.com"


def test_a_backup_restores_into_a_new_account_next_to_other_people(monkeypatch: pytest.MonkeyPatch) -> None:
    """Download your data locally, sign up on the live site, restore: the shared skills are
    reused (no duplicates), the other account is untouched and gains no nicknames."""
    monkeypatch.setattr(dependencies, "ALLOW_DEFAULT_USER", False)
    local, live = _engine(), _engine()
    try:
        demo.seed_if_empty(sessionmaker(bind=local, autoflush=False))  # your local career
        with Session(local) as db:
            auth_service.claim_built_in_user(db, "me@example.com", PASSWORD)
            python = db.scalar(select(Skill).where(Skill.name == "Python"))
            db.add(SkillAlias(skill_id=python.id, alias="py3"))
            db.commit()
        _use(local)
        mine = TestClient(app)
        mine.post("/auth/login", json={"email": "me@example.com", "password": PASSWORD})
        backup = mine.get("/export").json()

        demo.seed_if_empty(sessionmaker(bind=live, autoflush=False))  # someone else on the live site
        with Session(live) as db:
            auth_service.claim_built_in_user(db, "other@example.com", PASSWORD)
            db.commit()
            skills_before = db.scalar(select(func.count()).select_from(Skill))
            other_claims = db.scalar(select(func.count()).select_from(UserSkill))
        _use(live)
        me_live = TestClient(app)
        me_live.post("/auth/signup", json={"email": "me@example.com", "password": PASSWORD})

        preview = me_live.post("/import/preview", files={"file": ("b.json", json.dumps(backup), "application/json")})
        restored = me_live.post("/import", files={"file": ("b.json", json.dumps(backup), "application/json")})

        assert preview.json()["app_empty"] is True  # other people's skills don't count
        assert restored.status_code == 200, restored.json()
        assert len(me_live.get("/job-descriptions").json()) == 3
        with Session(live) as db:
            names = list(db.scalars(select(Skill.name)))
            assert len(names) == len(set(names)) == skills_before  # reused, never duplicated
            assert db.scalar(select(func.count()).select_from(UserSkill)) == other_claims * 2
            assert db.scalar(select(SkillAlias).where(SkillAlias.alias == "py3")) is None  # other uses Python
        again = me_live.post("/import", files={"file": ("b.json", json.dumps(backup), "application/json")})
        assert again.status_code == 409  # your account isn't empty any more
    finally:
        app.dependency_overrides.clear()
        local.dispose()
        live.dispose()
