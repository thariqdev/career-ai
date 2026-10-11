"""Tests for RAG stage 69: tools (exact answers from the database) and routing."""

import json
from collections.abc import Iterator

import httpx
import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.models import CVSkillPresence, Skill, User, UserSkill
from app.rag import tools
from app.rag.evaluate import fill_fixture
from app.rag.router import OllamaRouter, cascade_route, guard, guarded_keyword_route, keyword_route, tool_schemas
from app.rag.router_eval import DEV, HELD_OUT, JOBS, TEST, score
from app.rag.tools import TOOLS, ToolCall
from database import Base


@pytest.fixture()
def db() -> Iterator[Session]:
    engine = create_engine("sqlite://", poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine, autoflush=False) as session:
        yield session
    engine.dispose()


@pytest.fixture()
def user(db: Session) -> User:
    return fill_fixture(db)


# --- the tools ---------------------------------------------------------------------------


def test_skills_without_proof_lists_claimed_and_cv_only_skills(db: Session, user: User) -> None:
    cv_only = Skill(name="Rust")
    db.add(cv_only)
    db.flush()
    db.add(CVSkillPresence(user=user, skill_id=cv_only.id, present=True))
    db.flush()

    note = tools.run(db, user, ToolCall("skills_without_proof"))

    assert note.kind == "tool" and note.link == "/skills"
    assert note.text == (
        "Skills with no proof yet: 6. "
        "Claimed but no proof linked: Docker, Git, PostgreSQL, React, TypeScript. "
        "On your CV but not claimed or proven: Rust."
    )  # Python is verified, so it isn't listed


def test_verified_skills_name_their_proof(db: Session, user: User) -> None:
    assert tools.run(db, user, ToolCall("verified_skills")).text == (
        "Verified (proven) skills: 1. Python (proof: FundsApp repo)."
    )


def test_skills_on_cv(db: Session, user: User) -> None:
    assert tools.run(db, user, ToolCall("skills_on_cv")).text == (
        "Skills on your CV: 6. Docker, Git, PostgreSQL, Python, React, TypeScript."
    )


def test_job_gaps_for_one_job_all_jobs_or_an_unknown_job(db: Session, user: User) -> None:
    one = tools.run(db, user, ToolCall("job_gaps", "Acme"))
    every = tools.run(db, user, ToolCall("job_gaps"))
    unknown = tools.run(db, user, ToolCall("job_gaps", "Initrode"))

    assert one.title == "Missing skills for Backend Engineer at Acme" and one.link.startswith("/job-descriptions/")
    assert "Kubernetes" in one.text and "AWS" in one.text and "GraphQL" not in one.text
    assert "Backend Engineer at Acme" in every.text and "Missing for Frontend Developer at Globex: GraphQL." in every.text
    assert unknown.text.startswith('No job matches "Initrode". Your jobs: Backend Engineer at Acme, Frontend Developer at Globex')


def test_learn_first_ranks_by_how_many_jobs_need_it(db: Session, user: User) -> None:
    text = tools.run(db, user, ToolCall("learn_first")).text

    assert text.startswith("Missing skills to learn first, most needed first: 1. AWS (needed by 1 job)")
    assert "GraphQL" in text and "Kubernetes" in text


def test_tools_only_read(db: Session, user: User) -> None:
    db.commit()
    before = db.scalar(select(func.count()).select_from(UserSkill))
    for name in TOOLS:
        tools.run(db, user, ToolCall(name))

    assert not db.new and not db.dirty and not db.deleted
    assert db.scalar(select(func.count()).select_from(UserSkill)) == before


def test_an_unknown_tool_is_refused(db: Session, user: User) -> None:
    with pytest.raises(ValueError):
        tools.run(db, user, ToolCall("delete_everything"))


# --- the keyword router ------------------------------------------------------------------


def test_keyword_rules_on_the_dev_set() -> None:
    right, wrong, missed, mistakes = score(keyword_route, DEV)

    assert right == len(DEV), mistakes


def test_keyword_rules_never_pick_a_wrong_tool_on_unplanned_wording() -> None:
    _, wrong, _, mistakes = score(keyword_route, HELD_OUT)

    assert wrong == 0, mistakes  # missing a tool is fine (search answers); a wrong tool isn't


@pytest.mark.parametrize(
    ("question", "call"),
    [
        ("in my cv my name is there any cant you find that", None),  # about the name, not CV skills
        ("Is my Python skill verified?", None),  # one skill: search
        ("What am I missing for the Globex job?", ToolCall("job_gaps", "Frontend Developer at Globex")),
    ],
)
def test_keyword_route_examples(question: str, call: ToolCall | None) -> None:
    assert keyword_route(question, JOBS) == call


# --- the model's tool calling (faked HTTP) ------------------------------------------------


def _router(reply: httpx.Response | Exception) -> tuple[OllamaRouter, list[dict]]:
    sent: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(json.loads(request.content))
        if isinstance(reply, Exception):
            raise reply
        return reply

    return OllamaRouter(transport=httpx.MockTransport(handler)), sent


def _calls(*calls: dict) -> httpx.Response:
    return httpx.Response(200, json={"message": {"role": "assistant", "content": "", "tool_calls": list(calls)}})


def test_the_model_sees_every_tool_and_the_jobs() -> None:
    router, sent = _router(_calls({"function": {"name": "job_gaps", "arguments": {"job": "Acme"}}}))

    assert router.route("Am I ready for Acme?", JOBS) == ToolCall("job_gaps", "Acme")
    body = sent[0]
    assert [t["function"]["name"] for t in body["tools"]] == list(TOOLS)
    assert "Backend Engineer at Acme" in body["messages"][0]["content"]
    assert body["stream"] is False and body["options"]["temperature"] == 0


@pytest.mark.parametrize(
    ("reply", "call"),
    [
        (_calls({"function": {"name": "skills_on_cv", "arguments": "{}"}}), ToolCall("skills_on_cv")),
        (_calls({"function": {"name": "job_gaps", "arguments": '{"job": " "}'}}), ToolCall("job_gaps")),
        (_calls(), None),  # no tool chosen: search
        (_calls({"function": {"name": "drop_tables", "arguments": {}}}), None),  # not one of ours
        (httpx.Response(500, json={"error": "boom"}), None),
        (httpx.ConnectError("refused"), None),
    ],
)
def test_the_models_choice_is_read_safely(reply, call) -> None:
    router, _ = _router(reply)

    assert router.route("q", JOBS) == call


def test_only_job_gaps_takes_an_argument() -> None:
    with_args = [t["function"]["name"] for t in tool_schemas() if t["function"]["parameters"]["properties"]]

    assert with_args == ["job_gaps"]


# --- stage 70: guards and the cascade -----------------------------------------------------


@pytest.mark.parametrize(
    ("question", "call", "kept"),
    [
        ("Do I know Kubernetes?", ToolCall("skills_without_proof"), None),  # names a skill: search
        ("How do I prove Docker?", ToolCall("verified_skills"), None),  # instructions: search
        ("What am I missing for my jobs?", ToolCall("job_gaps", "Backend Engineer at Acme"), ToolCall("job_gaps")),
        ("Am I ready for Acme?", ToolCall("job_gaps", "Acme"), ToolCall("job_gaps", "Acme")),  # job really asked about
        ("Give me a learning order", ToolCall("learn_first"), ToolCall("learn_first")),
        ("Anything", None, None),
    ],
)
def test_guard(question: str, call: ToolCall | None, kept: ToolCall | None) -> None:
    assert guard(question, call) == kept


class FakeRouter:
    def __init__(self, answer: ToolCall | None) -> None:
        self.answer = answer
        self.asked: list[str] = []

    def route(self, question: str, job_labels: list[str]) -> ToolCall | None:
        self.asked.append(question)
        return self.answer


def test_the_cascade_asks_the_model_only_when_the_rules_find_nothing() -> None:
    model = FakeRouter(ToolCall("learn_first"))

    assert cascade_route("Which skills have no proof yet?", JOBS, model.route) == ToolCall("skills_without_proof")
    assert model.asked == []
    assert cascade_route("Give me a learning order", JOBS, model.route) == ToolCall("learn_first")
    assert cascade_route("Do I know Kubernetes?", JOBS, model.route) is None  # the guard vetoes the model
    assert model.asked == ["Give me a learning order", "Do I know Kubernetes?"]


def test_the_live_router_sends_one_skill_questions_to_search() -> None:
    assert keyword_route("Why is React not verified?", JOBS) == ToolCall("skills_without_proof")
    assert guarded_keyword_route("Why is React not verified?", JOBS) is None


@pytest.mark.parametrize("questions", [HELD_OUT, TEST], ids=["held-out", "test"])
def test_the_live_router_never_picks_a_wrong_tool(questions) -> None:
    right, wrong, missed, mistakes = score(lambda q, jobs: guarded_keyword_route(q, jobs), questions)

    assert wrong == 0, mistakes


def test_the_live_router_still_gets_every_dev_question() -> None:
    right, _, _, mistakes = score(lambda q, jobs: guarded_keyword_route(q, jobs), DEV)

    assert right == len(DEV), mistakes
