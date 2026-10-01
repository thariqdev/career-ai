"""Domain exceptions raised by the service layer.

These are plain Python exceptions with no HTTP knowledge. The API layer is
responsible for translating them into responses.
"""


class DomainError(Exception):
    """Base class for every business-rule violation raised by a domain service."""


class EvidenceOwnershipError(DomainError):
    """Evidence belongs to a different user than the UserSkill it is being linked to."""

    def __init__(self, user_skill_id: int, evidence_id: int) -> None:
        super().__init__(
            f"Evidence {evidence_id} does not belong to the same user as UserSkill {user_skill_id}."
        )


class EvidenceAlreadyLinkedError(DomainError):
    """The evidence is already linked to this UserSkill."""

    def __init__(self, user_skill_id: int, evidence_id: int) -> None:
        super().__init__(
            f"Evidence {evidence_id} is already linked to UserSkill {user_skill_id}."
        )


class InsufficientEvidenceError(DomainError):
    """A status that requires supporting evidence was requested with none linked."""

    def __init__(self, user_skill_id: int, requested_status: str) -> None:
        super().__init__(
            f"UserSkill {user_skill_id} cannot be {requested_status}: "
            "no linked evidence. Not enough verified information."
        )


class EmptySkillTextError(DomainError):
    """A skill name or alias was blank or whitespace-only."""

    def __init__(self) -> None:
        super().__init__("Skill name or alias must not be blank.")


class SkillNameCollisionError(DomainError):
    """The text already belongs to an existing skill name or alias.

    Skill names and aliases share one namespace, so a new name or alias may not
    normalize to the same text as any existing one.
    """

    def __init__(self, text: str, existing_skill_name: str) -> None:
        super().__init__(
            f'"{text}" already belongs to the skill "{existing_skill_name}" '
            "(skill names and aliases share one namespace)."
        )


class AliasNotFoundError(DomainError):
    """The skill has no alias matching this text."""

    def __init__(self, skill_name: str, alias: str) -> None:
        super().__init__(f'The skill "{skill_name}" has no alias "{alias.strip()}".')


class RequirementsAlreadyExistError(DomainError):
    """Extraction was refused because the job description already has requirements."""

    def __init__(self, job_description_id: int) -> None:
        super().__init__(
            f"Job description {job_description_id} already has requirements; "
            "extraction was not run again."
        )


class EmptyResourceTitleError(DomainError):
    """A learning resource's title was blank or whitespace-only."""

    def __init__(self) -> None:
        super().__init__("Learning resource title must not be blank.")


class InvalidResourceUrlError(DomainError):
    """A learning resource's URL isn't an http(s) link with a host."""

    def __init__(self, url: str) -> None:
        super().__init__(f'"{url}" is not a valid http or https link.')


class DuplicateLearningResourceError(DomainError):
    """The same URL is already saved for this skill under this learning mode."""

    def __init__(self, url: str) -> None:
        super().__init__(f'"{url}" is already saved for this skill in this learning mode.')


class AmbiguousSkillMatchError(DomainError):
    """The text matched more than one distinct Skill, so no single answer is safe."""

    def __init__(self, text: str, skill_names: list[str]) -> None:
        super().__init__(
            f'"{text}" is ambiguous: it matches multiple skills ({", ".join(sorted(skill_names))}). '
            "Fix the taxonomy so it maps to exactly one."
        )
