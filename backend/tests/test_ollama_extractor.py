"""Tests for the optional local AI reader (Ollama) and the combined reader around it.

No Ollama is needed: the HTTP layer is faked with httpx.MockTransport, and API tests
either swap in a fake AI reader or point at a port where nothing listens.
"""

import json
from collections.abc import Iterator

import httpx
import pytest
from fastapi import Depends
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.ai.providers.ollama_extractor import (
    MAX_PROPOSALS,
    MAX_RESPONSE_BYTES,
    CombinedRequirementExtractor,
    ExtractorUnavailableError,
    OllamaRequirementExtractor,
)
from app.ai.schemas import ExtractedRequirement, ExtractionResult
from app.core.services import skill_service
from app.db.models import JobDescription, JobRequirement, User
from app.dependencies import get_db, get_requirement_extractor
from app.main import app
from database import Base

POSTING = "We need Python and Kubernetes. Terraform is a plus."


def _ollama_reply(requirements: list[dict]) -> dict:
    return {"message": {"role": "assistant", "content": json.dumps({"requirements": requirements})}}


def _ollama(handler) -> OllamaRequirementExtractor:
    return OllamaRequirementExtractor("llama3.2", transport=httpx.MockTransport(handler))


class FakeAI:
    """Stands in for the Ollama reader: returns fixed proposals, or raises."""

    def __init__(self, requirements: list[ExtractedRequirement] | None = None, fail: bool = False) -> None:
        self._requirements = requirements or []
        self._fail = fail

    def extract_requirements(self, raw_text: str) -> ExtractionResult:
        if self._fail:
            raise ExtractorUnavailableError("Ollama isn't reachable (ConnectError).")
        return ExtractionResult(requirements=self._requirements)


def _mention(name: str, required: bool = True, text: str | None = None) -> ExtractedRequirement:
    return ExtractedRequirement(text=text or f"We use {name}", is_required=required, skill_mention=name)


# --- the Ollama HTTP client --------------------------------------------------------------


def test_sends_one_local_chat_request_and_parses_the_reply() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=_ollama_reply([{"text": "Kubernetes", "skill_mention": "Kubernetes"}]))

    result = _ollama(handler).extract_requirements(POSTING)

    assert [r.skill_mention for r in result.requirements] == ["Kubernetes"]
    [request] = seen
    assert str(request.url) == "http://127.0.0.1:11434/api/chat"
    body = json.loads(request.content)
    assert body["model"] == "llama3.2"
    assert body["stream"] is False
    assert body["format"]["properties"]["requirements"]["type"] == "array"
    assert POSTING in body["messages"][0]["content"]


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(500, json={"error": "model not found"}),
        httpx.Response(200, json={"message": {"content": "not json at all"}}),
        httpx.Response(200, json={"message": {"content": json.dumps({"requirements": "oops"})}}),
        httpx.Response(200, json={"unexpected": True}),
        httpx.Response(200, content=b"x" * (MAX_RESPONSE_BYTES + 1)),
    ],
    ids=["error-status", "not-json", "wrong-shape", "no-message", "too-large"],
)
def test_unusable_replies_raise_unavailable(response: httpx.Response) -> None:
    with pytest.raises(ExtractorUnavailableError):
        _ollama(lambda request: response).extract_requirements(POSTING)


def test_unreachable_ollama_raises_unavailable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    with pytest.raises(ExtractorUnavailableError, match="isn't reachable"):
        _ollama(handler).extract_requirements(POSTING)


def test_too_many_proposals_are_capped() -> None:
    many = [{"text": f"x{i}", "skill_mention": f"x{i}"} for i in range(MAX_PROPOSALS + 20)]

    result = _ollama(lambda request: httpx.Response(200, json=_ollama_reply(many))).extract_requirements(POSTING)

    assert len(result.requirements) == MAX_PROPOSALS


# --- the combined reader -----------------------------------------------------------------


TERMS = {"Python": ["Python", "py"], "Docker": ["Docker"]}


def test_combined_adds_only_named_skills_beyond_the_matcher() -> None:
    ai = FakeAI(
        [
            _mention("python"),  # the matcher already found Python
            _mention("py"),  # an alias of Python: same skill, dropped
            _mention("Kubernetes"),
            _mention("kubernetes"),  # same mention twice
            _mention("Terraform", required=False),
            ExtractedRequirement(text="5+ years of experience", skill_mention=None),  # names no skill
            _mention("A" * 61),  # far too long to be a skill name
        ]
    )
    combined = CombinedRequirementExtractor(TERMS, ai)

    result = combined.extract_requirements(POSTING)

    assert [(r.text, r.skill_mention, r.is_required) for r in result.requirements] == [
        ("Python", "Python", True),
        ("Kubernetes", "Kubernetes", True),
        ("Terraform", "Terraform", False),
    ]
    assert combined.note is None


def test_combined_falls_back_to_the_matcher_when_the_ai_is_unavailable() -> None:
    combined = CombinedRequirementExtractor(TERMS, FakeAI(fail=True))

    result = combined.extract_requirements(POSTING)

    assert [r.text for r in result.requirements] == ["Python"]
    assert combined.note is not None
    assert combined.note.startswith("AI reader unavailable, used your skill list only.")


# --- through the API -----------------------------------------------------------------------


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


def _use_ai(ai: FakeAI) -> None:
    def override(db: Session = Depends(get_db)) -> CombinedRequirementExtractor:
        return CombinedRequirementExtractor(skill_service.skill_terms(db), ai)

    app.dependency_overrides[get_requirement_extractor] = override


def _skill(engine: Engine, name: str) -> int:
    with Session(engine, autoflush=False) as db:
        skill_id = skill_service.create_skill(db, name).id
        db.commit()
    return skill_id


def _job(client: TestClient) -> int:
    return client.post("/job-descriptions", json={"raw_text": POSTING}).json()["id"]


def test_ai_proposals_are_still_grounded_and_never_create_skills(client: TestClient, engine: Engine) -> None:
    _skill(engine, "Python")
    _use_ai(FakeAI([_mention("Kubernetes"), _mention("Rust")]))  # Rust isn't in the posting
    job_id = _job(client)

    body = client.post(f"/job-descriptions/{job_id}/extract").json()

    assert [(r["requirement_text"], r["skill_name"]) for r in body["accepted"]] == [
        ("Python", "Python"),
        ("Kubernetes", None),
    ]
    assert {"text": "Rust", "reason": "not found in job description text"} in body["rejected"]
    assert body["note"] is None
    assert [s["name"] for s in client.get("/skills").json()] == ["Python"]


def test_saving_the_skill_then_looking_again_links_the_requirement(client: TestClient, engine: Engine) -> None:
    _use_ai(FakeAI([_mention("Kubernetes")]))
    job_id = _job(client)
    client.post(f"/job-descriptions/{job_id}/extract")
    kubernetes_id = _skill(engine, "Kubernetes")

    body = client.post(f"/job-descriptions/{job_id}/extract-new").json()

    assert [(r["requirement_text"], r["skill_id"]) for r in body["linked"]] == [("Kubernetes", kubernetes_id)]
    assert body["accepted"] == []  # linked in place, not added a second time
    requirements = client.get(f"/job-descriptions/{job_id}").json()["requirements"]
    assert [(r["requirement_text"], r["skill_name"]) for r in requirements] == [("Kubernetes", "Kubernetes")]


def test_linking_never_doubles_up_a_skill_the_job_already_has(client: TestClient, engine: Engine) -> None:
    python_id = _skill(engine, "Python")
    with Session(engine, autoflush=False) as db:
        job = JobDescription(user=User(email="me@career-ai.local"), raw_text="Python. PYTHON.")
        db.add(job)
        db.flush()
        db.add_all(
            [
                JobRequirement(job_description_id=job.id, skill_id=python_id, requirement_text="Python"),
                JobRequirement(job_description_id=job.id, skill_id=None, requirement_text="PYTHON"),
            ]
        )
        db.commit()
        job_id = job.id

    body = client.post(f"/job-descriptions/{job_id}/extract-new").json()

    assert body["linked"] == []
    skills = sorted(str(r["skill_id"]) for r in client.get(f"/job-descriptions/{job_id}").json()["requirements"])
    assert skills == sorted([str(python_id), "None"])


def test_real_wiring_falls_back_when_ollama_is_not_running(
    client: TestClient, engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OLLAMA_MODEL", "llama3.2")
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://127.0.0.1:9")  # nothing listens here
    _skill(engine, "Python")
    job_id = _job(client)

    body = client.post(f"/job-descriptions/{job_id}/extract").json()

    assert [r["requirement_text"] for r in body["accepted"]] == ["Python"]
    assert body["note"].startswith("AI reader unavailable, used your skill list only.")
    assert client.get("/job-descriptions/extractor").json() == {
        "name": "ollama",
        "paid": False,
        "model": "llama3.2",
    }


def test_the_paid_reader_keeps_priority_over_ollama(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OLLAMA_MODEL", "llama3.2")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-not-used")

    assert client.get("/job-descriptions/extractor").json() == {"name": "claude", "paid": True, "model": None}


def test_blank_ollama_model_means_off(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OLLAMA_MODEL", "   ")

    assert client.get("/job-descriptions/extractor").json() == {"name": "skill_list", "paid": False, "model": None}
