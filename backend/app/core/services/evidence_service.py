"""Deleting Evidence safely.

Evidence is only deleted when nothing depends on it. Refusing (not cascading) is the
point: a claim never silently loses its proof, and a past comparison never loses the
evidence it cited (ComparisonResultEvidence is append-only history).

Same conventions as the other services: plain functions taking a Session, no HTTP
knowledge, flush but never commit.
"""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.exceptions import EvidenceInUseError
from app.db.models import ComparisonResultEvidence, Evidence, UserSkillEvidence


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
