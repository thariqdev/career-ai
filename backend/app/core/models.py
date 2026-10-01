from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from app.db.models.enums import EvidenceType, LearningMode, VerificationStatus


class HealthResponse(BaseModel):
    status: str


# Request/response schemas enforce shape and types only. Business rules (blank text,
# collisions, ambiguity) belong to the domain services, which raise DomainErrors.


class SkillCreate(BaseModel):
    name: str
    category: str | None = None


class AliasCreate(BaseModel):
    alias: str


class SkillResponse(BaseModel):
    """Public shape of a Skill; `aliases` are the alias TEXT values only."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    category: str | None
    aliases: list[str]

    @field_validator("aliases", mode="before")
    @classmethod
    def _alias_text_only(cls, value: Any) -> Any:
        # When built from the ORM, `aliases` is a list of SkillAlias objects.
        return [getattr(item, "alias", item) for item in value]


class UserResponse(BaseModel):
    """Public shape of the (single, hardcoded) User."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    full_name: str | None


class JobDescriptionCreate(BaseModel):
    raw_text: str
    title: str | None = None
    company: str | None = None
    source_url: str | None = None


class JobRequirementResponse(BaseModel):
    """Public shape of a JobRequirement; `skill_name` is pulled from the relationship."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    requirement_text: str
    is_required: bool
    skill_id: int | None
    skill_name: str | None
    created_at: datetime

    @model_validator(mode="before")
    @classmethod
    def _skill_name_from_relationship(cls, data: Any) -> Any:
        # Unlike SkillResponse.aliases, `skill_name` has no ORM attribute counterpart
        # at all (JobRequirement has `.skill`, not `.skill_name`), so a per-field
        # from_attributes lookup would fail before any field_validator could run.
        # This model-level validator intercepts the raw ORM object first instead.
        if isinstance(data, dict):
            return data
        return {
            "id": data.id,
            "requirement_text": data.requirement_text,
            "is_required": data.is_required,
            "skill_id": data.skill_id,
            "skill_name": data.skill.name if data.skill is not None else None,
            "created_at": data.created_at,
        }


class JobDescriptionResponse(BaseModel):
    """Public shape of a JobDescription, with its requirements."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str | None
    company: str | None
    source_url: str | None
    raw_text: str
    created_at: datetime
    requirements: list[JobRequirementResponse]


class RejectedRequirementResponse(BaseModel):
    """A proposal requirement_service dropped, and why."""

    text: str
    reason: str

    @classmethod
    def from_rejection(cls, rejection: Any) -> "RejectedRequirementResponse":
        # requirement_service.RejectedRequirement is a plain dataclass, not an ORM
        # model, so there is no relationship shape to flatten here (unlike the other
        # from_attributes schemas) — just its proposal's text and the reason.
        return cls(text=rejection.proposal.text, reason=rejection.reason)


class ExtractionResponse(BaseModel):
    accepted: list[JobRequirementResponse]
    rejected: list[RejectedRequirementResponse]


class ComparisonResultResponse(BaseModel):
    """Public shape of a ComparisonResult; `evidence_ids` are pulled from the join rows."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    job_requirement_id: int
    knowledge_status: str
    reasoning: str
    evidence_ids: list[int]
    created_at: datetime

    @model_validator(mode="before")
    @classmethod
    def _evidence_ids_from_links(cls, data: Any) -> Any:
        # Same reason as JobRequirementResponse.skill_name above: `evidence_ids` has no
        # ORM attribute counterpart (ComparisonResult has `.evidence_links`), so this
        # must intercept the raw object before any per-field lookup is attempted.
        if isinstance(data, dict):
            return data
        return {
            "id": data.id,
            "job_requirement_id": data.job_requirement_id,
            "knowledge_status": data.knowledge_status,
            "reasoning": data.reasoning,
            "evidence_ids": [link.evidence_id for link in data.evidence_links],
            "created_at": data.created_at,
        }


class GapResponse(BaseModel):
    """One entry from comparison_service.skill_gaps: a RequirementGap, reshaped."""

    requirement: JobRequirementResponse
    result: ComparisonResultResponse

    @classmethod
    def from_gap(cls, gap: Any) -> "GapResponse":
        # comparison_service.RequirementGap is a plain dataclass (requirement, result),
        # not an ORM model, so each field is built from_attributes individually here.
        return cls(
            requirement=JobRequirementResponse.model_validate(gap.requirement),
            result=ComparisonResultResponse.model_validate(gap.result),
        )


class UserSkillCreate(BaseModel):
    skill_id: int


class UserSkillResponse(BaseModel):
    """Public shape of a UserSkill claim; `skill_name`/`evidence_ids` are pulled from relationships."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    skill_id: int
    skill_name: str
    status: str
    notes: str | None
    evidence_ids: list[int]
    created_at: datetime
    updated_at: datetime

    @model_validator(mode="before")
    @classmethod
    def _skill_name_and_evidence_ids_from_relationships(cls, data: Any) -> Any:
        # Same reason as JobRequirementResponse.skill_name and
        # ComparisonResultResponse.evidence_ids: neither `skill_name` (UserSkill has
        # `.skill`, not `.skill_name`) nor `evidence_ids` (UserSkill has
        # `.evidence_links`, not `.evidence_ids`) has an ORM attribute counterpart, so
        # a per-field from_attributes lookup would fail before a field_validator ran.
        if isinstance(data, dict):
            return data
        return {
            "id": data.id,
            "skill_id": data.skill_id,
            "skill_name": data.skill.name,
            "status": data.status,
            "notes": data.notes,
            "evidence_ids": [link.evidence_id for link in data.evidence_links],
            "created_at": data.created_at,
            "updated_at": data.updated_at,
        }


class EvidenceCreate(BaseModel):
    # Validated against the real EvidenceType enum by Pydantic itself: a bad value is a
    # 422 shape error before any route code runs, same idea as StatusUpdate.status below.
    evidence_type: EvidenceType
    title: str
    description: str | None = None
    url: str | None = None
    work_experience_id: int | None = None
    project_id: int | None = None
    education_id: int | None = None


class EvidenceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    evidence_type: str
    title: str
    description: str | None
    url: str | None
    created_at: datetime


class EvidenceLinkCreate(BaseModel):
    evidence_id: int


class StatusUpdate(BaseModel):
    # Validated against the real VerificationStatus enum by Pydantic itself.
    status: VerificationStatus


class CVPresenceUpdate(BaseModel):
    present: bool


class CVPresenceResponse(BaseModel):
    """Public shape of a CVSkillPresence; `skill_name` is pulled from the relationship."""

    model_config = ConfigDict(from_attributes=True)

    skill_id: int
    skill_name: str
    present: bool
    updated_at: datetime

    @model_validator(mode="before")
    @classmethod
    def _skill_name_from_relationship(cls, data: Any) -> Any:
        # Same reason as UserSkillResponse.skill_name: `skill_name` has no ORM attribute
        # counterpart (CVSkillPresence has `.skill`, not `.skill_name`).
        if isinstance(data, dict):
            return data
        return {
            "skill_id": data.skill_id,
            "skill_name": data.skill.name,
            "present": data.present,
            "updated_at": data.updated_at,
        }


class CVStatusResponse(BaseModel):
    """One cv_service.CombinedSkillStatus, reshaped for the API."""

    skill_id: int
    skill_name: str
    knowledge_status: str | None
    cv_status: str
    recommendation: str | None

    @classmethod
    def from_combined_status(cls, combined: Any) -> "CVStatusResponse":
        # cv_service.CombinedSkillStatus is a plain dataclass, not an ORM model, so this
        # is built field-by-field rather than via from_attributes (same pattern as
        # RejectedRequirementResponse.from_rejection / GapResponse.from_gap).
        return cls(
            skill_id=combined.skill.id,
            skill_name=combined.skill.name,
            knowledge_status=(
                combined.knowledge_status.value if combined.knowledge_status is not None else None
            ),
            cv_status=combined.cv_status.value,
            recommendation=combined.recommendation,
        )


class LearningResourceCreate(BaseModel):
    # Validated against the real LearningMode enum by Pydantic itself (bad value -> 422).
    mode: LearningMode
    title: str
    url: str


class LearningResourceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    skill_id: int
    mode: str
    title: str
    url: str
    created_at: datetime


class LearningModeResources(BaseModel):
    """One learning mode for one skill: its derived YouTube search link + saved links."""

    mode: str
    search_query: str
    search_url: str
    resources: list[LearningResourceResponse]


class SkillLearningResourcesResponse(BaseModel):
    skill_id: int
    skill_name: str
    modes: list[LearningModeResources]


class CVSkillRef(BaseModel):
    skill_id: int
    skill_name: str


class CVFoundSkill(CVSkillRef):
    matched_text: str
    on_cv: bool


class CVScanResponse(BaseModel):
    """A CV scan preview: nothing has been saved yet."""

    characters: int
    found: list[CVFoundSkill]
    on_cv_not_found: list[CVSkillRef]

    @classmethod
    def from_scan(cls, scan: Any) -> "CVScanResponse":
        # cv_import_service.CVScan is a plain dataclass, built field-by-field like
        # GapResponse.from_gap.
        return cls(
            characters=scan.characters,
            found=[
                CVFoundSkill(
                    skill_id=item.skill.id,
                    skill_name=item.skill.name,
                    matched_text=item.matched_text,
                    on_cv=item.on_cv,
                )
                for item in scan.found
            ],
            on_cv_not_found=[
                CVSkillRef(skill_id=skill.id, skill_name=skill.name) for skill in scan.on_cv_not_found
            ],
        )


class CVPresenceBatch(BaseModel):
    """The user's confirmed choices after reviewing a CV scan."""

    present_skill_ids: list[int] = []
    absent_skill_ids: list[int] = []


class LearningProgressUpdate(BaseModel):
    # "not_started" is accepted here but never stored: it means "no row" (see
    # learning_progress_service). Any other value is a 422 from Pydantic itself.
    status: Literal["not_started", "studying", "finished"]


class LearningProgressResponse(BaseModel):
    """The user's progress on one skill; updated_at is None when not started."""

    skill_id: int
    skill_name: str
    status: str
    updated_at: datetime | None

    @classmethod
    def for_skill(cls, skill: Any, progress: Any | None) -> "LearningProgressResponse":
        # Built field-by-field (like CVStatusResponse.from_combined_status): "not
        # started" has no row, so there may be no ORM object to read from at all.
        return cls(
            skill_id=skill.id,
            skill_name=skill.name,
            status=progress.status.value if progress is not None else "not_started",
            updated_at=progress.updated_at if progress is not None else None,
        )
