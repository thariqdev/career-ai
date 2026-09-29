"""Relationship checks for JobRequirement.

Uses an in-memory SQLite database, same approach as the other model tests.
Extraction and skill-mapping logic don't exist yet — this only confirms the
records are wired to JobDescription and Skill correctly.
"""

from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.models import JobDescription, JobRequirement, Skill, User
from database import Base


@pytest.fixture()
def session() -> Iterator[Session]:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        yield db
    engine.dispose()


def test_requirement_links_to_its_job_description_and_canonical_skill(
    session: Session,
) -> None:
    user = User(email="dev@example.com")
    posting = JobDescription(user=user, raw_text="Need Postgres experience.")
    postgres = Skill(name="PostgreSQL")
    requirement = JobRequirement(
        job_description=posting, skill=postgres, requirement_text="Postgres experience"
    )

    session.add_all([user, posting, postgres, requirement])
    session.commit()

    assert requirement in posting.requirements
    assert requirement in postgres.job_requirements
    assert requirement.is_required is True


def test_requirement_without_a_known_skill_stays_unmapped(session: Session) -> None:
    """Unknown technologies must not force a new Skill to be invented."""
    user = User(email="dev@example.com")
    posting = JobDescription(user=user, raw_text="Need Zorblax experience.")
    requirement = JobRequirement(
        job_description=posting, requirement_text="Zorblax experience", is_required=False
    )

    session.add_all([user, posting, requirement])
    session.commit()

    assert requirement.skill is None
    assert requirement.is_required is False
    assert session.query(Skill).count() == 0
