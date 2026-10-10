"""Your name: read from the top of the CV, editable via PATCH /me, and known to the assistant."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.services.cv_profile_service import read_name
from app.dependencies import get_db
from app.main import app
from database import Base

CV = "B. Mohammed Thariq\nChennai, India | thariq@example.com | +91 98765 43210\n\nSkills\nPython, Docker"


@pytest.mark.parametrize(
    ("text", "name"),
    [
        (CV, "B. Mohammed Thariq"),
        ("JANE DOE\nSoftware Engineer", "Jane Doe"),  # all caps is tidied, same words
        ("Curriculum Vitae\nJane Doe\njane@x.com", "Jane Doe"),  # a heading line is skipped
        ("Jane Doe | jane@x.com | linkedin.com/in/jane", "Jane Doe"),
        ("Software Engineer\nPython Developer\nEducation", None),  # job titles aren't names
        ("Experience\nAcme 2020 - 2022", None),
        ("", None),
    ],
)
def test_the_name_is_read_from_the_top_of_the_cv(text: str, name: str | None) -> None:
    assert read_name(text) == name


def test_only_the_top_lines_are_read() -> None:
    assert read_name("Skills\nPython\nDocker\nSQL\nAWS\nJane Doe") is None


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


def test_the_name_can_be_saved_tidied_and_cleared(client: TestClient) -> None:
    assert client.get("/me").json()["full_name"] is None

    assert client.patch("/me", json={"full_name": "  Jane   Doe "}).json()["full_name"] == "Jane Doe"
    assert client.get("/me").json()["full_name"] == "Jane Doe"
    assert client.patch("/me", json={"full_name": "   "}).json()["full_name"] is None
    assert client.patch("/me", json={"full_name": "x" * 101}).status_code == 422


def test_adding_the_cv_saves_the_name_but_never_overwrites_one(client: TestClient) -> None:
    body = client.post("/cv/add-all", data={"text": CV}).json()
    assert body["name_saved"] == "B. Mohammed Thariq"
    assert client.get("/me").json()["full_name"] == "B. Mohammed Thariq"

    client.patch("/me", json={"full_name": "Thariq"})
    body = client.post("/cv/add-all", data={"text": CV}).json()
    assert body["name_saved"] is None
    assert client.get("/me").json()["full_name"] == "Thariq"


def test_fill_from_my_cv_shows_the_name(client: TestClient) -> None:
    assert client.post("/profile/cv-drafts", data={"text": CV}).json()["name"] == "B. Mohammed Thariq"


def test_the_assistant_knows_your_name(client: TestClient) -> None:
    client.post("/cv/add-all", data={"text": CV})

    body = client.post("/assistant/ask", json={"question": "what is my name ?"}).json()

    assert body["sources"][0]["kind"] == "profile"
    assert "Your name is B. Mohammed Thariq." in body["answer"]


def test_without_a_name_the_assistant_says_how_to_add_it(client: TestClient) -> None:
    body = client.post("/assistant/ask", json={"question": "What is my name?"}).json()

    assert body["sources"][0]["kind"] == "profile"
    assert "Your name is not saved yet" in body["answer"]
