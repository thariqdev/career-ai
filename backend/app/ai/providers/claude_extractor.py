"""The real, Claude-backed requirement extractor.

This is the real implementation behind the interface (RequirementExtractor) the
codebase has had ready for months, with only a placeholder (stub_extractor.py)
behind it until now. Nothing about the trust boundary changes: requirement_service
still treats whatever this returns as an untrusted PROPOSAL — the same grounding
check, dedup, and skill mapping apply unchanged, regardless of which extractor
produced it. This class's only job is turning raw text into a typed guess.
"""

import anthropic

from app.ai.client import RequirementExtractor
from app.ai.schemas import ExtractionResult

# The cheapest current model, chosen deliberately for this task. Change this one
# line if a different model is ever needed.
MODEL = "claude-haiku-4-5"

_PROMPT_TEMPLATE = """\
You are reading a job posting to find its requirements and qualifications.

For each distinct requirement or qualification in the text below:
- Copy the relevant phrase VERBATIM from the text. Do not paraphrase, summarize, \
or reword it — copy the exact words as they appear.
- Mark it as required or preferred (is_required).
- If a specific technology or skill is named, include it as skill_mention (e.g. \
"Python", "PostgreSQL"). Otherwise leave skill_mention null.

If the text has no clear requirements, return an empty list.

Job posting text:
\"\"\"
{raw_text}
\"\"\"
"""


class ClaudeRequirementExtractor(RequirementExtractor):
    """Calls the real Anthropic API. Constructs its client lazily, never at import time.

    Every test file that uses TestClient(app) imports this module transitively via
    app/dependencies.py, so building the client eagerly (e.g. as a class attribute or
    in __init__) would make the whole test suite require a real API key just to load,
    even though tests never call extract_requirements on this class. Building the
    client only when extract_requirements actually runs is what keeps the test suite
    genuinely free of any real API dependency.
    """

    def extract_requirements(self, raw_text: str) -> ExtractionResult:
        client = anthropic.Anthropic()
        response = client.messages.parse(
            model=MODEL,
            max_tokens=4096,
            messages=[{"role": "user", "content": _PROMPT_TEMPLATE.format(raw_text=raw_text)}],
            output_format=ExtractionResult,
        )
        return response.parsed_output
