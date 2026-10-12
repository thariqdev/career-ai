"""The public portfolio demo (stage 94): a made-up career, reset on a schedule.

The app has no login (it's a personal, single-user tool), so the public deployment must
never hold anyone's real data. With DEMO_MODE=true:

- an empty database is SEEDED with the fictional career below at startup, built through
  the app's own services (so it's realistic: a CV, proof that verifies a skill, learning
  progress, three job postings with saved requirements, Compare history, an interview);
- POST /demo/reset (protected by DEMO_RESET_TOKEN; called daily by a GitHub Action)
  empties every table and seeds again, so visitors' changes don't pile up;
- risky endpoints (restoring or importing a backup) are switched off (forbid_in_demo).

Locally (no DEMO_MODE) none of this runs.
"""

import os
from datetime import date, datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import Engine, delete, select, text
from sqlalchemy.orm import Session

from database import Base

DEMO_NAME = "Alex Demo"
DEMO_CV = """Alex Demo
Python, FastAPI, PostgreSQL, Docker, React, TypeScript, Git and REST APIs."""

DEMO_JOBS = [
    {
        "title": "Backend Engineer",
        "company": "Northwind Labs",
        "status": "interviewing",
        "raw_text": (
            "Backend Engineer at Northwind Labs. You will build services in Python with FastAPI and "
            "PostgreSQL, ship them with Docker and Kubernetes on AWS, and keep them healthy with CI/CD. "
            "Experience with Redis is a plus."
        ),
    },
    {
        "title": "Full-Stack Developer",
        "company": "Brightpath",
        "status": "applied",
        "raw_text": (
            "Full-Stack Developer at Brightpath: React and TypeScript on the frontend, Node.js and "
            "GraphQL on the backend, PostgreSQL for data. Testing with Jest. Git and code review daily."
        ),
    },
    {
        "title": "Data Engineer",
        "company": "Quantica",
        "status": "saved",
        "raw_text": (
            "Data Engineer at Quantica. Build pipelines in Python and SQL with Airflow and dbt on "
            "Snowflake. Docker experience and good communication skills."
        ),
    },
]


def demo_mode() -> bool:
    return (os.getenv("DEMO_MODE") or "").strip().lower() in ("1", "true", "yes")


def forbid_in_demo() -> None:
    """A FastAPI dependency: refuse an endpoint in the public demo."""
    if demo_mode():
        raise HTTPException(status_code=403, detail="Not available in the public demo.")


def is_empty(db: Session) -> bool:
    from app.db.models import JobDescription, Skill

    return db.scalar(select(Skill.id).limit(1)) is None and db.scalar(select(JobDescription.id).limit(1)) is None


def empty_all_tables(engine: Engine) -> None:
    """Delete every row (children first). TRUNCATE ... RESTART IDENTITY on PostgreSQL."""
    tables = list(reversed(Base.metadata.sorted_tables))
    with engine.begin() as connection:
        if engine.dialect.name == "postgresql":
            connection.execute(text(f"TRUNCATE {', '.join(t.name for t in tables)} RESTART IDENTITY CASCADE"))
        else:
            for table in tables:
                connection.execute(delete(table))


def seed(db: Session) -> dict[str, int]:
    """Build the fictional career through the app's own services. Commits."""
    from app.ai.providers.skill_list_extractor import SkillListExtractor
    from app.core.services import (
        comparison_service,
        cv_adopt_service,
        learning_progress_service,
        requirement_service,
        skill_service,
        user_service,
    )
    from app.db.models import Education, Evidence, JobDescription, Project, UserSkillEvidence, WorkExperience
    from app.db.models.enums import ApplicationStatus, EvidenceType, LearningStatus, VerificationStatus

    user = user_service.get_or_create_default_user(db)
    cv_adopt_service.add_all_from_cv(db, user, DEMO_CV)  # skills on the CV, claimed (provisional), and the name
    claims = {c.skill.name: c for c in user.user_skills}

    project = Project(user=user, name="TaskFlow API", role="Solo developer",
                      description="A task-tracking REST API built with Python, FastAPI and PostgreSQL.")
    work = WorkExperience(user=user, company="Brightlane", role="Junior Developer",
                          start_date=date(2023, 1, 9), end_date=date(2024, 6, 28),
                          description="Built internal tools in Python and React.")
    db.add_all([project, work, Education(user=user, institution="Northfield University", degree="BSc",
                                         field_of_study="Computer Science",
                                         start_date=date(2019, 9, 1), end_date=date(2022, 6, 30))])
    db.flush()
    repo = Evidence(user=user, evidence_type=EvidenceType.PROJECT, title="TaskFlow repo",
                    url="https://example.com/taskflow", project=project)
    tooling = Evidence(user=user, evidence_type=EvidenceType.WORK_EXPERIENCE, title="Brightlane internal tools",
                       work_experience=work)
    db.add_all([repo, tooling])
    db.flush()
    db.add_all([
        UserSkillEvidence(user_skill_id=claims["Python"].id, evidence_id=repo.id),
        UserSkillEvidence(user_skill_id=claims["FastAPI"].id, evidence_id=repo.id),
        UserSkillEvidence(user_skill_id=claims["React"].id, evidence_id=tooling.id),
    ])
    claims["Python"].status = VerificationStatus.VERIFIED
    claims["FastAPI"].status = VerificationStatus.VERIFIED
    claims["React"].status = VerificationStatus.PARTIAL
    db.flush()

    learning_progress_service.set_progress(db, user, claims["TypeScript"].skill, LearningStatus.STUDYING)
    learning_progress_service.set_progress(db, user, claims["Docker"].skill, LearningStatus.FINISHED)

    for spec in DEMO_JOBS:
        job = JobDescription(user=user, title=spec["title"], company=spec["company"], raw_text=spec["raw_text"],
                             application_status=ApplicationStatus(spec["status"]))
        if spec["status"] != "saved":
            job.applied_on = date.today() - timedelta(days=6)
        if spec["status"] == "interviewing":
            job.next_interview_at = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0) + timedelta(days=3)
        db.add(job)
        db.flush()
        requirement_service.extract_requirements(db, job, SkillListExtractor(skill_service.skill_terms(db)))
        comparison_service.compare_job_description(db, job)
    db.commit()
    return {"skills": len(claims), "jobs": len(DEMO_JOBS)}


def reset(engine: Engine, session_factory) -> dict[str, int]:
    """Empty everything and seed again; the notes cache is cleared too."""
    from app.rag import note_cache

    empty_all_tables(engine)
    note_cache.clear()
    with session_factory() as db:
        return seed(db)


def seed_if_empty(session_factory) -> bool:
    """At startup in demo mode: give a fresh database the demo career. True if seeded."""
    with session_factory() as db:
        if not is_empty(db):
            return False
        seed(db)
        return True
