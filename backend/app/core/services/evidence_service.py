"""Editing and deleting Evidence safely.

Evidence is only deleted when nothing depends on it. Refusing (not cascading) is the
point: a claim never silently loses its proof, and a past comparison never loses the
evidence it cited (ComparisonResultEvidence is append-only history).

Editing (update_evidence) re-checks every rule on the evidence as it WILL be after the
edit, and never touches any claim's status. Past comparisons keep pointing at the same
evidence id, so they show its corrected text.

Same conventions as the other services: plain functions taking a Session, no HTTP
knowledge, flush but never commit.
"""

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.exceptions import EmptyProfileFieldError, EvidenceInUseError, TooManyEvidenceSourcesError
from app.core.web_links import require_web_link
from app.db.models import ComparisonResultEvidence, Evidence, UserSkillEvidence


_SOURCE_FIELDS = ("work_experience_id", "project_id", "education_id")


def update_evidence(db: Session, evidence: Evidence, changes: dict[str, Any]) -> Evidence:
    """Apply only the fields present in `changes` (a PATCH), then re-check every rule.

    title and evidence_type can't be cleared; description/url can (None or blank). A url
    must be an http(s) link. Afterwards the evidence must still have at most one source:
    to switch source, clear the old one in the same request.
    """
    clean: dict[str, Any] = {}
    for key, value in changes.items():
        if key == "title":
            if value is None or not value.strip():
                raise EmptyProfileFieldError("Title")
            clean[key] = value.strip()
        elif key == "evidence_type":
            if value is None:
                raise EmptyProfileFieldError("Type")
            clean[key] = value
        elif key in ("description", "url"):
            clean[key] = value.strip() if value is not None and value.strip() else None
        else:
            clean[key] = value  # source ids (ownership is checked by the route)
    if clean.get("url") is not None:
        clean["url"] = require_web_link(clean["url"])

    final_sources = [clean.get(f, getattr(evidence, f)) for f in _SOURCE_FIELDS]
    if sum(source is not None for source in final_sources) > 1:
        raise TooManyEvidenceSourcesError()

    for key, value in clean.items():
        setattr(evidence, key, value)
    db.flush()
    return evidence


def delete_evidence(db: Session, evidence: Evidence) -> None:
    """Delete evidence nothing depends on; EvidenceInUseError (409) otherwise."""
    db.flush()

    def count(model: type) -> int:
        return db.scalar(
            select(func.count()).select_from(model).where(model.evidence_id == evidence.id)
        )

    reasons = []
    if (n := count(UserSkillEvidence)):
        reasons.append(f"linked to {n} skill{'s' if n != 1 else ''} (unlink it first)")
    if (n := count(ComparisonResultEvidence)):
        reasons.append(f"part of {n} past comparison result{'s' if n != 1 else ''}")
    if reasons:
        raise EvidenceInUseError(evidence.title, reasons)

    db.delete(evidence)
    db.flush()
