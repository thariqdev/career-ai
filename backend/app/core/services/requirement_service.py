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

Re-running extraction on a job description that already has requirements is refused,
before the extractor is called, so requirements are never silently duplicated.

There is no real LLM yet: callers pass any object implementing RequirementExtractor.
Same conventions as the other services: plain functions taking a Session, no HTTP
knowledge, flush but never commit, and flush before reading (autoflush=False).
"""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.client import RequirementExtractor
from app.ai.schemas import ExtractedRequirement
from app.core.exceptions import AmbiguousSkillMatchError, RequirementsAlreadyExistError
from app.core.services import skill_service
from app.db.models import JobDescription, JobRequirement, Skill

REJECTED_BLANK = "blank requirement text"
REJECTED_NOT_GROUNDED = "not found in job description text"
REJECTED_DUPLICATE = "duplicate requirement text"


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

    normalized_job_text = skill_service.normalize_text(job_description.raw_text)
    seen: set[str] = set()
    accepted: list[JobRequirement] = []
    rejected: list[RejectedRequirement] = []

    for item in proposal.requirements:
        normalized = skill_service.normalize_text(item.text)
        if not normalized:
            rejected.append(RejectedRequirement(item, REJECTED_BLANK))
        elif normalized not in normalized_job_text:
            rejected.append(RejectedRequirement(item, REJECTED_NOT_GROUNDED))
        elif normalized in seen:
            rejected.append(RejectedRequirement(item, REJECTED_DUPLICATE))
        else:
            seen.add(normalized)
            requirement = JobRequirement(
                job_description=job_description,
                skill=_map_skill(db, item.skill_mention),
                requirement_text=item.text.strip(),
                is_required=item.is_required,
            )
            db.add(requirement)
            db.flush()
            accepted.append(requirement)

    return ExtractionOutcome(accepted=accepted, rejected=rejected)
