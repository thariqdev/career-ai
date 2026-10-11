"""Tests for RAG stage 67: grounded generation, citation checks, fallbacks, follow-ups.

No Ollama needed: FakeChat plays the model and records what it was sent, so we can test
the prompt, the guardrails and the streaming. Real answer quality is checked by hand
once Ollama is installed.
"""

import json
from collections.abc import Iterator

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.dependencies import get_db
from app.main import app
from app.rag import assistant
from app.rag.assistant import NOT_FOUND, UNCITED_NOTE, Prepared, Source, answer_events
from app.rag.chunker import Chunk
from app.rag.generate import (
    MAX_HISTORY_CHARS,
    REMINDER,
    SYSTEM_PROMPT,
    GenerationUnavailableError,
    Note,
    OllamaChat,
    Turn,
    build_messages,
    cited_numbers,
    clean_citations,
    fit_notes,
)
from database import Base


class FakeChat:
    """Plays the model: streams fixed tokens (or fails), and records the messages it got."""

    name = "fake"

    def __init__(self, tokens: list[str] | None = None, fail_after: int | None = None) -> None:
        self.tokens = tokens if tokens is not None else ["You're ", "missing ", "Kubernetes ", "[1]", "."]
        self.fail_after = fail_after
        self.calls: list[list[dict[str, str]]] = []

    def stream(self, messages: list[dict[str, str]]) -> Iterator[str]:
        self.calls.append(messages)
        for i, token in enumerate(self.tokens):
            if self.fail_after is not None and i == self.fail_after:
                raise GenerationUnavailableError("Ollama isn't reachable (ConnectError).")
            yield token


def _prepared(n_sources: int = 2) -> Prepared:
    chunks = [
        Chunk("gap:1:Kubernetes", "gap", "Kubernetes gap", "Gap: Kubernetes is missing for the job Backend.", "/a"),
        Chunk("skill:1", "skill", "Python", "Skill: Python. Your status: verified, proven by evidence: Repo.", "/b"),
    ]
    sources = [Source(i + 1, chunks[i], 1.0) for i in range(n_sources)]
    return Prepared("What am I missing?", sources, 10, "bm25", None)


def _run(prepared: Prepared, chat) -> tuple[str, dict, list[dict]]:
    """(final text, done event, all events) the way the chat applies them."""
    events = list(answer_events(prepared, [], chat))
    text = ""
    for event in events:
        if event["type"] == "delta":
            text += event["text"]
        elif event["type"] == "replace":
            text = event["text"]
    return text, events[-1], events


# --- the prompt ---------------------------------------------------------------------------------


def test_the_prompt_has_the_rules_the_notes_and_the_question_only() -> None:
    notes = [Note(1, "gap", "Kubernetes gap", "Gap: Kubernetes is missing.")]
    history = [Turn("user", "earlier question"), Turn("assistant", "earlier answer")]

    messages = build_messages("What am I missing?", notes, history)

    assert messages[0] == {"role": "system", "content": SYSTEM_PROMPT}
    for rule in ("ONLY the numbered notes", "[1]", "I couldn't find that in your data", "Never call a skill verified"):
        assert rule in SYSTEM_PROMPT
    assert [m["role"] for m in messages] == ["system", "user", "assistant", "user"]
    assert messages[-1]["content"] == (
        "Notes from my Career AI data:\n[1] (gap) Kubernetes gap: Gap: Kubernetes is missing.\n\n"
        "Question: What am I missing?\n\n" + REMINDER
    )


def test_history_is_capped_to_the_last_two_turns_and_trimmed() -> None:
    history = [Turn("user" if i % 2 == 0 else "assistant", f"turn {i} " + "x" * 2000) for i in range(10)]

    messages = build_messages("q", [Note(1, "skill", "Python", "t")], history)

    middle = messages[1:-1]
    assert len(middle) == 4 and middle[0]["content"].startswith("turn 6")
    assert all(len(m["content"]) <= MAX_HISTORY_CHARS for m in middle)


def test_notes_are_cut_to_the_budget_best_first_but_never_empty() -> None:
    notes = [Note(i, "skill", f"S{i}", "x" * 1000) for i in range(1, 10)]

    assert [n.number for n in fit_notes(notes, budget=2500)] == [1, 2]
    assert [n.number for n in fit_notes(notes, budget=10)] == [1]  # the best one always fits


def test_citation_checks() -> None:
    assert clean_citations("Learn it [1], see [7] and [0]. [2]", 2) == "Learn it [1], see  and . [2]"
    assert cited_numbers("A [1] B [2][2] C [9]", 2) == {1, 2}
    assert cited_numbers("No citations here.", 3) == set()


# --- the guardrails ----------------------------------------------------------------------------


def test_a_good_answer_streams_and_is_marked_ai() -> None:
    chat = FakeChat()

    text, done, events = _run(_prepared(), chat)

    assert text == "You're missing Kubernetes [1]."
    assert done == {"type": "done", "written_by": "ai", "note": None}
    assert events[0]["type"] == "meta"
    assert not any(e["type"] == "replace" for e in events)
    assert "Kubernetes gap" in chat.calls[0][-1]["content"]


def test_citations_to_notes_that_dont_exist_are_removed() -> None:
    text, done, _ = _run(_prepared(), FakeChat(["Learn Kubernetes [1] and practise daily [9]."]))

    assert text == "Learn Kubernetes [1] and practise daily ."
    assert done["written_by"] == "ai"


def test_an_answer_citing_nothing_falls_back_to_the_notes() -> None:
    text, done, _ = _run(_prepared(), FakeChat(["You are great at everything."]))

    assert text.startswith("Here's what I found in your data:")
    assert "[1] Gap: Kubernetes is missing" in text
    assert done == {"type": "done", "written_by": "notes", "note": UNCITED_NOTE}


def test_an_unavailable_model_falls_back_to_the_notes_with_a_reason() -> None:
    text, done, _ = _run(_prepared(), FakeChat(fail_after=2))

    assert text.startswith("Here's what I found in your data:")
    assert done["written_by"] == "notes"
    assert done["note"].startswith("The AI writer is unavailable")


def test_no_matching_notes_never_calls_the_model() -> None:
    chat = FakeChat()

    text, done, _ = _run(_prepared(n_sources=0), chat)

    assert text == NOT_FOUND
    assert chat.calls == []
    assert done["written_by"] == "notes"


# --- the Ollama chat client (faked HTTP) -------------------------------------------------------


def _ollama(handler) -> OllamaChat:
    return OllamaChat(transport=httpx.MockTransport(handler))


def test_ollama_chat_streams_tokens_from_ndjson() -> None:
    sent = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(json.loads(request.content))
        lines = [
            {"message": {"role": "assistant", "content": "Learn "}, "done": False},
            {"message": {"role": "assistant", "content": "Kubernetes [1]."}, "done": False},
            {"message": {"role": "assistant", "content": ""}, "done": True},
        ]
        return httpx.Response(200, content="\n".join(json.dumps(line) for line in lines).encode())

    tokens = list(_ollama(handler).stream([{"role": "user", "content": "hi"}]))

    assert tokens == ["Learn ", "Kubernetes [1]."]
    assert sent[0]["model"] == "llama3.2" and sent[0]["stream"] is True
    assert sent[0]["options"]["temperature"] == 0.2


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(404, json={"error": "model not found"}),
        httpx.Response(200, content=b'{"error": "out of memory"}\n'),
        httpx.Response(200, content=b"not json\n"),
    ],
)
def test_bad_ollama_chat_answers_are_unavailable(response: httpx.Response) -> None:
    with pytest.raises(GenerationUnavailableError):
        list(_ollama(lambda request: response).stream([]))


def test_unreachable_ollama_chat_is_unavailable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    with pytest.raises(GenerationUnavailableError, match="isn't reachable"):
        list(_ollama(handler).stream([]))


# --- through the API ---------------------------------------------------------------------------


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
def with_job(client: TestClient) -> None:
    client.post("/cv/add-all", data={"text": "Python and Docker."})
    job_id = client.post(
        "/job-descriptions", json={"raw_text": "Need Python, Kubernetes and AWS.", "title": "Backend", "company": "Acme"}
    ).json()["id"]
    client.post(f"/job-descriptions/{job_id}/extract")


def test_the_api_returns_an_ai_answer_when_a_model_is_configured(
    client: TestClient, with_job: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    chat = FakeChat()
    monkeypatch.setattr(assistant, "configured_chat", lambda: chat)

    body = client.post("/assistant/ask", json={"question": "What am I missing for the Acme job?"}).json()

    assert body["written_by"] == "ai"
    assert body["answer"] == "You're missing Kubernetes [1]."
    assert body["sources"]


def test_the_stream_sends_replace_when_the_checks_change_the_answer(
    client: TestClient, with_job: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(assistant, "configured_chat", lambda: FakeChat(["No citations at all."]))

    response = client.post("/assistant/ask/stream", json={"question": "What am I missing for the Acme job?"})

    events = [json.loads(line) for line in response.text.splitlines()]
    kinds = [e["type"] for e in events]
    assert kinds[0] == "meta" and kinds[-2:] == ["replace", "done"]
    assert events[-2]["text"].startswith("Here's what I found in your data:")
    assert events[-1] == {"type": "done", "written_by": "notes", "note": UNCITED_NOTE}


def test_history_reaches_the_model_and_helps_find_follow_ups(
    client: TestClient, with_job: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    chat = FakeChat()
    monkeypatch.setattr(assistant, "configured_chat", lambda: chat)
    history = [
        {"role": "user", "text": "Do I have a Kubernetes gap?"},
        {"role": "assistant", "text": "Yes, Kubernetes is missing for Backend [1]."},
    ]

    body = client.post("/assistant/ask", json={"question": "How do I learn it?", "history": history}).json()

    # "it" alone finds nothing; with the previous question, the Kubernetes gap is found.
    assert any("Kubernetes" in s["title"] for s in body["sources"])
    sent = chat.calls[0]
    assert [m["role"] for m in sent] == ["system", "user", "assistant", "user"]
    assert sent[-1]["content"].endswith("Question: How do I learn it?\n\n" + REMINDER)


def test_too_much_history_is_refused(client: TestClient) -> None:
    history = [{"role": "user", "text": "x"}] * 21

    assert client.post("/assistant/ask", json={"question": "q", "history": history}).status_code == 422
