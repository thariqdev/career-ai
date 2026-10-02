"""HTTP tests for application tracking on a job: status, applied-on date and a note.

Same TestClient + dependency_overrides[get_db] + StaticPool in-memory SQLite pattern as
the other API tests.
"""

import json
from collections.abc import Iterator
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.models import JobDescription, User
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


def _job(client: TestClient) -> int:
    return client.post("/job-descriptions", json={"raw_text": "Need Python.", "title": "Backend"}).json()["id"]


def _patch(client: TestClient, job_id: int, body: dict):
    return client.patch(f"/job-descriptions/{job_id}/application", json=body)


def _application(body: dict) -> tuple:
    return body["application_status"], body["applied_on"], body["application_notes"]


TODAY = date.today().isoformat()


def test_a_new_job_is_saved_with_no_date_or_note(client: TestClient) -> None:
    body = client.get(f"/job-descriptions/{_job(client)}").json()

    assert _application(body) == ("saved", None, None)


def test_applied_without_a_date_records_today(client: TestClient) -> None:
    response = _patch(client, _job(client), {"status": "applied"})

    assert response.status_code == 200
    assert _application(response.json()) == ("applied", TODAY, None)


def test_an_explicit_date_is_kept(client: TestClient) -> None:
    response = _patch(client, _job(client), {"status": "applied", "applied_on": "2026-09-01"})

    assert _application(response.json()) == ("applied", "2026-09-01", None)


def test_only_sent_fields_change(client: TestClient) -> None:
    job_id = _job(client)
    _patch(client, job_id, {"status": "applied", "applied_on": "2026-09-01", "notes": "  Referral from Sam  "})

    response = _patch(client, job_id, {"status": "interviewing"})

    assert _application(response.json()) == ("interviewing", "2026-09-01", "Referral from Sam")
    response = _patch(client, job_id, {"notes": "Call Tues 3pm"})
    assert _application(response.json()) == ("interviewing", "2026-09-01", "Call Tues 3pm")


def test_a_blank_or_null_note_clears_it(client: TestClient) -> None:
    job_id = _job(client)
    _patch(client, job_id, {"notes": "something"})

    assert _patch(client, job_id, {"notes": "   "}).json()["application_notes"] is None
    _patch(client, job_id, {"notes": "something"})
    assert _patch(client, job_id, {"notes": None}).json()["application_notes"] is None


def test_other_statuses_never_invent_a_date(client: TestClient) -> None:
    response = _patch(client, _job(client), {"status": "rejected"})

    assert _application(response.json()) == ("rejected", None, None)


def test_a_future_date_is_refused(client: TestClient) -> None:
    job_id = _job(client)
    tomorrow = (date.today() + timedelta(days=1)).isoformat()

    response = _patch(client, job_id, {"status": "applied", "applied_on": tomorrow})

    assert response.status_code == 422
    assert "future" in response.json()["detail"]
    assert _application(client.get(f"/job-descriptions/{job_id}").json()) == ("saved", None, None)


def test_saved_with_a_date_is_refused(client: TestClient) -> None:
    response = _patch(client, _job(client), {"status": "saved", "applied_on": "2026-09-01"})

    assert response.status_code == 422
    assert "saved job" in response.json()["detail"]


def test_moving_back_to_saved_clears_the_date(client: TestClient) -> None:
    job_id = _job(client)
    _patch(client, job_id, {"status": "applied", "applied_on": "2026-09-01"})

    response = _patch(client, job_id, {"status": "saved"})

    assert _application(response.json()) == ("saved", None, None)


def test_an_unknown_status_is_422(client: TestClient) -> None:
    assert _patch(client, _job(client), {"status": "hired"}).status_code == 422


def test_another_users_job_is_404(client: TestClient, engine: Engine) -> None:
    with Session(engine, autoflush=False) as db:
        other = JobDescription(user=User(email="other@example.com"), raw_text="Secret")
        db.add(other)
        db.commit()
        other_id = other.id

    assert _patch(client, other_id, {"status": "applied"}).status_code == 404
    assert _patch(client, 999, {"status": "applied"}).status_code == 404


def test_listing_jobs_includes_the_application(client: TestClient) -> None:
    job_id = _job(client)
    _patch(client, job_id, {"status": "offer", "applied_on": "2026-08-15"})

    [job] = client.get("/job-descriptions").json()

    assert _application(job) == ("offer", "2026-08-15", None)


# --- backup -----------------------------------------------------------------------------


def test_export_and_restore_keep_the_application(client: TestClient, engine: Engine) -> None:
    job_id = _job(client)
    _patch(client, job_id, {"status": "interviewing", "applied_on": "2026-09-01", "notes": "Round 2"})
    backup = client.get("/export").json()
    assert _application(backup["job_descriptions"][0]) == ("interviewing", "2026-09-01", "Round 2")

    empty = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(empty)

    def override_get_db() -> Iterator[Session]:
        db = Session(empty, autoflush=False)
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    files = {"file": ("backup.json", json.dumps(backup).encode(), "application/json")}
    assert client.post("/import", files=files).status_code == 200
    [job] = client.get("/job-descriptions").json()
    assert _application(job) == ("interviewing", "2026-09-01", "Round 2")
    empty.dispose()


def test_an_older_backup_without_the_fields_restores_as_saved(client: TestClient, engine: Engine) -> None:
    _job(client)
    backup = client.get("/export").json()
    for field in ("application_status", "applied_on", "application_notes"):
        del backup["job_descriptions"][0][field]

    empty = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(empty)

    def override_get_db() -> Iterator[Session]:
        db = Session(empty, autoflush=False)
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    files = {"file": ("backup.json", json.dumps(backup).encode(), "application/json")}
    assert client.post("/import", files=files).status_code == 200
    [job] = client.get("/job-descriptions").json()
    assert _application(job) == ("saved", None, None)
    empty.dispose()


def test_a_backup_with_a_dated_saved_job_is_refused(client: TestClient) -> None:
    _job(client)
    backup = client.get("/export").json()
    backup["job_descriptions"][0]["applied_on"] = "2026-09-01"

    files = {"file": ("backup.json", json.dumps(backup).encode(), "application/json")}
    body = client.post("/import/preview", files=files).json()

    assert any("saved (not applied to) but has an applied-on date" in p for p in body["problems"])
