"""The optional free, local AI reader: Ollama, combined with the skill-list matcher.

Used only when OLLAMA_MODEL is set (and no ANTHROPIC_API_KEY, which keeps priority).
Ollama runs a model on the user's own machine: no account, no key, no cost, and the
posting never leaves the computer.

Nothing about the trust boundary changes. requirement_service still treats every
proposal as untrusted: the grounding check (the text must appear in the posting), dedup
and skill mapping through the saved taxonomy all apply unchanged. The model never
creates skills, never picks ids and never sets statuses.

CombinedRequirementExtractor runs the deterministic matcher first and only ADDS what
the model found beyond it. Model proposals are kept only when they name a skill
(skill_mention), and their text becomes that mention, so a requirement row reads
"Kubernetes", not a whole sentence, and can be saved as a skill in one click. If Ollama
is down or replies with anything unusable, the matcher's result is used alone and
`note` says so; extraction never fails because of the AI.
"""

import json

import httpx
from pydantic import ValidationError

from app.ai.client import RequirementExtractor
from app.ai.providers.skill_list_extractor import SkillListExtractor
from app.ai.schemas import ExtractedRequirement, ExtractionResult

DEFAULT_BASE_URL = "http://127.0.0.1:11434"
TIMEOUT_SECONDS = 120.0  # a local model on a laptop CPU can be slow
MAX_RESPONSE_BYTES = 200_000
MAX_PROPOSALS = 100
MAX_MENTION_LENGTH = 60  # a skill name, not a sentence

_PROMPT_TEMPLATE = """\
You are reading a job posting to find the technologies and skills it asks for.

For each distinct technology, tool, language, framework or professional skill named in \
the text below, return one item:
- text: copy the phrase VERBATIM from the text where it is named.
- skill_mention: the skill's name exactly as written in the text (e.g. "Kubernetes", \
"PostgreSQL", "REST APIs"). Never invent a skill the text doesn't name.
- is_required: false if the text marks it as preferred, a plus or nice-to-have; \
otherwise true.

Leave out soft requirements that name no skill (e.g. "5+ years of experience").
If the text names no skills, return an empty list.

Job posting text:
\"\"\"
{raw_text}
\"\"\"
"""


class ExtractorUnavailableError(Exception):
    """Ollama couldn't be reached or gave an unusable answer. Internal: never reaches HTTP."""


class OllamaRequirementExtractor(RequirementExtractor):
    """One local request to Ollama's /api/chat, constrained to the ExtractionResult schema.

    The HTTP client is built per call, never at import or construction time, so loading
    the app needs no running Ollama. `transport` exists only so tests can fake Ollama.
    """

    def __init__(
        self,
        model: str,
        base_url: str = DEFAULT_BASE_URL,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._transport = transport

    def extract_requirements(self, raw_text: str) -> ExtractionResult:
        body = {
            "model": self._model,
            "messages": [{"role": "user", "content": _PROMPT_TEMPLATE.format(raw_text=raw_text)}],
            "format": ExtractionResult.model_json_schema(),
            "stream": False,
            "options": {"temperature": 0},
        }
        try:
            with httpx.Client(transport=self._transport, timeout=TIMEOUT_SECONDS) as client:
                response = client.post(f"{self._base_url}/api/chat", json=body)
            if response.status_code != 200:
                raise ExtractorUnavailableError(f"Ollama answered {response.status_code}.")
            if len(response.content) > MAX_RESPONSE_BYTES:
                raise ExtractorUnavailableError("Ollama's answer was too large.")
            content = response.json()["message"]["content"]
            result = ExtractionResult.model_validate_json(content)
        except httpx.HTTPError as error:
            raise ExtractorUnavailableError(f"Ollama isn't reachable ({type(error).__name__}).") from error
        except (json.JSONDecodeError, KeyError, TypeError, ValidationError) as error:
            raise ExtractorUnavailableError("Ollama's answer wasn't in the expected format.") from error
        return ExtractionResult(requirements=result.requirements[:MAX_PROPOSALS])


class CombinedRequirementExtractor(RequirementExtractor):
    """The skill-list matcher, plus whatever named skills the AI reader found beyond it."""

    def __init__(self, terms_by_skill: dict[str, list[str]], ai: RequirementExtractor) -> None:
        self._matcher = SkillListExtractor(terms_by_skill)
        self._ai = ai
        # Every saved name/alias, casefolded, mapped to its skill: lets an AI mention of an
        # already-found skill ("python" next to the matcher's "Python") be dropped.
        self._skill_by_term = {
            " ".join(term.split()).casefold(): skill
            for skill, terms in terms_by_skill.items()
            for term in terms
        }
        self.note: str | None = None  # set after each run: why the AI reader wasn't used

    def extract_requirements(self, raw_text: str) -> ExtractionResult:
        found = self._matcher.extract_requirements(raw_text).requirements
        self.note = None
        try:
            proposals = self._ai.extract_requirements(raw_text).requirements
        except ExtractorUnavailableError as error:
            self.note = f"AI reader unavailable, used your skill list only. {error}"
            return ExtractionResult(requirements=found)

        found_skills = {self._skill_by_term.get(self._key(r.skill_mention or "")) for r in found}
        seen = {self._key(r.text) for r in found}
        extra: list[ExtractedRequirement] = []
        for proposal in proposals:
            mention = (proposal.skill_mention or "").strip()
            key = self._key(mention)
            if not key or len(mention) > MAX_MENTION_LENGTH or key in seen:
                continue
            known = self._skill_by_term.get(key)
            if known is not None and known in found_skills:
                continue
            seen.add(key)
            # The mention itself is the requirement text; requirement_service still
            # checks it appears in the posting, so an invented name is rejected there.
            extra.append(
                ExtractedRequirement(text=mention, is_required=proposal.is_required, skill_mention=mention)
            )
        return ExtractionResult(requirements=[*found, *extra])

    @staticmethod
    def _key(text: str) -> str:
        return " ".join(text.split()).casefold()
