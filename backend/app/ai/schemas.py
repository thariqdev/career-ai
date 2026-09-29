"""Structured output schemas for LLM calls.

These describe the SHAPE of what an extractor returns. They enforce types only:
everything an LLM returns is an untrusted proposal, and the business rules that
decide what is accepted live in the backend services (see requirement_service).
"""

from pydantic import BaseModel


class ExtractedRequirement(BaseModel):
    """One requirement proposed for a job description."""

    text: str
    is_required: bool = True
    skill_mention: str | None = None  # a name/alias mention only, never a skill id


class ExtractionResult(BaseModel):
    """The typed proposal an extractor returns for one job description."""

    requirements: list[ExtractedRequirement]
