"""Tests for the Claude extractor's wiring and lazy construction.

CRITICAL: none of these tests make a real network call. They only check which object
get_requirement_extractor() returns and that ClaudeRequirementExtractor can be built
without a key — never that it can actually extract anything. ANTHROPIC_API_KEY is
always deleted or set to a fake value via monkeypatch, whatever the real environment
holds. (The no-key default is covered in test_skill_list_extractor.py.)
"""

from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.ai.providers.claude_extractor import ClaudeRequirementExtractor
from app.dependencies import get_requirement_extractor
from database import Base


@pytest.fixture()
def db() -> Iterator[Session]:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine, autoflush=False) as session:
        yield session
    engine.dispose()


def test_claude_extractor_can_be_constructed_with_no_api_key_set(monkeypatch) -> None:
    """Proves the Anthropic client is never built at construction time, only lazily
    inside extract_requirements — otherwise this would raise with no key present."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    ClaudeRequirementExtractor()  # must not raise


def test_a_set_key_switches_to_the_claude_extractor(monkeypatch, db: Session) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-not-real")

    extractor = get_requirement_extractor(db)

    assert isinstance(extractor, ClaudeRequirementExtractor)
