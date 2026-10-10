"""Tests for "Fill from my CV": CV text -> draft profile entries, read-only.

Same TestClient + StaticPool in-memory SQLite pattern as the other API tests.
"""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.services.cv_profile_service import parse_date
from app.core.services.skill_service import normalize_text
from app.db.models import Education, Project, WorkExperience
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


ONE_LINE = """Jane Doe
jane@example.com | github.com/jane
SUMMARY
Backend developer who likes clean APIs.
WORK EXPERIENCE
Software Engineer | Acme Corp | Jan 2022 - Present
• Built REST APIs in FastAPI serving 1M requests a day
• Led migration to PostgreSQL
Backend Intern, Globex — Jun 2021 – Dec 2021
- Wrote ETL jobs in Python
EDUCATION
B.Tech in Computer Science, Anna University, 2017 - 2021
SKILLS
Python, Docker
"""

STACKED = """Experience
Acme Corp
Senior Developer
03/2020 to 06/2023
• Did things
Projects
FundsApp
https://github.com/jane/fundsapp
A budgeting app built with React.
WeatherBot
Telegram bot for weather alerts.
Education:
State University
Bachelor of Science in Mathematics
2014 – 2018
"""


def _drafts(client: TestClient, text: str) -> dict:
    response = client.post("/profile/cv-drafts", data={"text": text})
    assert response.status_code == 200, response.json()
    return response.json()


def _work(body: dict) -> list[tuple]:
    return [(w["company"], w["role"], w["start_date"], w["end_date"]) for w in body["work_experiences"]]


# --- layouts --------------------------------------------------------------------------


def test_one_line_headers(client: TestClient) -> None:
    body = _drafts(client, ONE_LINE)

    assert body["sections_found"] == ["work", "education"]
    assert _work(body) == [
        ("Acme Corp", "Software Engineer", "2022-01-01", None),
        ("Globex", "Backend Intern", "2021-06-01", "2021-12-01"),
    ]
    assert body["work_experiences"][0]["description"] == (
        "Built REST APIs in FastAPI serving 1M requests a day\nLed migration to PostgreSQL"
    )
    assert body["work_experiences"][0]["dates_text"] == "Jan 2022 - Present"
    [edu] = body["educations"]
    assert (edu["institution"], edu["degree"], edu["field_of_study"]) == (
        "Anna University",
        "B.Tech",
        "Computer Science",
    )
    assert (edu["start_date"], edu["end_date"]) == ("2017-01-01", "2021-01-01")
    assert body["projects"] == []  # no Projects heading: nothing invented


def test_stacked_headers_and_dateless_projects(client: TestClient) -> None:
    body = _drafts(client, STACKED)

    assert _work(body) == [("Acme Corp", "Senior Developer", "2020-03-01", "2023-06-01")]
    assert [(p["name"], p["url"]) for p in body["projects"]] == [
        ("FundsApp", "https://github.com/jane/fundsapp"),
        ("WeatherBot", None),
    ]
    assert body["projects"][1]["description"] == "Telegram bot for weather alerts."
    [edu] = body["educations"]
    assert (edu["institution"], edu["degree"], edu["field_of_study"]) == (
        "State University",
        "Bachelor of Science",
        "Mathematics",
    )


def test_role_at_company_and_varied_headings(client: TestClient) -> None:
    text = """Professional Experience:
Data Analyst at Initech (Sept 2019 to 2020)
* Reports
Academic Background
Springfield College
Diploma in Business, 2015-2017
Personal Projects
Chess engine (2021)
Plays chess."""
    body = _drafts(client, text)

    assert _work(body) == [("Initech", "Data Analyst", "2019-09-01", "2020-01-01")]
    [edu] = body["educations"]
    assert (edu["institution"], edu["degree"], edu["field_of_study"]) == (
        "Springfield College",
        "Diploma",
        "Business",
    )
    assert [p["name"] for p in body["projects"]] == ["Chess engine"]  # trailing "(2021)" dropped


def test_a_cv_without_recognisable_sections_gives_empty_drafts(client: TestClient) -> None:
    body = _drafts(client, "I am a developer with five years of experience.\nI like Python.")

    assert body["sections_found"] == []
    assert body["work_experiences"] == body["educations"] == body["projects"] == []


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Jan 2022", "2022-01-01"),
        ("September 2019", "2019-09-01"),
        ("Sept. 2019", "2019-09-01"),
        ("03/2021", "2021-03-01"),
        ("3-2021", "2021-03-01"),
        ("2019", "2019-01-01"),
        ("13/2021", None),
        ("soon", None),
    ],
)
def test_dates_become_the_first_day_of_their_period(text: str, expected: str | None) -> None:
    parsed = parse_date(text)
    assert (parsed.isoformat() if parsed else None) == expected


# --- honesty rules --------------------------------------------------------------------


@pytest.mark.parametrize("cv", [ONE_LINE, STACKED])
def test_every_draft_word_comes_from_the_cv(client: TestClient, cv: str) -> None:
    body = _drafts(client, cv)
    source = normalize_text(cv)
    texts = []
    for kind, fields in (
        ("work_experiences", ("company", "role", "dates_text", "description")),
        ("educations", ("institution", "degree", "field_of_study", "dates_text", "description")),
        ("projects", ("name", "url", "dates_text", "description")),
    ):
        for draft in body[kind]:
            for f in fields:
                if draft[f]:
                    texts.extend(draft[f].split("\n"))
    assert texts
    for text in texts:
        assert normalize_text(text) in source, text


def test_reading_drafts_saves_nothing(client: TestClient, engine: Engine) -> None:
    _drafts(client, ONE_LINE)
    _drafts(client, STACKED)

    with Session(engine) as db:
        for model in (WorkExperience, Education, Project):
            assert db.scalar(select(func.count()).select_from(model)) == 0


def test_entries_already_in_the_profile_are_flagged(client: TestClient) -> None:
    client.post("/work-experiences", json={"company": "acme corp", "role": "Software Engineer", "start_date": "2022-01-01"})
    client.post("/educations", json={"institution": "Anna University"})

    body = _drafts(client, ONE_LINE)

    assert [w["duplicate"] for w in body["work_experiences"]] == [True, False]
    assert [e["duplicate"] for e in body["educations"]] == [True]


def test_saving_a_draft_uses_the_normal_rules(client: TestClient) -> None:
    [first, _] = _drafts(client, ONE_LINE)["work_experiences"]
    fields = ("company", "role", "start_date", "end_date", "description")

    saved = client.post("/work-experiences", json={f: first[f] for f in fields})
    bad = client.post("/work-experiences", json={**{f: first[f] for f in fields}, "end_date": "2000-01-01"})

    assert saved.status_code == 201
    assert bad.status_code == 422  # end before start: the same rule as typing it by hand


# --- input --------------------------------------------------------------------------------


def test_file_upload_works_too(client: TestClient) -> None:
    response = client.post(
        "/profile/cv-drafts", files={"file": ("cv.txt", ONE_LINE.encode(), "text/plain")}
    )

    assert response.status_code == 200
    assert len(response.json()["work_experiences"]) == 2


@pytest.mark.parametrize(
    ("kwargs", "status"),
    [
        ({}, 422),  # neither file nor text
        ({"data": {"text": "   "}}, 422),  # blank
        ({"files": {"file": ("cv.exe", b"MZ", "application/octet-stream")}}, 415),
    ],
)
def test_bad_input_is_refused(client: TestClient, kwargs: dict, status: int) -> None:
    assert client.post("/profile/cv-drafts", **kwargs).status_code == status
