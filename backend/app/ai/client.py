"""Provider-agnostic LLM client interfaces.

Interfaces only: there is no provider code, prompt, API key or network access here.
"""

from typing import Protocol

from app.ai.schemas import ExtractionResult


class RequirementExtractor(Protocol):
    """Turns job description text into a typed PROPOSAL of requirements.

    Its sole job is text -> typed proposal. It knows nothing about the database, never
    picks skill ids, never creates skills and never sets statuses. The real LLM-backed
    implementation will plug in later behind this interface; until then tests use a fake.
    """

    def extract_requirements(self, raw_text: str) -> ExtractionResult: ...
