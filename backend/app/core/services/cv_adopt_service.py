""""Add all my CV skills": one click turns everything a CV mentions into your skills.

For every skill the CV mentions, either one already saved or one from the starter
catalogue (suggestion_service), this:
- saves it as a skill when it's new (catalogue name + category, and the CV's own spelling
  as a nickname when it differs, e.g. "JS" for JavaScript);
- marks it "on my CV" (CVSkillPresence);
- claims it as PROVISIONAL when it isn't claimed yet.

What it never does: mark anything VERIFIED or PARTIAL. Being listed on a CV is the user's
own statement, not proof (PROJECT_RULES.md section 4.2: self-reported knowledge stays
provisional); linking real evidence is still the only way to verification. An existing
claim keeps its status untouched. Running it again adds nothing new.

Same conventions as the other services: plain functions taking a Session, flush but
never commit (the route commits once, so it's all or nothing).
"""

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import SkillNameCollisionError
from app.core.services import (
    cv_import_service,
    cv_presence_service,
    cv_profile_service,
    skill_service,
    suggestion_service,
    user_service,
)
from app.db.models import User, UserSkill


@dataclass
class AdoptResult:
    added_skills: list[str] = field(default_factory=list)  # new skills created
    marked_on_cv: list[str] = field(default_factory=list)  # newly marked "on my CV"
    claimed: list[str] = field(default_factory=list)  # newly claimed (provisional)
    already_done: list[str] = field(default_factory=list)  # nothing to change
    name_saved: str | None = None  # your name, read from the CV (only when none was saved)


def add_all_from_cv(db: Session, user: User, text: str) -> AdoptResult:
    result = AdoptResult()
    # 1. New skills from the catalogue (created first, so the scan below finds them too).
    for suggestion in suggestion_service.suggest(db, text):
        skill = skill_service.create_skill(db, suggestion.name, suggestion.category)
        own_words = suggestion.matched_text.strip()
        if skill_service.normalize_text(own_words) != skill_service.normalize_text(skill.name):
            try:
                skill_service.add_alias(db, skill, own_words)
            except SkillNameCollisionError:
                pass  # that spelling belongs to another skill already; the name is enough
        result.added_skills.append(skill.name)

    # 2. Every saved skill the CV mentions (including the ones just created).
    scan = cv_import_service.scan_cv(db, user, text)

    claimed_ids = set(
        db.scalars(select(UserSkill.skill_id).where(UserSkill.user_id == user.id))
    )
    for found in scan.found:
        skill = found.skill
        changed = False
        if not found.on_cv:
            cv_presence_service.set_cv_presence(db, user, skill, True)
            result.marked_on_cv.append(skill.name)
            changed = True
        if skill.id not in claimed_ids:
            db.add(UserSkill(user=user, skill=skill))  # status defaults to PROVISIONAL
            claimed_ids.add(skill.id)
            result.claimed.append(skill.name)
            changed = True
        if not changed:
            result.already_done.append(skill.name)

    # 3. Your name from the top of the CV, unless you've already saved one.
    if not user.full_name:
        name = cv_profile_service.read_name(text)
        if name:
            user_service.set_full_name(db, user, name)
            result.name_saved = user.full_name
    db.flush()
    return result
