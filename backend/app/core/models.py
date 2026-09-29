from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator


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
