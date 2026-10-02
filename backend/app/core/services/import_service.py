"""Restoring a "Download my data" file (export_service, format version 1) into an empty app.

Restore is only allowed when the app has no skills and none of the user's data. Merging
into existing data would mean guessing which "Python" or which claim status wins, and
the app never guesses (PROJECT_RULES.md: nothing is inferred).

Safety, in order:
1. Parse: the file must be a Career AI export, format version 1, with every field of the
   right type (strict Pydantic models; unknown fields are refused).
2. Check: every link must point inside the file, and the rules the app always enforces
   must hold (VERIFIED/PARTIAL claims need linked evidence, evidence has at most one
   source, names and nicknames are unique, links are http(s), dates are in order...).
   ALL problems are collected and reported together; nothing is written if any exist.
3. Write: new ids are given out and every link is remapped to them (the file's ids are
   never reused). Values, including timestamps, are restored exactly as exported.

Same conventions as the other services: plain functions taking a Session, no HTTP
knowledge, flush but never commit. The route commits once, so a failure part-way
leaves nothing behind.
"""

import json
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.exceptions import (
    AppNotEmptyError,
    ImportFileError,
    InvalidResourceUrlError,
)
from app.core.services.skill_service import normalize_text
from app.core.web_links import require_web_link
from app.db.models import (
    ComparisonResult,
    ComparisonResultEvidence,
    CVSkillPresence,
    DismissedRequirement,
    Education,
    Evidence,
    JobDescription,
    JobRequirement,
    LearningProgress,
    LearningResource,
    Project,
    Skill,
    SkillAlias,
    User,
    UserSkill,
    UserSkillEvidence,
    WorkExperience,
)
from app.db.models.enums import EvidenceType, LearningMode, LearningStatus, VerificationStatus

MAX_IMPORT_BYTES = 5 * 1024 * 1024
MAX_PROBLEMS_SHOWN = 20


# --- the file format (mirrors export_service, version 1) ---------------------------------


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SkillIn(_Strict):
    id: int
    name: str
    category: str | None
    aliases: list[str]


class ClaimIn(_Strict):
    id: int
    skill_id: int
    status: VerificationStatus
    notes: str | None
    created_at: datetime
    updated_at: datetime
    evidence_ids: list[int]


class EvidenceIn(_Strict):
    id: int
    evidence_type: EvidenceType
    title: str
    description: str | None
    url: str | None
    work_experience_id: int | None
    project_id: int | None
    education_id: int | None
    created_at: datetime


class ProjectIn(_Strict):
    id: int
    name: str
    description: str | None
    role: str | None
    url: str | None
    start_date: date | None
    end_date: date | None
    created_at: datetime


class WorkIn(_Strict):
    id: int
    company: str
    role: str
    start_date: date
    end_date: date | None
    description: str | None
    created_at: datetime


class EducationIn(_Strict):
    id: int
    institution: str
    degree: str | None
    field_of_study: str | None
    start_date: date | None
    end_date: date | None
    description: str | None
    created_at: datetime


class RequirementIn(_Strict):
    id: int
    job_description_id: int
    skill_id: int | None
    requirement_text: str
    is_required: bool
    created_at: datetime


class ResultIn(_Strict):
    id: int
    job_requirement_id: int
    user_skill_id: int | None
    knowledge_status: VerificationStatus
    reasoning: str
    created_at: datetime
    evidence_ids: list[int]


class JobIn(_Strict):
    id: int
    title: str | None
    company: str | None
    source_url: str | None
    raw_text: str
    created_at: datetime
    requirements: list[RequirementIn]
    comparison_results: list[ResultIn]
    removed_skill_ids: list[int]


class CVMarkIn(_Strict):
    id: int
    skill_id: int
    present: bool
    updated_at: datetime


class ProgressIn(_Strict):
    id: int
    skill_id: int
    status: LearningStatus
    updated_at: datetime


class ResourceIn(_Strict):
    id: int
    skill_id: int
    mode: LearningMode
    title: str
    url: str
    created_at: datetime


class ExportFile(_Strict):
    app: Literal["Career AI"]
    format_version: Literal[1]
    exported_at: datetime
    user: dict[str, str | None]
    skills: list[SkillIn]
    claims: list[ClaimIn]
    evidence: list[EvidenceIn]
    projects: list[ProjectIn]
    work_experiences: list[WorkIn]
    educations: list[EducationIn]
    job_descriptions: list[JobIn]
    cv_marks: list[CVMarkIn]
    learning_progress: list[ProgressIn]
    learning_resources: list[ResourceIn]


@dataclass(frozen=True)
class ImportPreview:
    counts: dict[str, int]
    problems: list[str]
    app_empty: bool


# --- parse and check ----------------------------------------------------------------------


def parse(raw: bytes) -> tuple[ExportFile | None, list[str]]:
    """The file as typed data, or None with the reasons it isn't a valid export."""
    if len(raw) > MAX_IMPORT_BYTES:
        return None, [f"The file is too large. The limit is {MAX_IMPORT_BYTES // (1024 * 1024)} MB."]
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None, ["This isn't a JSON file. Choose a file made by \"Download my data\"."]
    if not isinstance(data, dict) or data.get("app") != "Career AI":
        return None, ["This isn't a Career AI export."]
    if data.get("format_version") != 1:
        return None, [f"Unsupported export format version: {data.get('format_version')!r} (expected 1)."]
    try:
        return ExportFile.model_validate(data), []
    except ValidationError as error:
        return None, [
            f"{'.'.join(str(part) for part in issue['loc'])}: {issue['msg']}"
            for issue in error.errors()[:MAX_PROBLEMS_SHOWN]
        ]


def _web_link_ok(url: str) -> bool:
    try:
        require_web_link(url)
        return True
    except InvalidResourceUrlError:
        return False


def check(file: ExportFile) -> list[str]:
    """Every broken link or broken rule in the file, as readable problems."""
    problems: list[str] = []

    def duplicates(section: str, ids: list[int]) -> None:
        for value, count in Counter(ids).items():
            if count > 1:
                problems.append(f"{section}: id {value} appears {count} times.")

    duplicates("skills", [s.id for s in file.skills])
    duplicates("claims", [c.id for c in file.claims])
    duplicates("evidence", [e.id for e in file.evidence])
    duplicates("projects", [p.id for p in file.projects])
    duplicates("work_experiences", [w.id for w in file.work_experiences])
    duplicates("educations", [e.id for e in file.educations])
    duplicates("job_descriptions", [j.id for j in file.job_descriptions])
    duplicates("requirements", [r.id for j in file.job_descriptions for r in j.requirements])
    duplicates("comparison_results", [r.id for j in file.job_descriptions for r in j.comparison_results])

    skill_ids = {s.id for s in file.skills}
    claim_ids = {c.id for c in file.claims}
    evidence_ids = {e.id for e in file.evidence}
    project_ids = {p.id for p in file.projects}
    work_ids = {w.id for w in file.work_experiences}
    education_ids = {e.id for e in file.educations}

    # Skill names and nicknames share one namespace (skill_service).
    seen_text: dict[str, str] = {}
    for skill in file.skills:
        for text in [skill.name, *skill.aliases]:
            key = normalize_text(text)
            if not key:
                problems.append(f'Skill {skill.id}: a name or nickname is blank.')
            elif key in seen_text:
                problems.append(f'"{text}" is used twice as a skill name or nickname.')
            else:
                seen_text[key] = text

    claimed_skills: Counter[int] = Counter()
    for claim in file.claims:
        if claim.skill_id not in skill_ids:
            problems.append(f"Claim {claim.id} points at missing skill {claim.skill_id}.")
        claimed_skills[claim.skill_id] += 1
        for evidence_id in claim.evidence_ids:
            if evidence_id not in evidence_ids:
                problems.append(f"Claim {claim.id} links missing evidence {evidence_id}.")
        if claim.status in (VerificationStatus.VERIFIED, VerificationStatus.PARTIAL) and not claim.evidence_ids:
            problems.append(f"Claim {claim.id} is {claim.status.value} but has no linked evidence.")
    for skill_id, count in claimed_skills.items():
        if count > 1:
            problems.append(f"Skill {skill_id} is claimed {count} times.")

    for item in file.evidence:
        if not item.title.strip():
            problems.append(f"Evidence {item.id} has a blank title.")
        if item.url is not None and not _web_link_ok(item.url):
            problems.append(f"Evidence {item.id} has a link that isn't http(s).")
        sources = [item.project_id, item.work_experience_id, item.education_id]
        if sum(source is not None for source in sources) > 1:
            problems.append(f"Evidence {item.id} has more than one source.")
        if item.project_id is not None and item.project_id not in project_ids:
            problems.append(f"Evidence {item.id} points at missing project {item.project_id}.")
        if item.work_experience_id is not None and item.work_experience_id not in work_ids:
            problems.append(f"Evidence {item.id} points at missing work experience {item.work_experience_id}.")
        if item.education_id is not None and item.education_id not in education_ids:
            problems.append(f"Evidence {item.id} points at missing education {item.education_id}.")

    def dates_in_order(label: str, start: date | None, end: date | None) -> None:
        if start is not None and end is not None and end < start:
            problems.append(f"{label}: the end date is before the start date.")

    for project in file.projects:
        if not project.name.strip():
            problems.append(f"Project {project.id} has a blank name.")
        if project.url is not None and not _web_link_ok(project.url):
            problems.append(f"Project {project.id} has a link that isn't http(s).")
        dates_in_order(f"Project {project.id}", project.start_date, project.end_date)
    for work in file.work_experiences:
        if not work.company.strip() or not work.role.strip():
            problems.append(f"Work experience {work.id} has a blank company or role.")
        dates_in_order(f"Work experience {work.id}", work.start_date, work.end_date)
    for education in file.educations:
        if not education.institution.strip():
            problems.append(f"Education {education.id} has a blank school.")
        dates_in_order(f"Education {education.id}", education.start_date, education.end_date)

    for job in file.job_descriptions:
        requirement_ids = {r.id for r in job.requirements}
        for requirement in job.requirements:
            if requirement.job_description_id != job.id:
                problems.append(f"Requirement {requirement.id} doesn't belong to job {job.id}.")
            if requirement.skill_id is not None and requirement.skill_id not in skill_ids:
                problems.append(f"Requirement {requirement.id} points at missing skill {requirement.skill_id}.")
        for result in job.comparison_results:
            if result.job_requirement_id not in requirement_ids:
                problems.append(f"Result {result.id} points at a requirement outside job {job.id}.")
            if result.user_skill_id is not None and result.user_skill_id not in claim_ids:
                problems.append(f"Result {result.id} points at missing claim {result.user_skill_id}.")
            for evidence_id in result.evidence_ids:
                if evidence_id not in evidence_ids:
                    problems.append(f"Result {result.id} cites missing evidence {evidence_id}.")
        for skill_id in job.removed_skill_ids:
            if skill_id not in skill_ids:
                problems.append(f"Job {job.id} has a removed skill {skill_id} that is missing.")
        if len(set(job.removed_skill_ids)) != len(job.removed_skill_ids):
            problems.append(f"Job {job.id} lists a removed skill twice.")

    def one_per_skill(section: str, skill_list: list[int]) -> None:
        for skill_id in skill_list:
            if skill_id not in skill_ids:
                problems.append(f"{section}: points at missing skill {skill_id}.")
        for skill_id, count in Counter(skill_list).items():
            if count > 1:
                problems.append(f"{section}: skill {skill_id} appears {count} times.")

    one_per_skill("cv_marks", [m.skill_id for m in file.cv_marks])
    one_per_skill("learning_progress", [p.skill_id for p in file.learning_progress])

    seen_resources: set[tuple[int, str, str]] = set()
    for resource in file.learning_resources:
        if resource.skill_id not in skill_ids:
            problems.append(f"Saved link {resource.id} points at missing skill {resource.skill_id}.")
        if not resource.title.strip():
            problems.append(f"Saved link {resource.id} has a blank title.")
        if not _web_link_ok(resource.url):
            problems.append(f"Saved link {resource.id} isn't an http(s) link.")
        key = (resource.skill_id, resource.mode.value, resource.url.strip())
        if key in seen_resources:
            problems.append(f"Saved link {resource.id} is a duplicate.")
        seen_resources.add(key)

    return problems


def counts(file: ExportFile) -> dict[str, int]:
    return {
        "skills": len(file.skills),
        "nicknames": sum(len(s.aliases) for s in file.skills),
        "claims": len(file.claims),
        "evidence": len(file.evidence),
        "projects": len(file.projects),
        "work_experiences": len(file.work_experiences),
        "educations": len(file.educations),
        "job_descriptions": len(file.job_descriptions),
        "requirements": sum(len(j.requirements) for j in file.job_descriptions),
        "comparison_results": sum(len(j.comparison_results) for j in file.job_descriptions),
        "cv_marks": len(file.cv_marks),
        "learning_progress": len(file.learning_progress),
        "learning_resources": len(file.learning_resources),
    }


def app_is_empty(db: Session, user: User) -> bool:
    """No skills at all, and none of this user's own records."""
    db.flush()
    if db.scalar(select(func.count()).select_from(Skill)):
        return False
    for model in (UserSkill, Evidence, Project, WorkExperience, Education, JobDescription, CVSkillPresence, LearningProgress):
        if db.scalar(select(func.count()).select_from(model).where(model.user_id == user.id)):
            return False
    return True


def preview(db: Session, user: User, raw: bytes) -> ImportPreview:
    """What a restore would bring in, and every problem found. Writes nothing."""
    file, problems = parse(raw)
    if file is not None:
        problems = check(file)
    return ImportPreview(
        counts=counts(file) if file is not None else {},
        problems=problems[:MAX_PROBLEMS_SHOWN],
        app_empty=app_is_empty(db, user),
    )


# --- write --------------------------------------------------------------------------------


def restore(db: Session, user: User, raw: bytes) -> dict[str, int]:
    """Check everything, then restore the whole file. Raises before writing anything."""
    file, problems = parse(raw)
    if file is not None:
        problems = check(file)
    if file is None or problems:
        raise ImportFileError(problems[:MAX_PROBLEMS_SHOWN])
    if not app_is_empty(db, user):
        raise AppNotEmptyError()

    def flushed(obj):  # add, flush to get the new id, return the row
        db.add(obj)
        db.flush()
        return obj

    skill = {
        s.id: flushed(Skill(name=s.name.strip(), category=s.category)) for s in file.skills
    }
    for s in file.skills:
        for alias in s.aliases:
            db.add(SkillAlias(skill_id=skill[s.id].id, alias=alias.strip()))

    project = {
        p.id: flushed(
            Project(
                user=user, name=p.name, description=p.description, role=p.role, url=p.url,
                start_date=p.start_date, end_date=p.end_date, created_at=p.created_at,
            )
        )
        for p in file.projects
    }
    work = {
        w.id: flushed(
            WorkExperience(
                user=user, company=w.company, role=w.role, start_date=w.start_date,
                end_date=w.end_date, description=w.description, created_at=w.created_at,
            )
        )
        for w in file.work_experiences
    }
    education = {
        e.id: flushed(
            Education(
                user=user, institution=e.institution, degree=e.degree, field_of_study=e.field_of_study,
                start_date=e.start_date, end_date=e.end_date, description=e.description,
                created_at=e.created_at,
            )
        )
        for e in file.educations
    }

    def new_id(mapping: dict, old: int | None) -> int | None:
        return None if old is None else mapping[old].id

    evidence = {
        e.id: flushed(
            Evidence(
                user=user, evidence_type=e.evidence_type, title=e.title, description=e.description,
                url=e.url, project_id=new_id(project, e.project_id),
                work_experience_id=new_id(work, e.work_experience_id),
                education_id=new_id(education, e.education_id), created_at=e.created_at,
            )
        )
        for e in file.evidence
    }
    claim = {
        c.id: flushed(
            UserSkill(
                user=user, skill_id=skill[c.skill_id].id, status=c.status, notes=c.notes,
                created_at=c.created_at, updated_at=c.updated_at,
            )
        )
        for c in file.claims
    }
    for c in file.claims:
        for evidence_id in c.evidence_ids:
            db.add(UserSkillEvidence(user_skill_id=claim[c.id].id, evidence_id=evidence[evidence_id].id))

    for j in file.job_descriptions:
        job = flushed(
            JobDescription(
                user=user, title=j.title, company=j.company, source_url=j.source_url,
                raw_text=j.raw_text, created_at=j.created_at,
            )
        )
        requirement = {
            r.id: flushed(
                JobRequirement(
                    job_description_id=job.id, skill_id=new_id(skill, r.skill_id),
                    requirement_text=r.requirement_text, is_required=r.is_required,
                    created_at=r.created_at,
                )
            )
            for r in j.requirements
        }
        for r in j.comparison_results:
            result = flushed(
                ComparisonResult(
                    job_requirement_id=requirement[r.job_requirement_id].id,
                    user_skill_id=new_id(claim, r.user_skill_id),
                    knowledge_status=r.knowledge_status, reasoning=r.reasoning,
                    created_at=r.created_at,
                )
            )
            for evidence_id in r.evidence_ids:
                db.add(ComparisonResultEvidence(comparison_result_id=result.id, evidence_id=evidence[evidence_id].id))
        for skill_id in j.removed_skill_ids:
            db.add(DismissedRequirement(job_description_id=job.id, skill_id=skill[skill_id].id))

    for m in file.cv_marks:
        db.add(CVSkillPresence(user=user, skill_id=skill[m.skill_id].id, present=m.present, updated_at=m.updated_at))
    for p in file.learning_progress:
        db.add(LearningProgress(user=user, skill_id=skill[p.skill_id].id, status=p.status, updated_at=p.updated_at))
    for r in file.learning_resources:
        db.add(
            LearningResource(
                skill_id=skill[r.skill_id].id, mode=r.mode, title=r.title, url=r.url.strip(),
                created_at=r.created_at,
            )
        )
    db.flush()
    return counts(file)
