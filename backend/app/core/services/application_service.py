"""The user's application tracking for a job: status, applied-on date and a note.

Facts the user supplies, never inferred. PATCH semantics: only keys present in `changes`
apply; `notes: null` (or blank) clears the note. Rules, checked on the final state:
- the applied-on date can't be in the future;
- a job that is "saved" (not applied to) has no applied-on date: sending one with
  "saved" is refused, and moving back to "saved" clears it;
- moving to "applied" without an applied-on date (and without sending one) records today,
  since "I applied" happened now. Any other status never fills in a date by itself.

Same conventions as the other services: plain functions taking a Session, no HTTP
knowledge, flush but never commit.
"""

from datetime import date
from typing import Any

from sqlalchemy.orm import Session

from app.core.exceptions import ApplicationDateError
from app.db.models import JobDescription
from app.db.models.enums import ApplicationStatus


def update_application(
    db: Session, job: JobDescription, changes: dict[str, Any], today: date | None = None
) -> JobDescription:
    today = today or date.today()
    status = changes.get("status") or job.application_status
    applied_on = changes["applied_on"] if "applied_on" in changes else job.applied_on

    if applied_on is not None and applied_on > today:
        raise ApplicationDateError("The applied-on date can't be in the future.")
    if status == ApplicationStatus.SAVED:
        if changes.get("applied_on") is not None:
            raise ApplicationDateError(
                "A saved job hasn't been applied to, so it has no applied-on date. "
                "Pick a status like \"applied\" first."
            )
        applied_on = None
    elif (
        changes.get("status") == ApplicationStatus.APPLIED
        and applied_on is None
        and "applied_on" not in changes
    ):
        applied_on = today

    if "notes" in changes:
        note = changes["notes"]
        job.application_notes = note.strip() if note and note.strip() else None
    job.application_status = status
    job.applied_on = applied_on
    db.flush()
    return job
