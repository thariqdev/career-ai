"""Validates an extractor's proposals and stores them as JobRequirement rows.

The boundary (PROJECT_RULES.md sections 2, 6, 9): the LLM proposes, the backend disposes.
Whatever an extractor returns is an untrusted PROPOSAL; deterministic code here decides
what is accepted. The extractor never creates skills, never picks a skill id and never
sets a status.

Rules applied to each proposal, in order:
- blank text -> rejected
- grounding check: the text must actually appear in the job description's raw_text,
  compared with the shared normalization (strip, casefold, collapse whitespace). This
  is strict on purpose: a paraphrase is rejected. That costs some recall but can never
  admit a fabricated requirement; loosening it is a later decision to make with evidence.
  (It is a substring check, so a very short proposal can match inside a longer word.)
- duplicate text (after normalization) within one proposal -> rejected; first wins
- otherwise accepted. The skill is mapped ONLY through skill_service.resolve_skill; no
  match, a blank mention or an ambiguous mention leaves skill_id None (never guessed,
  and a taxonomy problem never fails the whole extraction).

Rejected proposals are RETURNED with a reason so the caller can see what the model
proposed and why it was dropped; nothing is persisted for them.

Re-running extract_requirements on a job description that already has requirements is
refused, before the extractor is called, so requirements are never silently duplicated.
extract_new_requirements is the explicit "look again" path instead: same rules, plus a
proposal is rejected as REJECTED_EXISTING if its text, or the skill it maps to, is
already among this job's requirements. It only ever ADDS rows; existing requirements
and their comparison results are never changed or deleted.

Both entry points also skip any skill the user removed from this job earlier (a
DismissedRequirement note), rejecting it as REJECTED_DISMISSED, so a correction sticks.

Callers pass any object implementing RequirementExtractor. Same conventions as the other services: plain functions taking a Session, no HTTP
knowledge, flush but never commit, and flush before reading (autoflush=False).
"""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.client import RequirementExtractor
from app.ai.schemas import ExtractedRequirement
from app.core.exceptions import AmbiguousSkillMatchError, RequirementsAlreadyExistError
from app.core.services import skill_service
from app.db.models import DismissedRequirement, JobDescription, JobRequirement, Skill

REJECTED_BLANK = "blank requirement text"
REJECTED_NOT_GROUNDED = "not found in job description text"
REJECTED_DUPLICATE = "duplicate requirement text"
REJECTED_EXISTING = "already a requirement"
REJECTED_DISMISSED = "removed by you for this job"


@dataclass(frozen=True)
class RejectedRequirement:
    """A proposal that was dropped, and why."""

    proposal: ExtractedRequirement
    reason: str


@dataclass(frozen=True)
class ExtractionOutcome:
    """What extraction did: the stored requirements and the dropped proposals."""

    accepted: list[JobRequirement]
    rejected: list[RejectedRequirement]


def _map_skill(db: Session, mention: str | None) -> Skill | None:
    """Map a skill mention through the taxonomy only; never create, never guess."""
    if mention is None or not mention.strip():
        return None
    try:
        return skill_service.resolve_skill(db, mention)
    except AmbiguousSkillMatchError:
        return None


def _dismissed_skill_ids(db: Session, job_description: JobDescription) -> set[int]:
    return set(
        db.scalars(
            select(DismissedRequirement.skill_id).where(
                DismissedRequirement.job_description_id == job_description.id
            )
        )
    )


def extract_requirements(
    db: Session, job_description: JobDescription, extractor: RequirementExtractor
) -> ExtractionOutcome:
    """Run the extractor, validate its proposals, and store the accepted ones."""
    db.flush()  # autoflush=False: make pending state visible before reading

    already_has_requirements = db.scalar(
        select(JobRequirement.id)
        .where(JobRequirement.job_description_id == job_description.id)
        .limit(1)
    )
    if already_has_requirements is not None:
        raise RequirementsAlreadyExistError(job_description.id)  # extractor is NOT called

    proposal = extractor.extract_requirements(job_description.raw_text)
    dismissed = _dismissed_skill_ids(db, job_description)
    return _validate_and_store(db, job_description, proposal.requirements, set(), set(), dismissed)


def extract_new_requirements(
    db: Session, job_description: JobDescription, extractor: RequirementExtractor
) -> ExtractionOutcome:
    """Look again: store only proposals that aren't already requirements of this job.

    "Already" means the same normalized text, or mapping to a skill some existing
    requirement already maps to (so "Postgres" isn't added next to "PostgreSQL").
    Works on a job with no requirements too. Never touches existing rows.
    """
    db.flush()
    existing = list(
        db.scalars(
            select(JobRequirement).where(JobRequirement.job_description_id == job_description.id)
        )
    )
    existing_texts = {skill_service.normalize_text(r.requirement_text) for r in existing}
    existing_skill_ids = {r.skill_id for r in existing if r.skill_id is not None}

    proposal = extractor.extract_requirements(job_description.raw_text)
    return _validate_and_store(
        db,
        job_description,
        proposal.requirements,
        existing_texts,
        existing_skill_ids,
        _dismissed_skill_ids(db, job_description),
    )


def _validate_and_store(
    db: Session,
    job_description: JobDescription,
    proposals: list[ExtractedRequirement],
    existing_texts: set[str],
    existing_skill_ids: set[int],
    dismissed_skill_ids: set[int],
) -> ExtractionOutcome:
    """The rules both entry points share. With empty existing_* sets (first-time
    extraction) the REJECTED_EXISTING checks can never fire, so that path is unchanged."""
    normalized_job_text = skill_service.normalize_text(job_description.raw_text)
    seen: set[str] = set()
    accepted: list[JobRequirement] = []
    rejected: list[RejectedRequirement] = []

    for item in proposals:
        normalized = skill_service.normalize_text(item.text)
        if not normalized:
            rejected.append(RejectedRequirement(item, REJECTED_BLANK))
        elif normalized not in normalized_job_text:
            rejected.append(RejectedRequirement(item, REJECTED_NOT_GROUNDED))
        elif normalized in seen:
            rejected.append(RejectedRequirement(item, REJECTED_DUPLICATE))
        elif normalized in existing_texts:
            rejected.append(RejectedRequirement(item, REJECTED_EXISTING))
        else:
            skill = _map_skill(db, item.skill_mention)
            if skill is not None and skill.id in existing_skill_ids:
                rejected.append(RejectedRequirement(item, REJECTED_EXISTING))
                continue
            if skill is not None and skill.id in dismissed_skill_ids:
                rejected.append(RejectedRequirement(item, REJECTED_DISMISSED))
                continue
            seen.add(normalized)
            requirement = JobRequirement(
                job_description=job_description,
                skill=skill,
                requirement_text=item.text.strip(),
                is_required=item.is_required,
            )
            db.add(requirement)
            db.flush()
            accepted.append(requirement)

    return ExtractionOutcome(accepted=accepted, rejected=rejected)
