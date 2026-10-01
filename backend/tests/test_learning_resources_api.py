"""Tests for learning resources: derived YouTube search links and user-saved links.

Same TestClient + dependency_overrides[get_db] + StaticPool in-memory SQLite pattern
as test_user_skills_api.py. No network: search links are built, never fetched.
"""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.services import learning_service, skill_service
from app.db.models import LearningResource
from app.db.models.enums import LearningMode
from app.dependencies import get_db
from app.main import app
from database import Base

THEORY = "theory_interview"
PRACTICAL = "technical_practical"


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


def _create_skill(engine: Engine, name: str) -> int:
    with Session(engine, autoflush=False) as db:
        skill = skill_service.create_skill(db, name)
        db.commit()
        return skill.id


def _count(engine: Engine) -> int:
    with Session(engine, autoflush=False) as db:
        return db.scalar(select(func.count()).select_from(LearningResource))


def _add(client: TestClient, skill_id: int, mode: str, title: str, url: str):
    return client.post(
        f"/skills/{skill_id}/learning-resources", json={"mode": mode, "title": title, "url": url}
    )


def _modes(client: TestClient, skill_id: int) -> dict[str, dict]:
    response = client.get(f"/skills/{skill_id}/learning-resources")
    assert response.status_code == 200
    return {entry["mode"]: entry for entry in response.json()["modes"]}


# --- derived search links ------------------------------------------------------


@pytest.mark.parametrize(
    ("skill_name", "mode", "expected_query_param"),
    [
        ("Docker", LearningMode.THEORY_INTERVIEW, "Docker+interview+questions"),
        ("C++", LearningMode.TECHNICAL_PRACTICAL, "C%2B%2B+full+course+tutorial"),
        ("C#", LearningMode.THEORY_INTERVIEW, "C%23+interview+questions"),
        ("Machine Learning", LearningMode.TECHNICAL_PRACTICAL, "Machine+Learning+full+course+tutorial"),
    ],
)
def test_youtube_search_url_encodes_the_skill_name(skill_name, mode, expected_query_param) -> None:
    assert learning_service.youtube_search_url(skill_name, mode) == (
        "https://www.youtube.com/results?search_query=" + expected_query_param
    )


def test_a_skill_with_nothing_saved_still_gets_a_search_link_per_mode(
    client: TestClient, engine: Engine
) -> None:
    skill_id = _create_skill(engine, "Docker")

    body = client.get(f"/skills/{skill_id}/learning-resources").json()

    assert body["skill_id"] == skill_id
    assert body["skill_name"] == "Docker"
    assert [entry["mode"] for entry in body["modes"]] == [THEORY, PRACTICAL]
    theory, practical = body["modes"]
    assert theory["search_query"] == "Docker interview questions"
    assert theory["search_url"].endswith("search_query=Docker+interview+questions")
    assert practical["search_query"] == "Docker full course tutorial"
    assert theory["resources"] == [] and practical["resources"] == []


def test_unknown_skill_is_404_for_list_and_add(client: TestClient, engine: Engine) -> None:
    assert client.get("/skills/999/learning-resources").status_code == 404
    assert _add(client, 999, THEORY, "Docs", "https://example.com").status_code == 404
    assert _count(engine) == 0


# --- saving and removing links ----------------------------------------------------


def test_add_then_list_shows_it_under_its_own_mode_only(client: TestClient, engine: Engine) -> None:
    skill_id = _create_skill(engine, "Docker")

    response = _add(client, skill_id, PRACTICAL, "  Docker docs  ", "  https://docs.docker.com/  ")

    assert response.status_code == 201
    saved = response.json()
    assert saved["skill_id"] == skill_id
    assert saved["mode"] == PRACTICAL
    assert saved["title"] == "Docker docs"  # stripped
    assert saved["url"] == "https://docs.docker.com/"  # stripped
    modes = _modes(client, skill_id)
    assert [r["id"] for r in modes[PRACTICAL]["resources"]] == [saved["id"]]
    assert modes[THEORY]["resources"] == []


@pytest.mark.parametrize(
    "bad_url",
    ["javascript:alert(1)", "ftp://files.example.com/x", "docs.docker.com", "https://", "  "],
)
def test_non_web_links_are_rejected_and_nothing_is_saved(
    client: TestClient, engine: Engine, bad_url: str
) -> None:
    skill_id = _create_skill(engine, "Docker")

    response = _add(client, skill_id, THEORY, "Something", bad_url)

    assert response.status_code == 422
    assert _count(engine) == 0


def test_blank_title_is_422(client: TestClient, engine: Engine) -> None:
    skill_id = _create_skill(engine, "Docker")

    assert _add(client, skill_id, THEORY, "   ", "https://example.com").status_code == 422
    assert _count(engine) == 0


def test_bad_mode_is_422(client: TestClient, engine: Engine) -> None:
    skill_id = _create_skill(engine, "Docker")

    assert _add(client, skill_id, "not_a_mode", "Docs", "https://example.com").status_code == 422


def test_same_link_twice_in_one_mode_is_409_but_allowed_in_the_other_mode(
    client: TestClient, engine: Engine
) -> None:
    skill_id = _create_skill(engine, "Docker")
    assert _add(client, skill_id, THEORY, "Docs", "https://docs.docker.com/").status_code == 201

    duplicate = _add(client, skill_id, THEORY, "Docs again", "https://docs.docker.com/")
    other_mode = _add(client, skill_id, PRACTICAL, "Docs", "https://docs.docker.com/")

    assert duplicate.status_code == 409
    assert other_mode.status_code == 201
    assert _count(engine) == 2


def test_delete_removes_it_and_a_missing_id_is_404(client: TestClient, engine: Engine) -> None:
    skill_id = _create_skill(engine, "Docker")
    resource_id = _add(client, skill_id, THEORY, "Docs", "https://docs.docker.com/").json()["id"]

    response = client.delete(f"/learning-resources/{resource_id}")

    assert response.status_code == 204
    assert _modes(client, skill_id)[THEORY]["resources"] == []
    assert client.delete(f"/learning-resources/{resource_id}").status_code == 404
