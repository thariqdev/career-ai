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

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.exceptions import (
    AliasNotFoundError,
    AmbiguousSkillMatchError,
    EmptySkillTextError,
    SkillInUseError,
    SkillMergeConflictError,
    SkillMergeIntoItselfError,
    SkillNameCollisionError,
)
from app.db.models import (
    CVSkillPresence,
    JobRequirement,
    LearningProgress,
    LearningResource,
    Skill,
    SkillAlias,
    UserSkill,
)
from app.db.models.enums import LearningStatus


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


def update_skill(db: Session, skill: Skill, changes: dict) -> Skill:
    """Rename and/or re-categorize (PATCH: only keys present in `changes` apply).

    A new name follows the same one-namespace rule as create_skill, except that the
    skill itself isn't a collision: "python" -> "Python" is allowed. Renaming it to one
    of its OWN aliases is still refused (it would duplicate that alias); remove the alias
    first. Claims, evidence, CV marks, links and progress reference the skill by id, so
    they all follow the rename; old JobRequirement text keeps the posting's own words.
    """
    if "name" in changes:
        name = changes["name"] or ""
        display = name.strip()
        normalized = normalize_text(name)
        if not normalized:
            raise EmptySkillTextError()
        others = [s for s in _matching_skills(db, normalized) if s.id != skill.id]
        if others:
            raise SkillNameCollisionError(display, others[0].name)
        if normalized != normalize_text(skill.name) and any(
            normalize_text(a.alias) == normalized for a in skill.aliases
        ):
            raise SkillNameCollisionError(display, skill.name)
        skill.name = display
    if "category" in changes:
        category = changes["category"]
        skill.category = category.strip() if category and category.strip() else None
    db.flush()
    return skill


def squash(text: str) -> str:
    """Casefold and keep only letters, digits, "+" and "#": a looser key than normalize_text.

    Used ONLY to warn about look-alikes ("pytho n", "Py-thon" -> "python"), never to
    match or merge anything. "+" and "#" are kept so C, C++ and C# stay distinct.
    """
    return "".join(ch for ch in text.casefold() if ch.isalnum() or ch in "+#")


def similar_skills(db: Session, name: str) -> list[Skill]:
    """Skills whose name or an alias squashes to the same text as `name`. Read-only."""
    target = squash(name)
    if not target:
        return []
    return [
        skill
        for skill in list_skills(db)
        if squash(skill.name) == target or any(squash(a.alias) == target for a in skill.aliases)
    ]


def list_skills(db: Session) -> list[Skill]:
    """All canonical skills ordered by name. Read-only."""
    db.flush()
    return list(db.scalars(select(Skill).order_by(Skill.name, Skill.id)))


def skill_terms(db: Session) -> dict[str, list[str]]:
    """Each canonical skill name mapped to [its name, *its aliases]. Read-only.

    Plain strings only, so a caller (the skill-list extractor) can use the taxonomy
    without holding ORM objects or a Session.
    """
    return {skill.name: [skill.name, *(a.alias for a in skill.aliases)] for skill in list_skills(db)}


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


def _usage(db: Session, skill: Skill) -> list[str]:
    """Why this skill can't be deleted, as readable reasons; empty means it's unused."""

    def count(model: type, *conditions) -> int:
        return db.scalar(
            select(func.count()).select_from(model).where(model.skill_id == skill.id, *conditions)
        )

    reasons = []
    if count(UserSkill):
        reasons.append("claimed")
    if (n := count(JobRequirement)):
        reasons.append(f"used in {n} job requirement{'s' if n != 1 else ''}")
    if count(CVSkillPresence, CVSkillPresence.present.is_(True)):
        reasons.append("marked as on your CV")
    if (n := count(LearningResource)):
        reasons.append(f"holding {n} saved learning link{'s' if n != 1 else ''}")
    if count(LearningProgress):
        reasons.append("being tracked in learning progress")
    return reasons


def delete_skill(db: Session, skill: Skill) -> None:
    """Delete a skill nothing depends on, with its aliases. Raises SkillInUseError otherwise.

    Refusing (rather than cascading) protects user data and history: a claim, an old job
    comparison or a saved link never silently loses its skill. A CV row saying
    present=False is removed along with the skill, since cv_service already treats it
    exactly like having no row.
    """
    db.flush()
    reasons = _usage(db, skill)
    if reasons:
        raise SkillInUseError(skill.name, reasons)
    # Deleted through the ORM (not bulk SQL) so the session's loaded collections stay
    # consistent when the skill itself is deleted. _usage guarantees any remaining CV
    # rows here have present=False.
    for row in [*skill.cv_skill_presences, *skill.aliases]:
        db.delete(row)
    db.delete(skill)
    db.flush()


def merge_skills(db: Session, source: Skill, target: Skill) -> Skill:
    """Fold `source` (a duplicate) into `target`, then delete `source`. Returns `target`.

    Everything that pointed at the duplicate moves to the target, so nothing is lost:
    job requirements, aliases, claims (with their evidence and comparison history, which
    reference the claim, not the skill) and saved links. The duplicate's name becomes a
    target alias, so later postings using that spelling still resolve.

    Where both skills hold a per-user row, the rule is fixed and invents nothing:
    - learning progress: keep the further-along one (finished beats studying);
    - CV mark: present if either was present (the CV did mention one of the names);
    - saved links: an exact duplicate (same mode and URL) is dropped;
    - claims: refused with SkillMergeConflictError. Choosing which status and proof
      survive is the user's judgment (PROJECT_RULES.md: nothing is inferred).
    Merging covers every user's rows, since skills are a shared taxonomy.
    """
    db.flush()
    if source.id == target.id:
        raise SkillMergeIntoItselfError(source.name)
    target_claimants = {claim.user_id for claim in target.user_skills}
    if any(claim.user_id in target_claimants for claim in source.user_skills):
        raise SkillMergeConflictError(source.name, target.name)

    for row in [*source.user_skills, *source.job_requirements, *source.aliases]:
        row.skill = target

    saved = {(resource.mode, resource.url) for resource in target.learning_resources}
    for resource in list(source.learning_resources):
        if (resource.mode, resource.url) in saved:
            db.delete(resource)
        else:
            resource.skill = target
            saved.add((resource.mode, resource.url))

    progress_by_user = {row.user_id: row for row in target.learning_progress}
    for row in list(source.learning_progress):
        kept = progress_by_user.get(row.user_id)
        if kept is None:
            row.skill = target
            continue
        if row.status == LearningStatus.FINISHED:
            kept.status = LearningStatus.FINISHED
        db.delete(row)

    presence_by_user = {row.user_id: row for row in target.cv_skill_presences}
    for row in list(source.cv_skill_presences):
        kept = presence_by_user.get(row.user_id)
        if kept is None:
            row.skill = target
            continue
        kept.present = kept.present or row.present
        db.delete(row)

    # Move and drop rows first, so deleting the now-empty source touches nothing else.
    db.flush()
    source_name = source.name
    db.expire(source)
    db.delete(source)
    db.flush()
    add_alias(db, target, source_name)  # the name is free now that the source is gone
    db.expire(target)  # reload its collections from the database
    return target


def remove_alias(db: Session, skill: Skill, alias: str) -> None:
    """Remove one of THIS skill's aliases, matched with the shared normalization.

    Only this skill's own aliases are considered, so a name or another skill's alias
    with the same text is never touched. Raises AliasNotFoundError if none matches.
    """
    db.flush()
    normalized = normalize_text(alias)
    match = next(
        (item for item in skill.aliases if normalize_text(item.alias) == normalized), None
    )
    if match is None:
        raise AliasNotFoundError(skill.name, alias)
    db.delete(match)
    db.flush()
    db.expire(skill, ["aliases"])  # so skill.aliases is reloaded without the removed one
