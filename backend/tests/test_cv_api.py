"""HTTP tests for CV upload: scan (preview) and save (confirmed choices).

Same TestClient + dependency_overrides[get_db] + StaticPool in-memory SQLite pattern as
the other API tests. Sample PDF and .docx files are built inside the tests, so no
fixture files or extra packages are needed.
"""

import io
import zipfile
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.services import cv_import_service, skill_service
from app.db.models import CVSkillPresence, UserSkill
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


@pytest.fixture()
def skills(engine: Engine) -> dict[str, int]:
    """Python, Java, Docker, and PostgreSQL with the alias Postgres."""
    with Session(engine, autoflush=False) as db:
        ids = {name: skill_service.create_skill(db, name).id for name in ["Python", "Java", "Docker"]}
        postgres = skill_service.create_skill(db, "PostgreSQL")
        skill_service.add_alias(db, postgres, "Postgres")
        ids["PostgreSQL"] = postgres.id
        db.commit()
    return ids


# --- tiny sample files ----------------------------------------------------------


def _make_pdf(text: str) -> bytes:
    """A minimal one-page PDF whose page shows `text` (empty text -> no text at all)."""
    stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode() if text else b""
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = b"%PDF-1.4\n"
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % number + body + b"\nendobj\n"
    xref_at = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    for offset in offsets:
        out += b"%010d 00000 n \n" % offset
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (
        len(objects) + 1,
        xref_at,
    )
    return out


def _make_docx(paragraphs: list[str], prolog: str = "") -> bytes:
    body = "".join(f"<w:p><w:r><w:t>{p}</w:t></w:r></w:p>" for p in paragraphs)
    xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        + prolog
        + '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        + f"<w:body>{body}</w:body></w:document>"
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("word/document.xml", xml)
    return buffer.getvalue()


def _scan_file(client: TestClient, filename: str, content: bytes):
    return client.post("/cv/scan", files={"file": (filename, content, "application/octet-stream")})


def _found(response) -> list[tuple[str, str]]:
    assert response.status_code == 200, response.text
    return [(f["skill_name"], f["matched_text"]) for f in response.json()["found"]]


def _presence_count(engine: Engine) -> int:
    with Session(engine, autoflush=False) as db:
        return db.scalar(select(func.count()).select_from(CVSkillPresence))


# --- scanning each format ----------------------------------------------------------


def test_scan_txt_finds_skills_by_name_and_alias_whole_words_only(
    client: TestClient, skills: dict[str, int]
) -> None:
    cv = b"Experienced in Python and Postgres. Some JavaScript."

    response = _scan_file(client, "cv.txt", cv)

    assert _found(response) == [("Python", "Python"), ("PostgreSQL", "Postgres")]
    assert response.json()["characters"] == len(cv)


def test_scan_pdf(client: TestClient, skills: dict[str, int]) -> None:
    response = _scan_file(client, "cv.PDF", _make_pdf("Skills: Python, Docker"))

    assert _found(response) == [("Python", "Python"), ("Docker", "Docker")]


def test_scan_docx(client: TestClient, skills: dict[str, int]) -> None:
    response = _scan_file(client, "cv.docx", _make_docx(["Skills", "Docker and Postgres"]))

    assert _found(response) == [("Docker", "Docker"), ("PostgreSQL", "Postgres")]


def test_scan_pasted_text(client: TestClient, skills: dict[str, int]) -> None:
    response = client.post("/cv/scan", data={"text": "I write java and docker daily"})

    assert _found(response) == [("Java", "java"), ("Docker", "docker")]


# --- scanning is a preview -------------------------------------------------------------


def test_scan_saves_nothing_and_reports_what_is_already_on_the_cv(
    client: TestClient, engine: Engine, skills: dict[str, int]
) -> None:
    client.patch(f"/skills/{skills['Python']}/cv-presence", json={"present": True})
    client.patch(f"/skills/{skills['Docker']}/cv-presence", json={"present": True})
    before = _presence_count(engine)

    body = _scan_file(client, "cv.txt", b"Python and Java").json()

    assert [(f["skill_name"], f["on_cv"]) for f in body["found"]] == [
        ("Python", True),
        ("Java", False),
    ]
    assert [s["skill_name"] for s in body["on_cv_not_found"]] == ["Docker"]
    assert _presence_count(engine) == before


# --- bad input --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("filename", "content", "status"),
    [
        ("photo.png", b"\x89PNG not a cv", 415),
        ("cv", b"Python", 415),  # no extension
        ("cv.pdf", b"%PDF-1.4 this is not really a pdf", 415),
        ("cv.docx", b"not a zip file", 415),
        ("cv.docx", _make_docx(["Python"], prolog='<!DOCTYPE x [<!ENTITY a "b">]>'), 415),
        ("cv.txt", b"   \n\t  ", 422),
        ("cv.pdf", _make_pdf(""), 422),  # a PDF with no text, like a scanned image
    ],
)
def test_unusable_files_give_a_clear_error(
    client: TestClient, engine: Engine, skills: dict[str, int], filename, content, status
) -> None:
    response = _scan_file(client, filename, content)

    assert response.status_code == status
    assert response.json()["detail"]
    assert _presence_count(engine) == 0


def test_a_file_over_the_limit_is_413(client: TestClient, skills: dict[str, int]) -> None:
    too_big = b"Python " * (cv_import_service.MAX_CV_BYTES // 7 + 1)

    assert _scan_file(client, "cv.txt", too_big).status_code == 413


def test_scan_needs_exactly_one_of_file_or_text(client: TestClient, skills: dict[str, int]) -> None:
    assert client.post("/cv/scan").status_code == 422
    both = client.post(
        "/cv/scan",
        data={"text": "Python"},
        files={"file": ("cv.txt", b"Python", "text/plain")},
    )
    assert both.status_code == 422


# --- saving confirmed choices -------------------------------------------------------


def _cv_status(client: TestClient, skill_id: int) -> str:
    return client.get(f"/skills/{skill_id}/cv-status").json()["cv_status"]


def test_save_marks_present_and_absent_and_leaves_others_alone(
    client: TestClient, engine: Engine, skills: dict[str, int]
) -> None:
    client.patch(f"/skills/{skills['Docker']}/cv-presence", json={"present": True})

    response = client.put(
        "/cv/presence",
        json={
            "present_skill_ids": [skills["Python"], skills["PostgreSQL"]],
            "absent_skill_ids": [skills["Docker"]],
        },
    )

    assert response.status_code == 200
    assert {(r["skill_name"], r["present"]) for r in response.json()} == {
        ("Python", True),
        ("PostgreSQL", True),
        ("Docker", False),
    }
    assert _cv_status(client, skills["Python"]) == "present"
    assert _cv_status(client, skills["Docker"]) == "not_present"
    with Session(engine, autoflush=False) as db:
        java_rows = db.scalar(
            select(func.count())
            .select_from(CVSkillPresence)
            .where(CVSkillPresence.skill_id == skills["Java"])
        )
    assert java_rows == 0  # never mentioned, so never touched


def test_save_with_an_unknown_skill_is_404_and_saves_nothing(
    client: TestClient, engine: Engine, skills: dict[str, int]
) -> None:
    response = client.put(
        "/cv/presence", json={"present_skill_ids": [skills["Python"], 999], "absent_skill_ids": []}
    )

    assert response.status_code == 404
    assert _presence_count(engine) == 0


def test_save_with_a_skill_in_both_lists_is_422(
    client: TestClient, engine: Engine, skills: dict[str, int]
) -> None:
    response = client.put(
        "/cv/presence",
        json={"present_skill_ids": [skills["Python"]], "absent_skill_ids": [skills["Python"]]},
    )

    assert response.status_code == 422
    assert _presence_count(engine) == 0


# --- the key rule: a CV is a claim, not proof ----------------------------------------


def test_scanning_and_saving_a_cv_never_changes_verification(
    client: TestClient, engine: Engine, skills: dict[str, int]
) -> None:
    claim = client.post("/user-skills", json={"skill_id": skills["Python"]}).json()

    _scan_file(client, "cv.txt", b"Python, Docker, Postgres")
    client.put(
        "/cv/presence",
        json={"present_skill_ids": [skills["Python"], skills["Docker"], skills["PostgreSQL"]]},
    )

    claims = client.get("/user-skills").json()
    assert [(c["id"], c["status"], c["evidence_ids"]) for c in claims] == [
        (claim["id"], "provisional", [])
    ]
    with Session(engine, autoflush=False) as db:
        assert db.scalar(select(func.count()).select_from(UserSkill)) == 1
