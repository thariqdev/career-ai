"""Deterministic requirement extractor: finds known skills in the text. No AI involved.

Given every skill's name and aliases, it proposes one requirement per skill that
appears in the job text, using the exact words found there. Because each proposal is
copied from the text, it always passes requirement_service's grounding check, and
skill_mention is that same matched text, so the existing resolve_skill mapping links
it to the right skill. It can only ever find skills already in the taxonomy.

Matching rules:
- Whole terms only. Letters, digits, underscore, "+" and "#" all count as part of a
  term, so "Java" is not found inside "JavaScript" and "C" is not found inside "C++".
- Case-insensitive, except terms of SHORT_TERM_MAX_LENGTH characters or fewer ("Go",
  "R", "C#"), which must match exactly so everyday words like "go" aren't counted.
- Whitespace inside a multi-word term matches any run of whitespace in the text.
- One proposal per skill (its earliest match, from any of its terms), in text order.
- Every proposal is marked required: this matcher cannot tell required from preferred.
"""

import re

from app.ai.client import RequirementExtractor
from app.ai.schemas import ExtractedRequirement, ExtractionResult

SHORT_TERM_MAX_LENGTH = 2

_TERM_CHAR = r"[\w+#]"


def _compile(term: str) -> re.Pattern[str] | None:
    words = term.split()
    if not words:
        return None
    body = r"\s+".join(re.escape(word) for word in words)
    flags = 0 if len("".join(words)) <= SHORT_TERM_MAX_LENGTH else re.IGNORECASE
    return re.compile(rf"(?<!{_TERM_CHAR}){body}(?!{_TERM_CHAR})", flags)


class SkillListExtractor(RequirementExtractor):
    """Proposes a requirement for each known skill found in the text."""

    def __init__(self, terms_by_skill: dict[str, list[str]]) -> None:
        self._patterns_by_skill = [
            [pattern for pattern in map(_compile, terms) if pattern is not None]
            for terms in terms_by_skill.values()
        ]

    def extract_requirements(self, raw_text: str) -> ExtractionResult:
        found: list[tuple[int, str]] = []
        for patterns in self._patterns_by_skill:
            matches = [match for pattern in patterns if (match := pattern.search(raw_text))]
            if matches:
                first = min(matches, key=lambda match: match.start())
                found.append((first.start(), first.group(0)))

        found.sort()
        return ExtractionResult(
            requirements=[
                ExtractedRequirement(text=text, is_required=True, skill_mention=text)
                for _, text in found
            ]
        )
