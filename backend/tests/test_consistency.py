"""Stage 88: one fact, one answer. Features that say which skills a job asks for, or what
it's missing, must agree with the match (match_service), the app's single source of truth.

Where they already agree, these tests keep it that way. Where they don't yet (the
gaps endpoint, a Compare snapshot over saved requirements only), a strict xfail documents
the known disagreement: when it's fixed, the test passes, xfail(strict) turns that into a
failure, and the marker must be removed. A known bug can't be silently forgotten. (The
/gaps one was fixed in stage 89.)
"""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.dependencies import get_db
from app.main import app
from database import Base


@pytest.fixture()
def engine() -> Iterator[Engine]:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture()
def client(engine: Engine, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

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


@pytest.fixture()
def job(client: TestClient) -> int:
    """Python and Docker on the CV; a job asking for Python, Docker, Kubernetes and AWS, of
    which only Python and Kubernetes are SAVED requirements (the rest is in the posting text)."""
    client.post("/cv/add-all", data={"text": "Python and Docker."})
    job_id = client.post("/job-descriptions", json={
        "raw_text": "Backend role: Python, Docker, Kubernetes and AWS.", "title": "Backend", "company": "Acme",
    }).json()["id"]
    client.post(f"/job-descriptions/{job_id}/extract")
    client.post(f"/job-descriptions/{job_id}/compare")
    return job_id


def _match(client: TestClient, job_id: int) -> dict[str, set[str]]:
    body = client.get(f"/job-descriptions/{job_id}/match").json()
    return {group: {i["name"] for i in body[group]} for group in ("proven", "on_cv", "missing")}


def test_the_job_list_agrees_with_the_match(client: TestClient, job: int) -> None:
    listed = next(j for j in client.get("/job-descriptions").json() if j["id"] == job)
    match = client.get(f"/job-descriptions/{job}/match").json()

    assert (listed["match_percent"], listed["match_total"]) == (match["percent"], match["total"])


def test_the_interview_prep_sheet_agrees_with_the_match(client: TestClient, job: int) -> None:
    sheet = {i["skill_name"] for i in client.get(f"/job-descriptions/{job}/interview-prep").json()["items"]}

    assert sheet == set().union(*_match(client, job).values())


def test_the_assistants_exact_list_agrees_with_the_match(client: TestClient, job: int) -> None:
    body = client.post("/assistant/ask", json={"question": "What am I missing for the Acme job?"}).json()
    tool = body["sources"][0]

    assert tool["kind"] == "tool"
    for skill in _match(client, job)["missing"]:
        assert skill in tool["text"]
    for skill in _match(client, job)["on_cv"] | _match(client, job)["proven"]:
        assert f" {skill}," not in tool["text"] and not tool["text"].endswith(f" {skill}.")


def test_the_gaps_endpoint_agrees_with_the_match(client: TestClient, job: int) -> None:
    # Was a strict xfail in stage 88 (gaps came from the last Compare over saved requirements
    # only); fixed in stage 89, and the xfail flagged itself as designed.
    gaps = {g["skill_name"] for g in client.get(f"/job-descriptions/{job}/gaps").json()}
    match = _match(client, job)

    assert gaps == match["missing"] | match["on_cv"]  # every skill not yet proven
