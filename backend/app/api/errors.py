"""Maps domain errors (plain Python, raised by services) to HTTP responses.

Registered once on the app in main.py, so routes never need try/except for DomainError.
The body matches FastAPI's own error shape: {"detail": "<message>"}.
"""

from fastapi import Request
from fastapi.responses import JSONResponse

from app.core.exceptions import (
    AliasNotFoundError,
    AmbiguousSkillMatchError,
    DomainError,
    DuplicateLearningResourceError,
    EmptyResourceTitleError,
    EmptySkillTextError,
    EvidenceAlreadyLinkedError,
    EvidenceOwnershipError,
    InsufficientEvidenceError,
    InvalidResourceUrlError,
    RequirementsAlreadyExistError,
    SkillNameCollisionError,
)

_STATUS_BY_ERROR: dict[type[DomainError], int] = {
    EmptySkillTextError: 422,
    EmptyResourceTitleError: 422,
    InvalidResourceUrlError: 422,
    DuplicateLearningResourceError: 409,
    AliasNotFoundError: 404,
    SkillNameCollisionError: 409,
    AmbiguousSkillMatchError: 409,
    EvidenceOwnershipError: 409,
    EvidenceAlreadyLinkedError: 409,
    InsufficientEvidenceError: 409,
    RequirementsAlreadyExistError: 409,
}
_DEFAULT_STATUS = 400  # any other DomainError subclass


def _status_for(error: DomainError) -> int:
    # Walk the class hierarchy so a future subclass of a mapped error inherits its status.
    for error_class in type(error).__mro__:
        if error_class in _STATUS_BY_ERROR:
            return _STATUS_BY_ERROR[error_class]
    return _DEFAULT_STATUS


async def domain_error_handler(request: Request, error: DomainError) -> JSONResponse:
    return JSONResponse(status_code=_status_for(error), content={"detail": str(error)})
