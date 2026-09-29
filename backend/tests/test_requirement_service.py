"""Tests for requirement_service (the LLM is an untrusted proposer; the backend disposes).

Uses an in-memory SQLite database, same approach as the other service tests. The
session uses autoflush=False to match SessionLocal in database.py. There is no real
LLM anywhere: tests use small fake extractors returning canned proposals.
"""

from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.ai.schemas import ExtractedRequirement, ExtractionResult
from app.core.exceptions import RequirementsAlreadyExistError
from app.core.services import comparison_service, requirement_service, skill_service
from app.db.models import (
    ComparisonResult,
    JobDescription,
    JobRequirement,
    Skill,
    SkillAlias,
    User,
    UserSkill,
)
from app.db.models.enums import VerificationStatus
from app.core.services.requirement_service import (
    REJECTED_BLANK,
    REJECTED_DUPLICATE,
    REJECTED_NOT_GROUNDED,
)
from database import Base


class FakeExtractor:
    """Returns canned proposals and records every call it receives."""

    def __init__(self, *proposals: ExtractedRequirement) -> None:
        self._result = ExtractionResult(requirements=list(proposals))
        self.calls: list[str] = []

    def extract_requirements(self, raw_text: str) -> ExtractionResult:
        self.calls.append(raw_text)
        return self._result


class FailingExtractor:
    def extract_requirements(self, raw_text: str) -> ExtractionResult:
        raise RuntimeError("model unavailable")


@pytest.fixture()
def session() -> Iterator[Session]:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine, autoflush=False) as db:
        yield db
    engine.dispose()


def _proposal(
    text: str, is_required: bool = True, mention: str | None = None
) -> ExtractedRequirement:
    return ExtractedRequirement(text=text, is_required=is_required, skill_mention=mention)


def _job(db: Session, raw_text: str) -> JobDescription:
    user = User(email="a@example.com")
    job = JobDescription(user=user, raw_text=raw_text)
    db.add_all([user, job])
    db.flush()
    return job


def _count(db: Session, model: type) -> int:
    return db.scalar(select(func.count()).select_from(model))


def _stored_texts(db: Session) -> list[str]:
    return list(db.scalars(select(JobRequirement.requirement_text).order_by(JobRequirement.id)))


RAW = "We need Python experience and PostgreSQL knowledge. Docker is a plus."


# --- accepting grounded proposals -------------------------------------------


def test_grounded_proposals_are_stored_in_order_with_flags_and_stripped_text(
    session: Session,
) -> None:
    job = _job(session, RAW)
    extractor = FakeExtractor(
        _proposal("Python experience", True),
        _proposal("PostgreSQL knowledge", True),
        _proposal("  Docker is a plus  ", False),
    )

    outcome = requirement_service.extract_requirements(session, job, extractor)

    assert [r.requirement_text for r in outcome.accepted] == [
        "Python experience",
        "PostgreSQL knowledge",
        "Docker is a plus",
    ]
    assert [r.is_required for r in outcome.accepted] == [True, True, False]
    assert all(r.id is not None and r.job_description_id == job.id for r in outcome.accepted)
    assert outcome.rejected == []
    assert _stored_texts(session) == [r.requirement_text for r in outcome.accepted]
    assert extractor.calls == [RAW]


def test_an_invented_requirement_is_rejected_and_not_stored(session: Session) -> None:
    job = _job(session, RAW)
    invented = _proposal("Kubernetes expertise")
    extractor = FakeExtractor(_proposal("Python experience"), invented)

    outcome = requirement_service.extract_requirements(session, job, extractor)

    assert [r.requirement_text for r in outcome.accepted] == ["Python experience"]
    [rejection] = outcome.rejected
    assert rejection.proposal is invented
    assert rejection.reason == REJECTED_NOT_GROUNDED
    assert _stored_texts(session) == ["Python experience"]  # nothing stored for the reject


def test_grounding_tolerates_only_case_and_whitespace_and_rejects_paraphrases(
    session: Session,
) -> None:
    job = _job(session, "Python\n   experience required.")
    extractor = FakeExtractor(
        _proposal("  python   EXPERIENCE "),  # same words, different case/whitespace
        _proposal("Experience with Python"),  # a paraphrase
    )

    outcome = requirement_service.extract_requirements(session, job, extractor)

    assert [r.requirement_text for r in outcome.accepted] == ["python   EXPERIENCE"]
    [rejection] = outcome.rejected
    assert rejection.proposal.text == "Experience with Python"
    assert rejection.reason == REJECTED_NOT_GROUNDED


def test_blank_proposed_text_is_rejected(session: Session) -> None:
    job = _job(session, RAW)
    extractor = FakeExtractor(_proposal(""), _proposal("   "), _proposal("Python experience"))

    outcome = requirement_service.extract_requirements(session, job, extractor)

    assert [r.reason for r in outcome.rejected] == [REJECTED_BLANK, REJECTED_BLANK]
    assert _stored_texts(session) == ["Python experience"]


def test_duplicate_texts_are_stored_once_and_first_wins(session: Session) -> None:
    job = _job(session, "Python experience is needed.")
    first = _proposal("Python experience", True)
    duplicate = _proposal("  PYTHON   experience ", False)

    outcome = requirement_service.extract_requirements(session, job, FakeExtractor(first, duplicate))

    [accepted] = outcome.accepted
    assert accepted.requirement_text == "Python experience"
    assert accepted.is_required is True
    [rejection] = outcome.rejected
    assert rejection.proposal is duplicate
    assert rejection.reason == REJECTED_DUPLICATE
    assert _stored_texts(session) == ["Python experience"]


# --- skill mapping: only through the taxonomy --------------------------------


def test_skill_mention_resolves_by_canonical_name_and_by_alias(session: Session) -> None:
    python = skill_service.create_skill(session, "Python")
    postgres = skill_service.create_skill(session, "PostgreSQL")
    skill_service.add_alias(session, postgres, "Postgres")
    job = _job(session, "Need Python. Need PostgreSQL. Need Postgres.")
    extractor = FakeExtractor(
        _proposal("Python", mention="python"),
        _proposal("PostgreSQL", mention="postgresql"),
        _proposal("Postgres", mention="POSTGRES"),
    )

    outcome = requirement_service.extract_requirements(session, job, extractor)

    assert [r.skill_id for r in outcome.accepted] == [python.id, postgres.id, postgres.id]


def test_unknown_skill_mention_stays_unmapped_and_creates_no_skill(session: Session) -> None:
    skill_service.create_skill(session, "Python")
    job = _job(session, "Need Zorblax experience.")
    before = (_count(session, Skill), _count(session, SkillAlias))

    outcome = requirement_service.extract_requirements(
        session, job, FakeExtractor(_proposal("Zorblax experience", mention="Zorblax"))
    )

    [requirement] = outcome.accepted
    assert requirement.skill_id is None
    assert (_count(session, Skill), _count(session, SkillAlias)) == before  # LLM cannot invent skills


@pytest.mark.parametrize("mention", [None, "", "   "])
def test_blank_or_missing_skill_mention_is_unmapped(session: Session, mention: str | None) -> None:
    skill_service.create_skill(session, "Python")
    job = _job(session, "Need Python experience.")

    outcome = requirement_service.extract_requirements(
        session, job, FakeExtractor(_proposal("Python experience", mention=mention))
    )

    assert outcome.accepted[0].skill_id is None


def test_ambiguous_skill_mention_is_stored_unmapped_without_failing(session: Session) -> None:
    """Bypass the service to create the bad data the DB itself does not forbid."""
    first, second = Skill(name="React.js"), Skill(name="React Native")
    session.add_all(
        [first, second, SkillAlias(skill=first, alias="React"), SkillAlias(skill=second, alias="react")]
    )
    job = _job(session, "React experience wanted.")

    outcome = requirement_service.extract_requirements(
        session, job, FakeExtractor(_proposal("React experience", mention="React"))
    )

    [requirement] = outcome.accepted
    assert requirement.skill_id is None
    assert outcome.rejected == []
    assert _count(session, Skill) == 2


# --- refusal, failures, transactions -----------------------------------------


def test_refuses_when_requirements_already_exist_and_never_calls_the_extractor(
    session: Session,
) -> None:
    job = _job(session, RAW)
    session.add(JobRequirement(job_description=job, requirement_text="Existing"))
    session.flush()
    extractor = FakeExtractor(_proposal("Python experience"))

    with pytest.raises(RequirementsAlreadyExistError) as excinfo:
        requirement_service.extract_requirements(session, job, extractor)

    assert str(job.id) in str(excinfo.value)
    assert extractor.calls == []  # no LLM cost or side effects when refused
    assert _stored_texts(session) == ["Existing"]


def test_the_refusal_reads_the_database_not_a_stale_relationship(session: Session) -> None:
    job = _job(session, RAW)
    assert job.requirements == []  # relationship collection is now loaded (and empty)
    session.add(JobRequirement(job_description_id=job.id, requirement_text="Added around it"))
    session.flush()
    assert job.requirements == []  # ...and is stale

    with pytest.raises(RequirementsAlreadyExistError):
        requirement_service.extract_requirements(
            session, job, FakeExtractor(_proposal("Python experience"))
        )


def test_an_extractor_failure_propagates_and_stores_nothing(session: Session) -> None:
    job = _job(session, RAW)

    with pytest.raises(RuntimeError, match="model unavailable"):
        requirement_service.extract_requirements(session, job, FailingExtractor())

    assert _count(session, JobRequirement) == 0


def test_the_service_never_commits_and_touches_no_knowledge_or_comparison_tables(
    session: Session,
) -> None:
    job = _job(session, RAW)
    session.commit()  # the job description is durable; everything after this is the service's

    requirement_service.extract_requirements(
        session, job, FakeExtractor(_proposal("Python experience"), _proposal("Docker is a plus"))
    )

    assert _count(session, JobRequirement) == 2
    assert _count(session, UserSkill) == 0
    assert _count(session, ComparisonResult) == 0
    session.rollback()
    assert _count(session, JobRequirement) == 0  # nothing had been committed


# --- end to end with the existing services -----------------------------------


def test_extracted_requirements_flow_into_comparison_and_gaps(session: Session) -> None:
    python = skill_service.create_skill(session, "Python")
    job = _job(session, "Need Python experience and some obscure tooling.")
    session.add(UserSkill(user=job.user, skill=python))  # a PROVISIONAL claim, no evidence
    session.flush()
    extractor = FakeExtractor(
        _proposal("Python experience", mention="Python"),
        _proposal("some obscure tooling", mention=None),
    )

    outcome = requirement_service.extract_requirements(session, job, extractor)
    results = comparison_service.compare_job_description(session, job)

    assert [r.job_requirement_id for r in results] == [r.id for r in outcome.accepted]
    assert results[0].knowledge_status is VerificationStatus.PROVISIONAL
    assert results[0].user_skill is not None
    assert results[1].knowledge_status is VerificationStatus.NOT_VERIFIED  # unmapped
    assert results[1].user_skill is None
    gaps = comparison_service.skill_gaps(session, job)
    assert [g.requirement.id for g in gaps] == [r.id for r in outcome.accepted]
    assert [g.skill for g in gaps] == [python, None]
