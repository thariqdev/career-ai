"""Relationship checks for the User/Project/WorkExperience/Education/Evidence cluster.

Uses an in-memory SQLite database so these tests don't require a running
PostgreSQL instance. This only exercises SQLAlchemy mappings (columns,
foreign keys, relationships) — not the (not-yet-built) verification service.
"""

from collections.abc import Iterator
from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.models import Education, Evidence, Project, User, WorkExperience
from app.db.models.enums import EvidenceType
from database import Base


@pytest.fixture()
def session() -> Iterator[Session]:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        yield db
    engine.dispose()


def test_user_owns_project_work_experience_and_education(session: Session) -> None:
    user = User(email="dev@example.com", full_name="Dev User")
    project = Project(user=user, name="FundsApp", role="Backend developer")
    work = WorkExperience(
        user=user, company="Acme Corp", role="Software Engineer", start_date=date(2024, 1, 1)
    )
    education = Education(user=user, institution="State University", degree="B.Sc. CS")

    session.add_all([user, project, work, education])
    session.commit()

    assert project in user.projects
    assert work in user.work_experiences
    assert education in user.educations
    assert project.user is user


def test_evidence_links_back_to_its_source_record(session: Session) -> None:
    user = User(email="dev@example.com")
    project = Project(user=user, name="FundsApp")

    evidence = Evidence(
        user=user,
        project=project,
        evidence_type=EvidenceType.PROJECT,
        title="FundsApp public repository",
        url="https://github.com/example/fundsapp",
    )

    session.add_all([user, project, evidence])
    session.commit()

    assert evidence in user.evidence_records
    assert evidence in project.evidence_records
    assert evidence.project is project
    assert evidence.work_experience is None
    assert evidence.evidence_type is EvidenceType.PROJECT


def test_evidence_can_stand_alone_without_a_source_record(session: Session) -> None:
    """Evidence for e.g. a certification need not point back to another table."""
    user = User(email="dev@example.com")
    evidence = Evidence(
        user=user,
        evidence_type=EvidenceType.CERTIFICATION,
        title="AWS Certified Developer – Associate",
        url="https://www.credly.com/example",
    )

    session.add_all([user, evidence])
    session.commit()

    assert evidence.project is None
    assert evidence.work_experience is None
    assert evidence.education is None
