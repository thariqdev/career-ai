"""Stage 98: forgot password (emailed one-time link), reset, and change password.
A fake mail sender records emails; nothing is ever sent. In-memory SQLite, real logins."""

import re
from collections.abc import Iterator
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app import dependencies
from app.core.services import auth_service, mail_service
from app.db.models import AuthSession, PasswordReset, User
from app.dependencies import get_db
from app.main import app
from database import Base

OLD, NEW = "old-password-1", "new-password-2"


@pytest.fixture()
def outbox(monkeypatch: pytest.MonkeyPatch) -> list[dict]:
    sent: list[dict] = []
    monkeypatch.setattr(mail_service, "send_email", lambda to, subject, body: sent.append(
        {"to": to, "subject": subject, "body": body}) or True)
    monkeypatch.setenv("APP_URL", "https://career.example.com/")
    return sent


@pytest.fixture()
def engine(monkeypatch: pytest.MonkeyPatch) -> Iterator[Engine]:
    monkeypatch.setattr(dependencies, "ALLOW_DEFAULT_USER", False)
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)

    def override_get_db() -> Iterator[Session]:
        with Session(engine, autoflush=False) as db:
            yield db

    app.dependency_overrides[get_db] = override_get_db
    yield engine
    app.dependency_overrides.clear()
    engine.dispose()


@pytest.fixture()
def client(engine: Engine) -> TestClient:
    client = TestClient(app)
    client.post("/auth/signup", json={"email": "thariq@example.com", "password": OLD, "full_name": "Thariq"})
    return client


def _token(email: dict) -> str:
    return re.search(r"reset-password\?token=([\w-]+)", email["body"]).group(1)


def test_forgot_password_emails_a_one_time_link_and_never_a_password(client: TestClient, outbox, engine) -> None:
    response = TestClient(app).post("/auth/forgot-password", json={"email": "THARIQ@example.com"})

    assert response.status_code == 202
    [email] = outbox
    assert email["to"] == "thariq@example.com" and email["subject"] == "Reset your Career AI password"
    assert "https://career.example.com/reset-password?token=" in email["body"] and "30 minutes" in email["body"]
    assert OLD not in email["body"] and "Hi Thariq," in email["body"]
    with Session(engine) as db:
        assert db.scalar(select(PasswordReset.token_hash)) != _token(email)  # only a hash is stored


def test_the_reply_is_the_same_whether_or_not_the_account_exists(client: TestClient, outbox) -> None:
    anon = TestClient(app)
    real = anon.post("/auth/forgot-password", json={"email": "thariq@example.com"})
    unknown = anon.post("/auth/forgot-password", json={"email": "nobody@example.com"})

    assert real.status_code == unknown.status_code == 202
    assert real.json() == unknown.json()
    assert [e["to"] for e in outbox] == ["thariq@example.com"]  # only real accounts get mail


def test_a_reset_link_sets_the_new_password_logs_out_everywhere_and_works_once(client: TestClient, outbox, engine) -> None:
    other_device = TestClient(app)
    other_device.post("/auth/login", json={"email": "thariq@example.com", "password": OLD})
    TestClient(app).post("/auth/forgot-password", json={"email": "thariq@example.com"})
    token = _token(outbox[0])
    browser = TestClient(app)

    response = browser.post("/auth/reset-password", json={"token": token, "new_password": NEW})

    assert response.status_code == 200 and browser.get("/auth/me").status_code == 200  # logged in here
    assert client.get("/auth/me").status_code == 401 and other_device.get("/auth/me").status_code == 401
    assert TestClient(app).post("/auth/login", json={"email": "thariq@example.com", "password": OLD}).status_code == 401
    assert TestClient(app).post("/auth/login", json={"email": "thariq@example.com", "password": NEW}).status_code == 200
    again = TestClient(app).post("/auth/reset-password", json={"token": token, "new_password": "third-password"})
    assert again.status_code == 400 and "Ask for a new one" in again.json()["detail"]


def test_an_expired_or_made_up_link_changes_nothing(client: TestClient, outbox, engine) -> None:
    TestClient(app).post("/auth/forgot-password", json={"email": "thariq@example.com"})
    with Session(engine) as db:
        db.scalar(select(PasswordReset)).expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        db.commit()

    expired = TestClient(app).post("/auth/reset-password", json={"token": _token(outbox[0]), "new_password": NEW})
    made_up = TestClient(app).post("/auth/reset-password", json={"token": "made-up", "new_password": NEW})

    assert expired.status_code == made_up.status_code == 400
    assert client.get("/auth/me").status_code == 200  # still logged in: nothing changed
    assert TestClient(app).post("/auth/login", json={"email": "thariq@example.com", "password": OLD}).status_code == 200


def test_a_weak_new_password_is_refused_and_the_link_stays_usable(client: TestClient, outbox) -> None:
    TestClient(app).post("/auth/forgot-password", json={"email": "thariq@example.com"})
    token = _token(outbox[0])

    assert TestClient(app).post("/auth/reset-password", json={"token": token, "new_password": "short"}).status_code == 422
    assert TestClient(app).post("/auth/reset-password", json={"token": token, "new_password": NEW}).status_code == 200


def test_at_most_three_reset_emails_an_hour(client: TestClient, outbox) -> None:
    anon = TestClient(app)
    replies = [anon.post("/auth/forgot-password", json={"email": "thariq@example.com"}) for _ in range(5)]

    assert {r.status_code for r in replies} == {202}  # the reply never changes
    assert len(outbox) == auth_service.MAX_RESETS_PER_HOUR


def test_change_password_needs_the_current_one_and_keeps_only_this_browser(client: TestClient, engine) -> None:
    other_device = TestClient(app)
    other_device.post("/auth/login", json={"email": "thariq@example.com", "password": OLD})

    wrong = client.post("/auth/change-password", json={"current_password": "nope-nope", "new_password": NEW})
    right = client.post("/auth/change-password", json={"current_password": OLD, "new_password": NEW})

    assert wrong.status_code == 422 and wrong.json()["detail"] == "Your current password is wrong."
    assert right.status_code == 200 and client.get("/auth/me").status_code == 200
    assert other_device.get("/auth/me").status_code == 401
    with Session(engine) as db:
        assert db.scalar(select(User)).password_hash.startswith("scrypt$")
        assert len(list(db.scalars(select(AuthSession)))) == 1
    assert TestClient(app).post("/auth/change-password", json={"current_password": NEW, "new_password": OLD}).status_code == 401


def test_without_smtp_settings_nothing_is_sent_and_no_link_is_logged(caplog) -> None:
    sent = mail_service.send_email("a@example.com", "Reset your Career AI password", "secret link here")

    assert sent is False
    assert "not sent" in caplog.text and "secret link here" not in caplog.text
