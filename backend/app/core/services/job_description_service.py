"""Deleting a job description, or one of its requirements, with the history that belongs only to it.

A job's requirements and their comparison results (and those results' evidence links)
exist only for that job, so they go with it. Nothing outside the job is touched:
skills, claims, evidence and CV marks stay exactly as they were. (Evidence itself is
never deleted here; only the ComparisonResultEvidence rows that cited it for this job.)

The same holds one level down: a single requirement's comparison results exist only
for that requirement, so delete_requirement removes them with it and leaves the job's
other requirements and results alone.

Rows are removed child-first, in foreign-key order, with bulk DELETE statements.

Same conventions as the other services: plain functions taking a Session, no HTTP
knowledge, flush but never commit.
"""

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db.models import ComparisonResult, ComparisonResultEvidence, JobDescription, JobRequirement


def delete_job_description(db: Session, job_description: JobDescription) -> None:
    db.flush()
    requirement_ids = select(JobRequirement.id).where(
        JobRequirement.job_description_id == job_description.id
    )
    result_ids = select(ComparisonResult.id).where(
        ComparisonResult.job_requirement_id.in_(requirement_ids)
    )
    db.execute(
        delete(ComparisonResultEvidence).where(
            ComparisonResultEvidence.comparison_result_id.in_(result_ids)
        )
    )
    db.execute(delete(ComparisonResult).where(ComparisonResult.job_requirement_id.in_(requirement_ids)))
    db.execute(delete(JobRequirement).where(JobRequirement.job_description_id == job_description.id))
    db.execute(delete(JobDescription).where(JobDescription.id == job_description.id))
    db.flush()


def delete_requirement(db: Session, requirement: JobRequirement) -> None:
    """Remove one requirement with its own comparison results (and their evidence links).

    Nothing else is touched: other requirements of the job keep their results. Note that
    "Look for new skills" re-reads the posting and may add the requirement back.
    """
    db.flush()
    result_ids = select(ComparisonResult.id).where(
        ComparisonResult.job_requirement_id == requirement.id
    )
    db.execute(
        delete(ComparisonResultEvidence).where(
            ComparisonResultEvidence.comparison_result_id.in_(result_ids)
        )
    )
    db.execute(delete(ComparisonResult).where(ComparisonResult.job_requirement_id == requirement.id))
    db.execute(delete(JobRequirement).where(JobRequirement.id == requirement.id))
    db.flush()
