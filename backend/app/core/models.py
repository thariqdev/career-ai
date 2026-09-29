from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from app.db.models.enums import EvidenceType, VerificationStatus


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
    """Public shape of a UserSkill claim; `skill_name` is pulled from the relationship."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    skill_id: int
    skill_name: str
    status: str
    notes: str | None
    created_at: datetime
    updated_at: datetime

    @model_validator(mode="before")
    @classmethod
    def _skill_name_from_relationship(cls, data: Any) -> Any:
        # Same reason as JobRequirementResponse.skill_name: `skill_name` has no ORM
        # attribute counterpart (UserSkill has `.skill`, not `.skill_name`), so a
        # per-field from_attributes lookup would fail before a field_validator ran.
        if isinstance(data, dict):
            return data
        return {
            "id": data.id,
            "skill_id": data.skill_id,
            "skill_name": data.skill.name,
            "status": data.status,
            "notes": data.notes,
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
