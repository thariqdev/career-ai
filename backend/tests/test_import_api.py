"""HTTP tests for restoring a "Download my data" file: all or nothing, empty app only.

Two in-memory SQLite databases: one is filled and exported, the other receives the
restore. Same TestClient + dependency_overrides[get_db] + StaticPool pattern as the
other API tests.
"""

import copy
import json
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.services import import_service, skill_service
from app.dependencies import get_db
from app.main import app
from database import Base


def _engine() -> Engine:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return engine


@pytest.fixture()
def engines() -> Iterator[tuple[Engine, Engine]]:
    source, target = _engine(), _engine()
    yield source, target
    source.dispose()
    target.dispose()


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)  # use the free skill-list reader
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def _use(engine: Engine) -> None:
    def override_get_db() -> Iterator[Session]:
        db = Session(engine, autoflush=False)
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db


def _fill(client: TestClient, engine: Engine) -> None:
    """One of everything, through the real API."""
    _use(engine)
    with Session(engine, autoflush=False) as db:
        python = skill_service.create_skill(db, "Python", "Languages")
        skill_service.add_alias(db, python, "py")
        skill_service.create_skill(db, "Docker")
        db.commit()
    skills = {s["name"]: s["id"] for s in client.get("/skills").json()}
    project_id = client.post(
        "/projects", json={"name": "FundsApp", "url": "https://github.com/me/funds", "start_date": "2025-01-01"}
    ).json()["id"]
    client.post("/work-experiences", json={"company": "Acme", "role": "Intern", "start_date": "2024-06-01"})
    client.post("/educations", json={"institution": "State University", "degree": "BSc"})
    evidence_id = client.post(
        "/evidence", json={"evidence_type": "project", "title": "Repo", "project_id": project_id}
    ).json()["id"]
    client.post("/evidence", json={"evidence_type": "certification", "title": "AWS cert"})
    claim_id = client.post("/user-skills", json={"skill_id": skills["Python"]}).json()["id"]
    client.post(f"/user-skills/{claim_id}/evidence-links", json={"evidence_id": evidence_id})
    client.post(f"/user-skills/{claim_id}/status", json={"status": "verified"})
    client.patch(f"/skills/{skills['Python']}/cv-presence", json={"present": True})
    client.put(f"/skills/{skills['Docker']}/learning-progress", json={"status": "studying"})
    client.post(
        f"/skills/{skills['Docker']}/learning-resources",
        json={"mode": "theory_interview", "title": "Docs", "url": "https://docs.docker.com/"},
    )
    for title in ("Backend", "Platform"):
        job_id = client.post(
            "/job-descriptions", json={"raw_text": "Need Python and Docker.", "title": title}
        ).json()["id"]
        client.post(f"/job-descriptions/{job_id}/extract")
        client.post(f"/job-descriptions/{job_id}/compare")
    docker_requirement = next(
        r["id"] for r in client.get(f"/job-descriptions/{job_id}").json()["requirements"] if r["skill_name"] == "Docker"
    )
    client.delete(f"/job-descriptions/{job_id}/requirements/{docker_requirement}")


def _export(client: TestClient, engine: Engine) -> dict:
    _use(engine)
    return client.get("/export").json()


def _upload(client: TestClient, engine: Engine, data: dict | bytes, path: str = "/import"):
    _use(engine)
    raw = data if isinstance(data, bytes) else json.dumps(data).encode()
    return client.post(path, files={"file": ("backup.json", raw, "application/json")})


def _resolved(data: dict) -> dict:
    """The export with every id replaced by what it points at, so two exports with
    different ids can be compared, links included."""
    skill = {s["id"]: s["name"] for s in data["skills"]}
    evidence = {e["id"]: e["title"] for e in data["evidence"]}
    project = {p["id"]: p["name"] for p in data["projects"]}
    claim_skill = {c["id"]: skill[c["skill_id"]] for c in data["claims"]}

    def drop(row: dict, *keys: str) -> dict:
        return {k: v for k, v in row.items() if k not in ("id", *keys)}

    jobs = []
    for job in data["job_descriptions"]:
        requirement = {r["id"]: r["requirement_text"] for r in job["requirements"]}
        jobs.append(
            {
                **drop(job, "requirements", "comparison_results", "removed_skill_ids"),
                "requirements": [
                    {**drop(r, "job_description_id", "skill_id"), "skill": skill.get(r["skill_id"])}
                    for r in job["requirements"]
                ],
                "results": [
                    {
                        **drop(r, "job_requirement_id", "user_skill_id", "evidence_ids"),
                        "requirement": requirement[r["job_requirement_id"]],
                        "claim": claim_skill.get(r["user_skill_id"]),
                        "evidence": [evidence[i] for i in r["evidence_ids"]],
                    }
                    for r in job["comparison_results"]
                ],
                "removed": [skill[i] for i in job["removed_skill_ids"]],
            }
        )
    return {
        "skills": [drop(s) for s in data["skills"]],
        "claims": [
            {**drop(c, "skill_id", "evidence_ids"), "skill": skill[c["skill_id"]], "evidence": [evidence[i] for i in c["evidence_ids"]]}
            for c in data["claims"]
        ],
        "evidence": [{**drop(e, "project_id"), "project": project.get(e["project_id"])} for e in data["evidence"]],
        "projects": [drop(p) for p in data["projects"]],
        "work_experiences": [drop(w) for w in data["work_experiences"]],
        "educations": [drop(e) for e in data["educations"]],
        "jobs": jobs,
        "cv_marks": [{**drop(m, "skill_id"), "skill": skill[m["skill_id"]]} for m in data["cv_marks"]],
        "progress": [{**drop(p, "skill_id"), "skill": skill[p["skill_id"]]} for p in data["learning_progress"]],
        "resources": [{**drop(r, "skill_id"), "skill": skill[r["skill_id"]]} for r in data["learning_resources"]],
    }


def _row_counts(engine: Engine) -> dict[str, int]:
    """Every table except users: the app creates its one built-in user on the first
    request (get_current_user), which happens before the restore code runs at all."""
    with Session(engine) as db:
        return {
            t.name: db.scalar(select(func.count()).select_from(t))
            for t in Base.metadata.sorted_tables
            if t.name != "users"
        }


# --- the round trip -----------------------------------------------------------------------


def test_round_trip_restores_everything_with_its_links(client: TestClient, engines) -> None:
    source, target = engines
    _fill(client, source)
    original = _export(client, source)

    response = _upload(client, target, original)

    assert response.status_code == 200
    assert response.json()["counts"]["claims"] == 1
    assert response.json()["counts"]["requirements"] == 3
    restored = _export(client, target)
    assert _resolved(restored) == _resolved(original)
    # Timestamps come back exactly as exported.
    assert restored["claims"][0]["created_at"] == original["claims"][0]["created_at"]


def test_restored_app_works_normally(client: TestClient, engines) -> None:
    source, target = engines
    _fill(client, source)
    _upload(client, target, _export(client, source))

    _use(target)
    [claim] = client.get("/user-skills").json()
    assert claim["status"] == "verified"
    jobs = client.get("/job-descriptions").json()
    assert client.post(f"/job-descriptions/{jobs[0]['id']}/compare").status_code == 200
    # The removed-requirement note survived: looking again doesn't bring Docker back.
    platform = next(j for j in jobs if j["title"] == "Platform")
    client.post(f"/job-descriptions/{platform['id']}/extract-new")
    names = [r["skill_name"] for r in client.get(f"/job-descriptions/{platform['id']}").json()["requirements"]]
    assert names == ["Python"]


# --- refused --------------------------------------------------------------------------------


def test_restore_into_a_non_empty_app_is_refused(client: TestClient, engines) -> None:
    source, target = engines
    _fill(client, source)
    backup = _export(client, source)
    before = _row_counts(source)

    response = _upload(client, source, backup)

    assert response.status_code == 409
    assert "empty app" in response.json()["detail"]
    assert _row_counts(source) == before


def _broken(backup: dict, how: str) -> dict:
    data = copy.deepcopy(backup)
    if how == "version":
        data["format_version"] = 2
    elif how == "not-career-ai":
        data["app"] = "Something else"
    elif how == "broken-link":
        data["claims"][0]["evidence_ids"] = [9999]
    elif how == "verified-without-evidence":
        data["claims"][0]["evidence_ids"] = []
    elif how == "two-sources":
        data["evidence"][0]["work_experience_id"] = data["work_experiences"][0]["id"]
    elif how == "duplicate-nickname":
        data["skills"][1]["aliases"] = ["PY"]
    elif how == "non-web-link":
        data["learning_resources"][0]["url"] = "javascript:alert(1)"
    elif how == "bad-dates":
        data["projects"][0]["end_date"] = "2000-01-01"
    elif how == "wrong-type":
        data["claims"][0]["status"] = "expert"
    elif how == "unknown-field":
        data["skills"][0]["level"] = "expert"
    elif how == "missing-skill":
        data["cv_marks"][0]["skill_id"] = 9999
    return data


@pytest.mark.parametrize(
    "how",
    [
        "version",
        "not-career-ai",
        "broken-link",
        "verified-without-evidence",
        "two-sources",
        "duplicate-nickname",
        "non-web-link",
        "bad-dates",
        "wrong-type",
        "unknown-field",
        "missing-skill",
    ],
)
def test_bad_files_are_refused_and_nothing_is_written(client: TestClient, engines, how: str) -> None:
    source, target = engines
    _fill(client, source)
    bad = _broken(_export(client, source), how)
    before = _row_counts(target)

    response = _upload(client, target, bad)

    assert response.status_code == 422, response.json()
    assert response.json()["detail"].startswith("This backup can't be restored:")
    assert _row_counts(target) == before


def test_not_json_is_refused(client: TestClient, engines) -> None:
    _, target = engines

    response = _upload(client, target, b"%PDF-1.4 not json")

    assert response.status_code == 422
    assert "isn't a JSON file" in response.json()["detail"]


def test_oversized_file_is_refused(client: TestClient, engines) -> None:
    _, target = engines

    response = _upload(client, target, b" " * (import_service.MAX_IMPORT_BYTES + 1))

    assert response.status_code == 422
    assert "too large" in response.json()["detail"]


# --- preview ----------------------------------------------------------------------------------


def test_preview_reports_counts_and_writes_nothing(client: TestClient, engines) -> None:
    source, target = engines
    _fill(client, source)
    backup = _export(client, source)
    before = _row_counts(target)

    body = _upload(client, target, backup, "/import/preview").json()

    assert body["problems"] == []
    assert body["app_empty"] is True
    assert body["counts"]["skills"] == 2
    assert body["counts"]["nicknames"] == 1
    assert body["counts"]["job_descriptions"] == 2
    assert _row_counts(target) == before


def test_preview_lists_every_problem(client: TestClient, engines) -> None:
    source, target = engines
    _fill(client, source)
    bad = _broken(_broken(_export(client, source), "verified-without-evidence"), "non-web-link")

    body = _upload(client, target, bad, "/import/preview").json()

    assert any("verified but has no linked evidence" in p for p in body["problems"])
    assert any("isn't an http(s) link" in p for p in body["problems"])


def test_preview_says_when_the_app_is_not_empty(client: TestClient, engines) -> None:
    source, _ = engines
    _fill(client, source)

    body = _upload(client, source, _export(client, source), "/import/preview").json()

    assert body["app_empty"] is False
