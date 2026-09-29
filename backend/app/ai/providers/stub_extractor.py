"""TEMPORARY placeholder extractor, pending real LLM integration.

`NoOpRequirementExtractor` is what `get_requirement_extractor` (app/dependencies.py)
wires in by default today. It deliberately proposes NOTHING rather than guessing —
consistent with the anti-hallucination rules the whole extraction step exists to
enforce (PROJECT_RULES.md sections 2, 6, 9). This makes the /extract endpoint real
and provable now, without any model behind it.

When a real LLM-backed provider exists, swapping it in requires touching only the
`get_requirement_extractor` dependency — no endpoint or service changes.
"""

from app.ai.client import RequirementExtractor
from app.ai.schemas import ExtractionResult


class NoOpRequirementExtractor(RequirementExtractor):
    """Always proposes zero requirements. A placeholder, not a real extractor."""

    def extract_requirements(self, raw_text: str) -> ExtractionResult:
        return ExtractionResult(requirements=[])
