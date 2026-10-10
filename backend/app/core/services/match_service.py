"""How well you match one job, right now: proven, on your CV, or missing.

Read-only and deterministic, and always current: it reads the posting text itself plus
your current claims, evidence status and CV marks, so it never needs "Compare again".

Which skills the job asks for (each counted once, in the order the posting names them):
- skills of yours the posting mentions (by name or nickname), even ones saved after the
  job was read;
- the job's saved requirements (e.g. ones the AI reader found);
- common skills from the starter catalogue the posting mentions that you haven't saved
  (suggestion_service): these are always missing, with skill_id None.
Skills you removed from this job ("not for this job" notes) are left out.

For each: proven = a VERIFIED claim; on_cv = claimed (not verified) or marked on your CV;
missing = neither. The percentage is (proven + on_cv) / all, i.e. "how much of this job
is on my CV"; the proven count shows how much of that is backed by evidence.

has_cv is False while the user has no skill marked on their CV and no claim at all: then
every skill is "missing" only because there's nothing to compare with yet, and the page
asks for the CV first instead of showing a discouraging 0%.
"""

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.providers.skill_list_extractor import SkillListExtractor
from app.core.exceptions import AmbiguousSkillMatchError
from app.core.services import skill_service, suggestion_service
from app.db.models import CVSkillPresence, DismissedRequirement, JobDescription, JobRequirement, User, UserSkill
from app.db.models.enums import VerificationStatus


@dataclass(frozen=True)
class MatchItem:
    skill_id: int | None  # None: not one of your skills (yet)
    name: str
    is_required: bool


@dataclass
class JobMatch:
    proven: list[MatchItem] = field(default_factory=list)
    on_cv: list[MatchItem] = field(default_factory=list)
    missing: list[MatchItem] = field(default_factory=list)
    has_cv: bool = False  # any skill marked on the CV, or any claim

    @property
    def total(self) -> int:
        return len(self.proven) + len(self.on_cv) + len(self.missing)

    @property
    def percent(self) -> int:
        return round(100 * (len(self.proven) + len(self.on_cv)) / self.total) if self.total else 0


def job_match(db: Session, user: User, job: JobDescription) -> JobMatch:
    claims = {
        c.skill_id: c.status
        for c in db.scalars(select(UserSkill).where(UserSkill.user_id == user.id))
    }
    on_cv = set(
        db.scalars(
            select(CVSkillPresence.skill_id).where(
                CVSkillPresence.user_id == user.id, CVSkillPresence.present.is_(True)
            )
        )
    )
    removed = set(
        db.scalars(
            select(DismissedRequirement.skill_id).where(DismissedRequirement.job_description_id == job.id)
        )
    )
    requirements = list(
        db.scalars(
            select(JobRequirement)
            .where(JobRequirement.job_description_id == job.id)
            .order_by(JobRequirement.id)
        )
    )
    required_by_skill = {r.skill_id: r.is_required for r in requirements if r.skill_id is not None}

    # Ordered, de-duplicated list of (skill_id or None, name, is_required).
    asked: list[MatchItem] = []
    seen: set[str] = set()

    def add(skill_id: int | None, name: str, is_required: bool) -> None:
        key = f"id:{skill_id}" if skill_id is not None else f"text:{skill_service.normalize_text(name)}"
        if key in seen or (skill_id is not None and skill_id in removed):
            return
        seen.add(key)
        if skill_id is not None:
            seen.add(f"text:{skill_service.normalize_text(name)}")
        asked.append(MatchItem(skill_id, name, is_required))

    # 1. Your skills the posting mentions (current taxonomy, so later additions count).
    for proposal in SkillListExtractor(skill_service.skill_terms(db)).extract_requirements(job.raw_text).requirements:
        try:
            skill = skill_service.resolve_skill(db, proposal.text)
        except AmbiguousSkillMatchError:
            continue
        if skill is not None:
            add(skill.id, skill.name, required_by_skill.get(skill.id, True))
    # 2. The job's own requirements (mapped ones not mentioned verbatim, and unmapped ones).
    for requirement in requirements:
        if requirement.skill_id is not None:
            add(requirement.skill_id, requirement.skill.name, requirement.is_required)
        else:
            add(None, requirement.requirement_text, requirement.is_required)
    # 3. Common skills the posting names that you haven't saved: missing by definition.
    for suggestion in suggestion_service.suggest(db, job.raw_text):
        add(None, suggestion.name, True)

    match = JobMatch(has_cv=bool(on_cv or claims))
    for item in asked:
        if item.skill_id is not None and claims.get(item.skill_id) == VerificationStatus.VERIFIED:
            match.proven.append(item)
        elif item.skill_id is not None and (item.skill_id in claims or item.skill_id in on_cv):
            match.on_cv.append(item)
        else:
            match.missing.append(item)
    for group in (match.proven, match.on_cv, match.missing):
        group.sort(key=lambda i: not i.is_required)  # stable: posting order within each
    return match
