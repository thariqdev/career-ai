"""Suggest skills to add: catalogue skills a text mentions that you haven't saved yet.

Read-only, and only ever a suggestion (see app/core/skill_catalog.py). A catalogue
skill is skipped when its name or any of its spellings already belongs to one of your
saved skills (names and nicknames share one namespace in skill_service), so nothing you
already have is suggested again.

Matching follows the skill-list reader's rules (whole terms; letters, digits, "_", "+"
and "#" are part of a term; whitespace inside a term matches any whitespace), and is
case-sensitive for terms of 2 characters or fewer and for EXACT_CASE everyday words.
"""

import re
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.services import skill_service
from app.core.skill_catalog import CATALOG, EXACT_CASE, CatalogSkill

MAX_SUGGESTIONS = 50

_TERM_CHAR = r"[\w+#]"


@dataclass(frozen=True)
class Suggestion:
    name: str  # the catalogue's canonical name, e.g. "JavaScript"
    category: str
    matched_text: str  # the text's own words, e.g. "JS"


def _pattern(term: str) -> re.Pattern[str] | None:
    words = term.split()
    if not words:
        return None
    body = r"\s+".join(re.escape(word) for word in words)
    exact = term in EXACT_CASE or len("".join(words)) <= 2
    return re.compile(rf"(?<!{_TERM_CHAR}){body}(?!{_TERM_CHAR})", 0 if exact else re.IGNORECASE)


# Compiled once: the catalogue is fixed.
_PATTERNS: list[tuple[CatalogSkill, list[re.Pattern[str]]]] = [
    (skill, [p for p in map(_pattern, skill.terms) if p is not None]) for skill in CATALOG
]


def suggest(db: Session, text: str) -> list[Suggestion]:
    """Catalogue skills mentioned in `text` that aren't saved yet, in text order."""
    saved = {
        skill_service.normalize_text(term)
        for terms in skill_service.skill_terms(db).values()
        for term in terms
    }
    found: list[tuple[int, Suggestion]] = []
    for skill, patterns in _PATTERNS:
        if any(skill_service.normalize_text(term) in saved for term in skill.terms):
            continue
        matches = [m for p in patterns if (m := p.search(text))]
        if matches:
            first = min(matches, key=lambda m: m.start())
            found.append((first.start(), Suggestion(skill.name, skill.category, first.group(0))))
    found.sort(key=lambda item: item[0])
    return [suggestion for _, suggestion in found][:MAX_SUGGESTIONS]
