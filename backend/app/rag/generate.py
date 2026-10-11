"""GENERATE (RAG stage 67): a local language model writes the answer from the retrieved notes.

Calling a model is easy; keeping it HONEST is the real work. Four defences, in order:

1. The system prompt states the rules: use only the numbered notes, cite every fact
   like [1], say so when the notes don't answer, never upgrade a skill's status, be brief.
2. The model sees ONLY the retrieved notes (plus the last couple of chat turns), never
   the whole database, so it can't wander. The notes are cut to a size budget so they
   fit the model's context window (its working memory), best-ranked kept first.
3. After writing, citations are checked: a [7] when there were 4 notes is removed.
4. An answer that cites NOTHING isn't trusted: the reply falls back to the notes
   themselves. (No citation = no evidence the model used them.)

The model runs locally in Ollama (llama3.2 by default): free, and nothing leaves the
computer. Temperature is low (0.2) so answers stick to the notes instead of being creative.
If Ollama is off or the model isn't pulled, GenerationUnavailableError is raised and the
assistant shows the notes instead, with a note saying why.
"""

import json
import re
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Literal, Protocol

import httpx

from app.rag.warmup import keep_alive

DEFAULT_CHAT_MODEL = "llama3.2"
DEFAULT_BASE_URL = "http://127.0.0.1:11434"
# The first question loads the model into memory, which can take minutes on a CPU; after
# that, answers take seconds. A dead Ollama still fails fast (the connect timeout).
TIMEOUT = httpx.Timeout(300.0, connect=5.0)
TEMPERATURE = 0.2
MAX_CONTEXT_CHARS = 6000  # notes budget (~1,500 tokens): small models have small memories
MAX_HISTORY_MESSAGES = 4  # the last 2 question/answer turns
MAX_HISTORY_CHARS = 600  # per earlier message

SYSTEM_PROMPT = """You are Career AI's assistant. You help one person understand their own \
career data: their skills, proof (evidence), job descriptions, gaps and what to learn.

Rules:
1. Use ONLY the numbered notes given with the question. Do not use outside knowledge \
about the person, and never invent skills, jobs, dates or proof.
2. Cite the note behind every fact with its number in square brackets, like [1] or [2][3].
3. If the notes don't answer the question, say "I couldn't find that in your data." and \
stop. Don't guess.
4. Never call a skill verified or proven unless a note says so. "Provisional" or "on your \
CV" means not proven yet.
5. Be brief and practical: a few sentences or a short list. When suggesting what to do, \
say which skill or job it's about."""


class GenerationUnavailableError(Exception):
    """The chat model couldn't be used (Ollama not running, model not pulled...)."""


@dataclass(frozen=True)
class Note:
    number: int
    kind: str
    title: str
    text: str


@dataclass(frozen=True)
class Turn:
    role: Literal["user", "assistant"]
    text: str


class ChatModel(Protocol):
    name: str

    def stream(self, messages: list[dict[str, str]]) -> Iterator[str]: ...


def fit_notes(notes: list[Note], budget: int = MAX_CONTEXT_CHARS) -> list[Note]:
    """Keep notes in rank order until the budget is used (at least the best one)."""
    kept: list[Note] = []
    used = 0
    for note in notes:
        size = len(note.title) + len(note.text) + 20
        if kept and used + size > budget:
            break
        kept.append(note)
        used += size
    return kept


def build_messages(question: str, notes: list[Note], history: list[Turn]) -> list[dict[str, str]]:
    """The exact messages sent to the model: rules, recent turns, then notes + question."""
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    for turn in history[-MAX_HISTORY_MESSAGES:]:
        messages.append({"role": turn.role, "content": turn.text[:MAX_HISTORY_CHARS]})
    numbered = "\n".join(f"[{n.number}] ({n.kind}) {n.title}: {n.text}" for n in notes)
    messages.append(
        {
            "role": "user",
            "content": f"Notes from my Career AI data:\n{numbered}\n\nQuestion: {question}\n\n{REMINDER}",
        }
    )
    return messages


# Repeated right after the question: small models follow the LAST instruction they read
# far better than one at the top. Measured on llama3.2 (2026-10-11): answers citing a note
# went from 9/18 with the rules only in the system prompt to 18/18 with this line.
REMINDER = "Answer using only these notes, and cite the note number for every fact, like [1]."


_CITATION = re.compile(r"\[(\d+)\]")


def clean_citations(text: str, note_count: int) -> str:
    """Remove citations to notes that don't exist ([7] when there were 4), keeping the rest."""
    return _CITATION.sub(lambda m: m.group(0) if 1 <= int(m.group(1)) <= note_count else "", text)


def cited_numbers(text: str, note_count: int) -> set[int]:
    return {int(n) for n in _CITATION.findall(text) if 1 <= int(n) <= note_count}


class OllamaChat:
    """Streams a local Ollama chat model's reply, token by token (POST /api/chat, stream)."""

    def __init__(
        self,
        model: str = DEFAULT_CHAT_MODEL,
        base_url: str = DEFAULT_BASE_URL,
        transport: httpx.BaseTransport | None = None,  # tests only
    ) -> None:
        self.name = model
        self._base_url = base_url.rstrip("/")
        self._transport = transport

    def stream(self, messages: list[dict[str, str]]) -> Iterator[str]:
        body = {
            "model": self.name,
            "messages": messages,
            "stream": True,
            "options": {"temperature": TEMPERATURE},
            "keep_alive": keep_alive(),
        }
        try:
            with httpx.Client(transport=self._transport, timeout=TIMEOUT) as client:
                with client.stream("POST", f"{self._base_url}/api/chat", json=body) as response:
                    if response.status_code != 200:
                        raise GenerationUnavailableError(
                            f"Ollama answered {response.status_code}. Is the model pulled? Run: ollama pull {self.name}"
                        )
                    for line in response.iter_lines():
                        if not line.strip():
                            continue
                        try:
                            data = json.loads(line)
                        except json.JSONDecodeError as error:
                            raise GenerationUnavailableError("Ollama sent something that isn't JSON.") from error
                        if data.get("error"):
                            raise GenerationUnavailableError(f"Ollama: {data['error']}")
                        piece = (data.get("message") or {}).get("content", "")
                        if piece:
                            yield piece
                        if data.get("done"):
                            return
        except httpx.HTTPError as error:
            raise GenerationUnavailableError(f"Ollama isn't reachable ({type(error).__name__}).") from error
