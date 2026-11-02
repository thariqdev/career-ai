"""Stage 97: accounts. Sign up, log in, log out, sessions, lockout, and "no login = 401".
Real logins only (the built-in-user test seam is switched off). In-memory SQLite only."""

from collections.abc import Iterator
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app import dependencies
from app.core.services import auth_service
from app.db.models import AuthSession, User
from app.dependencies import SESSION_COOKIE, get_db
from app.main import app
from database import Base

PASSWORD = "correct horse 42"


@pytest.fixture()
def engine(monkeypatch: pytest.MonkeyPatch) -> Iterator[Engine]:
    monkeypatch.setattr(dependencies, "ALLOW_DEFAULT_USER", False)  # real logins only
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
    return TestClient(app)


def _signup(client: TestClient, email: str = "thariq@example.com", password: str = PASSWORD, **extra):
    return client.post("/auth/signup", json={"email": email, "password": password, **extra})


def test_sign_up_logs_you_in_and_never_returns_the_password(client: TestClient, engine: Engine) -> None:
    response = _signup(client, "Thariq@Example.com", full_name="Mohammed Thariq")

    assert response.status_code == 201
    assert response.json() == {"id": 1, "email": "thariq@example.com", "full_name": "Mohammed Thariq"}
    cookie = response.headers["set-cookie"]
    assert f"{SESSION_COOKIE}=" in cookie and "HttpOnly" in cookie and "samesite=lax" in cookie.lower()
    assert client.get("/auth/me").json()["email"] == "thariq@example.com"
    with Session(engine) as db:
        user = db.scalar(select(User))
        token_hash = db.scalar(select(AuthSession.token_hash))
    assert user.password_hash.startswith("scrypt$") and PASSWORD not in user.password_hash
    assert token_hash != client.cookies[SESSION_COOKIE]  # only a hash of the token is stored


def test_without_logging_in_every_private_route_says_401(client: TestClient) -> None:
    for method, path in [("get", "/me"), ("get", "/auth/me"), ("get", "/skills"), ("get", "/job-descriptions"),
                         ("get", "/export"), ("get", "/practice/rag-questions"), ("get", "/learning-progress")]:
        assert getattr(client, method)(path).status_code == 401, path
    assert client.post("/assistant/ask", json={"question": "hi"}).status_code == 401
    assert client.post("/job-descriptions", json={"raw_text": "Need Python."}).status_code == 401
    assert client.get("/health").status_code == 200  # public


def test_log_out_ends_the_session_and_log_in_starts_a_new_one(client: TestClient, engine: Engine) -> None:
    _signup(client)
    assert client.post("/auth/logout").status_code == 204
    assert client.get("/auth/me").status_code == 401
    with Session(engine) as db:
        assert db.scalar(select(AuthSession)) is None

    response = client.post("/auth/login", json={"email": " THARIQ@example.com ", "password": PASSWORD})

    assert response.status_code == 200 and client.get("/auth/me").status_code == 200


def test_wrong_password_and_unknown_email_get_the_same_answer(client: TestClient) -> None:
    _signup(client)
    client.post("/auth/logout")

    wrong = client.post("/auth/login", json={"email": "thariq@example.com", "password": "nope-nope"})
    unknown = client.post("/auth/login", json={"email": "nobody@example.com", "password": PASSWORD})

    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json() == {"detail": "Wrong email or password."}
    assert client.get("/auth/me").status_code == 401


def test_five_wrong_passwords_lock_the_account_for_a_while(client: TestClient, engine: Engine) -> None:
    _signup(client)
    client.post("/auth/logout")
    for _ in range(auth_service.MAX_FAILED_LOGINS):
        client.post("/auth/login", json={"email": "thariq@example.com", "password": "guess-guess"})

    locked = client.post("/auth/login", json={"email": "thariq@example.com", "password": PASSWORD})
    assert locked.status_code == 429 and "Try again" in locked.json()["detail"]

    with Session(engine) as db:  # the lock runs out
        db.scalar(select(User)).locked_until = datetime.now(timezone.utc) - timedelta(seconds=1)
        db.commit()
    assert client.post("/auth/login", json={"email": "thariq@example.com", "password": PASSWORD}).status_code == 200


def test_sign_up_rules(client: TestClient) -> None:
    assert _signup(client, password="short").status_code == 422
    assert _signup(client, email="not-an-email").status_code == 422
    assert _signup(client).status_code == 201
    other = TestClient(app)
    taken = other.post("/auth/signup", json={"email": "THARIQ@example.com", "password": PASSWORD})
    assert taken.status_code == 409


def test_an_expired_or_made_up_session_is_logged_out(client: TestClient, engine: Engine) -> None:
    _signup(client)
    with Session(engine) as db:
        db.scalar(select(AuthSession)).expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        db.commit()

    assert client.get("/auth/me").status_code == 401
    with Session(engine) as db:
        assert db.scalar(select(AuthSession)) is None  # removed when seen
    forged = TestClient(app, cookies={SESSION_COOKIE: "made-up-token"})
    assert forged.get("/me").status_code == 401


def test_the_cookie_is_secure_unless_switched_off_for_local_http(client: TestClient, monkeypatch) -> None:
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "true")
    assert "Secure" in _signup(client).headers["set-cookie"]


def test_an_account_without_a_password_cannot_log_in(client: TestClient, engine: Engine) -> None:
    with Session(engine) as db:
        db.add(User(email="me@career-ai.local"))  # the old built-in user, not claimed yet
        db.commit()

    response = client.post("/auth/login", json={"email": "me@career-ai.local", "password": ""})

    assert response.status_code == 401
