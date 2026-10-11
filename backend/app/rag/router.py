"""ROUTING (RAG stage 69): does this question need a tool, and which one?

Two routers, measured against each other in app/rag/router_eval.py:

- keyword_route: hand-written rules ("no proof" -> skills_without_proof, a job's name
  plus "missing" -> job_gaps for that job, ...). Free, instant, predictable, testable;
  but it only understands phrasings someone thought of.
- OllamaRouter: the local model's TOOL CALLING. The model is shown each tool's name and
  description (a JSON schema) and replies with the tool to call and its arguments, or
  with no tool. It understands new phrasings, but it's slower, and it's a model: it can
  pick a tool when none fits.

Either way, None means "no tool: use search", which is always safe.
"""

import json
import re

import httpx

from app.rag.generate import DEFAULT_BASE_URL, DEFAULT_CHAT_MODEL
from app.rag.tools import TOOLS, ToolCall

# --- keyword rules -----------------------------------------------------------------------

_NO_PROOF = re.compile(
    r"\b(?:no|without|lack(?:ing)?|need(?:s)?|missing)\s+(?:any\s+)?(?:proof|evidence)\b"
    r"|\bun(?:verified|proven)\b|\b(?:not|n't|never)\s+(?:yet\s+)?(?:been\s+)?(?:verified|proven|proved)\b"
    r"|\bhaven'?t\s+(?:i\s+)?(?:yet\s+)?(?:proven|proved|verified)\b",
    re.IGNORECASE,
)
_PROVEN = re.compile(r"\b(?:verified|proven|proved)\b", re.IGNORECASE)
_LIST = re.compile(r"\b(?:which|what|list|show|all)\b", re.IGNORECASE)
_SKILLS = re.compile(r"\bskills\b", re.IGNORECASE)
_CV = re.compile(r"\b(?:cv|resume|résumé)\b", re.IGNORECASE)
_LEARN_FIRST = re.compile(
    r"\blearn\s+first\b|\bstudy\s+first\b|\bwhat\s+should\s+i\s+(?:learn|study)\b|\bfocus\s+on\b"
    r"|\bprioriti[sz]e\b|\bmost\s+needed\b|\bwhere\s+should\s+i\s+start\b",
    re.IGNORECASE,
)
_GAPS = re.compile(
    r"\bmissing\b|\bgaps\b|\black\b|\bneed\b|\bdon'?t\s+have\b|\bdo\s+not\s+have\b", re.IGNORECASE
)
_JOBS_WORD = re.compile(r"\b(?:jobs?|roles?|positions?|applications?)\b", re.IGNORECASE)
_STOP = {"the", "and", "for", "job", "role", "senior", "junior"}


def _job_named(question: str, job_labels: list[str]) -> str | None:
    """The job whose distinctive words (title or company) appear in the question."""
    words = set(re.findall(r"[a-z0-9.+#]+", question.lower()))
    for label in job_labels:
        distinctive = [w for w in re.findall(r"[a-z0-9.+#]+", label.lower()) if len(w) >= 3 and w not in _STOP and w != "at"]
        if any(w in words for w in distinctive):
            return label
    return None


def keyword_route(question: str, job_labels: list[str]) -> ToolCall | None:
    """Rules, checked in order (the most specific first). None = no tool, use search."""
    if _NO_PROOF.search(question):
        return ToolCall("skills_without_proof")
    if _PROVEN.search(question) and _LIST.search(question) and (_SKILLS.search(question) or "so far" in question.lower()):
        return ToolCall("verified_skills")
    if _CV.search(question) and (_SKILLS.search(question) or _LIST.search(question)) and "name" not in question.lower():
        return ToolCall("skills_on_cv")
    job = _job_named(question, job_labels)
    if job and (_GAPS.search(question) or re.search(r"\blearn\b", question, re.IGNORECASE)):
        return ToolCall("job_gaps", job)
    if _LEARN_FIRST.search(question):
        return ToolCall("learn_first")
    if _GAPS.search(question) and (_JOBS_WORD.search(question) or re.search(r"\bgaps\b", question, re.IGNORECASE)):
        return ToolCall("job_gaps")
    return None


# --- the model's tool calling ------------------------------------------------------------

ROUTER_SYSTEM = """You route questions for a careers app that knows one person's skills, \
CV, proof and saved jobs. If one of the tools gives exactly what the question asks for, \
call it. If the question is about one particular skill, a project, education, work \
history, the person's name, how to do something, or anything else, do not call a tool: \
reply with the single word NONE."""


def tool_schemas() -> list[dict]:
    """The tools in the JSON-schema format chat models expect."""
    schemas = []
    for name, description in TOOLS.items():
        properties = {}
        if name == "job_gaps":
            properties["job"] = {
                "type": "string",
                "description": "The job's title or company if the question names one job; leave out for all jobs.",
            }
        schemas.append(
            {
                "type": "function",
                "function": {
                    "name": name,
                    "description": description,
                    "parameters": {"type": "object", "properties": properties, "required": []},
                },
            }
        )
    return schemas


class OllamaRouter:
    """Asks a local Ollama model to pick a tool (POST /api/chat with `tools`)."""

    def __init__(
        self,
        model: str = DEFAULT_CHAT_MODEL,
        base_url: str = DEFAULT_BASE_URL,
        transport: httpx.BaseTransport | None = None,  # tests only
    ) -> None:
        self.name = model
        self._base_url = base_url.rstrip("/")
        self._transport = transport

    def route(self, question: str, job_labels: list[str]) -> ToolCall | None:
        """The model's choice; None for no tool, an unknown tool, or any error."""
        system = ROUTER_SYSTEM + "\nThe person's saved jobs: " + ("; ".join(job_labels) or "none") + "."
        body = {
            "model": self.name,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": question}],
            "tools": tool_schemas(),
            "stream": False,
            "options": {"temperature": 0},
        }
        try:
            with httpx.Client(transport=self._transport, timeout=httpx.Timeout(300.0, connect=5.0)) as client:
                response = client.post(f"{self._base_url}/api/chat", json=body)
            if response.status_code != 200:
                return None
            calls = (response.json().get("message") or {}).get("tool_calls") or []
        except (httpx.HTTPError, ValueError):
            return None
        if not calls:
            return None
        function = calls[0].get("function") or {}
        name = function.get("name")
        if name not in TOOLS:
            return None
        arguments = function.get("arguments") or {}
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments)
            except ValueError:
                arguments = {}
        job = arguments.get("job") if name == "job_gaps" else None
        return ToolCall(name, job.strip() if isinstance(job, str) and job.strip() else None)
