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
