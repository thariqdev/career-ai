"""Tests for the real/placeholder extractor wiring.

CRITICAL: none of these tests make a real network call. They only check which
object get_requirement_extractor() returns, and that ClaudeRequirementExtractor can
be instantiated without a key — never that it can actually extract anything, which
would require a real API call. ANTHROPIC_API_KEY is always explicitly deleted or set
to a fake value via monkeypatch, regardless of what's in the real environment.
"""

from app.ai.providers.claude_extractor import ClaudeRequirementExtractor
from app.ai.providers.stub_extractor import NoOpRequirementExtractor
from app.dependencies import get_requirement_extractor


def test_no_key_returns_the_placeholder_extractor(monkeypatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    extractor = get_requirement_extractor()

    assert isinstance(extractor, NoOpRequirementExtractor)


def test_claude_extractor_can_be_constructed_with_no_api_key_set(monkeypatch) -> None:
    """Proves the Anthropic client is never built at construction time, only lazily
    inside extract_requirements — otherwise this would raise with no key present."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    ClaudeRequirementExtractor()  # must not raise


def test_a_set_key_switches_to_the_claude_extractor(monkeypatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-not-real")

    extractor = get_requirement_extractor()

    assert isinstance(extractor, ClaudeRequirementExtractor)
