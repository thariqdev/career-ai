"""Canonical skill resolution and safe taxonomy maintenance (PROJECT_RULES.md section 6).

Design rules:
- Exact match only, by design. Text is normalized (strip, casefold, collapse
  internal whitespace) and compared for equality against skill names and aliases.
  There is no stemming, punctuation handling, or "close enough" logic. Related
  technologies are NOT equivalent ("SQL" is not "PostgreSQL"; "NodeJS" is not
  "Node.js") unless an alias registers the relationship explicitly.
- Lookups never create anything. resolve_skill only reads; an unknown technology
  stays unknown rather than becoming a skill (anti-hallucination rule).
- The backend, not an LLM, owns the final mapping to a canonical Skill.
- Skill names and aliases share ONE normalized namespace, and its uniqueness is
  enforced here in the service because the schema does not enforce it (skills.name
  is only case-sensitively unique; skill_aliases.alias has no constraint). A DB
  unique index on a normalized column is a possible later hardening step.

Conventions (same as verification_service): plain functions taking a Session, no
HTTP knowledge, flush but never commit, and flush before reading because
SessionLocal uses autoflush=False.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import (
    AmbiguousSkillMatchError,
    EmptySkillTextError,
    SkillNameCollisionError,
)
from app.db.models import Skill, SkillAlias


def normalize_text(text: str) -> str:
    """The only normalization: strip, collapse whitespace runs to one space, casefold.

    Public because requirement_service reuses it, so "the same text" means the same
    thing everywhere.
    """
    return " ".join(text.split()).casefold()


def _matching_skills(db: Session, normalized: str) -> list[Skill]:
    """Return the distinct Skills whose name or alias normalizes to `normalized`.

    Loads names and aliases and compares in Python: SQL cannot collapse internal
    whitespace portably, and this stays correct on both Postgres and SQLite. Fine
    for a taxonomy this size; a stored normalized column is the later scaling step.
    """
    db.flush()  # autoflush=False: make pending skills/aliases visible first

    skills_by_id = {skill.id: skill for skill in db.scalars(select(Skill))}
    matched: dict[int, Skill] = {
        skill.id: skill for skill in skills_by_id.values() if normalize_text(skill.name) == normalized
    }
    for alias in db.scalars(select(SkillAlias)):
        if normalize_text(alias.alias) == normalized:
            matched[alias.skill_id] = skills_by_id[alias.skill_id]
    return list(matched.values())


def resolve_skill(db: Session, text: str) -> Skill | None:
    """Map free text to the one canonical Skill it names, or None. Never creates anything."""
    normalized = normalize_text(text)
    if not normalized:
        return None

    matches = _matching_skills(db, normalized)
    if not matches:
        return None
    if len(matches) > 1:
        raise AmbiguousSkillMatchError(text, [skill.name for skill in matches])
    return matches[0]


def list_skills(db: Session) -> list[Skill]:
    """All canonical skills ordered by name. Read-only."""
    db.flush()
    return list(db.scalars(select(Skill).order_by(Skill.name, Skill.id)))


def get_skill(db: Session, skill_id: int) -> Skill | None:
    """Look up a Skill by primary key, or None. Read-only."""
    db.flush()
    return db.get(Skill, skill_id)


def _require_free_text(db: Session, text: str) -> str:
    """Validate new name/alias text and return it stripped; reject blanks and collisions."""
    display = text.strip()
    normalized = normalize_text(text)
    if not normalized:
        raise EmptySkillTextError()

    existing = _matching_skills(db, normalized)
    if existing:
        raise SkillNameCollisionError(display, existing[0].name)
    return display


def create_skill(db: Session, name: str, category: str | None = None) -> Skill:
    """Add a new canonical Skill. The name must be unused across all names and aliases."""
    skill = Skill(name=_require_free_text(db, name), category=category)
    db.add(skill)
    db.flush()
    return skill


def add_alias(db: Session, skill: Skill, alias: str) -> SkillAlias:
    """Register an alias for a Skill. Rejects any text already used as a name or alias.

    That includes this skill's own name: an alias identical to its own skill's
    name is redundant, so it is treated as a collision too.
    """
    skill_alias = SkillAlias(skill=skill, alias=_require_free_text(db, alias))
    db.add(skill_alias)
    db.flush()
    return skill_alias
