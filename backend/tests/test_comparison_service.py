"""Tests for comparison_service (deterministic requirement-vs-knowledge comparison).

Uses an in-memory SQLite database, same approach as the other service tests. The
session uses autoflush=False to match SessionLocal in database.py.
"""

from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session

from app.core.services import comparison_service, skill_service, verification_service
from app.db.models import (
    ComparisonResult,
    ComparisonResultEvidence,
    Evidence,
    JobDescription,
    JobRequirement,
    Skill,
    User,
    UserSkill,
    UserSkillEvidence,
)
from app.db.models.enums import EvidenceType, VerificationStatus
from database import Base

NOT_ENOUGH = "Not enough verified information."


@pytest.fixture()
def session() -> Iterator[Session]:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine, autoflush=False) as db:
        yield db
    engine.dispose()


def _user(db: Session, email: str = "a@example.com") -> User:
    user = User(email=email)
    db.add(user)
    db.flush()
    return user


def _job(db: Session, user: User) -> JobDescription:
    job = JobDescription(user=user, raw_text="We need a backend engineer.")
    db.add(job)
    db.flush()
    return job


def _requirement(
    db: Session, job: JobDescription, skill: Skill | None = None, is_required: bool = True
) -> JobRequirement:
    requirement = JobRequirement(
        job_description=job,
        skill=skill,
        requirement_text="some requirement",
        is_required=is_required,
    )
    db.add(requirement)
    db.flush()
    return requirement


def _claim(db: Session, user: User, skill: Skill, status: VerificationStatus | None = None) -> UserSkill:
    """A UserSkill created the normal way (PROVISIONAL, no evidence) unless a status is forced."""
    user_skill = UserSkill(user=user, skill=skill)
    if status is not None:
        user_skill.status = status  # only used to fake bad/bypassing data in tests
    db.add(user_skill)
    db.flush()
    return user_skill


def _evidence(db: Session, user: User, title: str) -> Evidence:
    evidence = Evidence(user=user, evidence_type=EvidenceType.PROJECT, title=title)
    db.add(evidence)
    db.flush()
    return evidence


def _verify_legitimately(
    db: Session, user_skill: UserSkill, evidence: list[Evidence], status: VerificationStatus
) -> None:
    for item in evidence:
        verification_service.link_evidence(db, user_skill, item)
    verification_service.set_status(db, user_skill, status)


def _evidence_ids(result: ComparisonResult) -> set[int]:
    return {link.evidence_id for link in result.evidence_links}


def test_unmapped_requirement_is_not_verified(session: Session) -> None:
    user = _user(session)
    job = _job(session, user)
    requirement = _requirement(session, job, skill=None)

    [result] = comparison_service.compare_job_description(session, job)

    assert result.job_requirement is requirement
    assert result.knowledge_status is VerificationStatus.NOT_VERIFIED
    assert result.user_skill is None
    assert result.evidence_links == []
    assert NOT_ENOUGH in result.reasoning


def test_mapped_requirement_without_a_user_skill_is_not_verified(session: Session) -> None:
    user = _user(session)
    python = skill_service.create_skill(session, "Python")
    job = _job(session, user)
    _requirement(session, job, skill=python)

    [result] = comparison_service.compare_job_description(session, job)

    assert result.knowledge_status is VerificationStatus.NOT_VERIFIED
    assert result.user_skill is None
    assert result.evidence_links == []
    assert NOT_ENOUGH in result.reasoning


def test_provisional_user_skill_is_reported_as_provisional(session: Session) -> None:
    user = _user(session)
    python = skill_service.create_skill(session, "Python")
    user_skill = _claim(session, user, python)
    job = _job(session, user)
    _requirement(session, job, skill=python)

    [result] = comparison_service.compare_job_description(session, job)

    assert result.knowledge_status is VerificationStatus.PROVISIONAL
    assert result.user_skill is user_skill
    assert result.evidence_links == []


def test_verified_user_skill_links_exactly_its_evidence(session: Session) -> None:
    user = _user(session)
    python = skill_service.create_skill(session, "Python")
    user_skill = _claim(session, user, python)
    first = _evidence(session, user, "FundsApp repo")
    second = _evidence(session, user, "Py cert")
    _verify_legitimately(session, user_skill, [first, second], VerificationStatus.VERIFIED)
    job = _job(session, user)
    _requirement(session, job, skill=python)

    [result] = comparison_service.compare_job_description(session, job)

    assert result.knowledge_status is VerificationStatus.VERIFIED
    assert result.user_skill is user_skill
    assert _evidence_ids(result) == {first.id, second.id}
    assert len(result.evidence_links) == 2
    assert f"#{first.id}" in result.reasoning
    assert f"#{second.id}" in result.reasoning
    assert f"#{user_skill.id}" in result.reasoning


def test_partial_user_skill_with_one_evidence(session: Session) -> None:
    user = _user(session)
    python = skill_service.create_skill(session, "Python")
    user_skill = _claim(session, user, python)
    evidence = _evidence(session, user, "Side project")
    _verify_legitimately(session, user_skill, [evidence], VerificationStatus.PARTIAL)
    job = _job(session, user)
    _requirement(session, job, skill=python)

    [result] = comparison_service.compare_job_description(session, job)

    assert result.knowledge_status is VerificationStatus.PARTIAL
    assert _evidence_ids(result) == {evidence.id}


@pytest.mark.parametrize("claimed", [VerificationStatus.VERIFIED, VerificationStatus.PARTIAL])
def test_evidence_less_verified_or_partial_claim_is_capped_to_provisional(
    session: Session, claimed: VerificationStatus
) -> None:
    """Data written around verification_service must never be repeated as a claim."""
    user = _user(session)
    python = skill_service.create_skill(session, "Python")
    user_skill = _claim(session, user, python, status=claimed)
    job = _job(session, user)
    _requirement(session, job, skill=python)

    [result] = comparison_service.compare_job_description(session, job)

    assert result.knowledge_status is VerificationStatus.PROVISIONAL
    assert result.user_skill is user_skill
    assert result.evidence_links == []
    assert "not backed by evidence" in result.reasoning
    assert claimed.name in result.reasoning


def test_another_users_user_skill_is_never_used(session: Session) -> None:
    user_a = _user(session, "a@example.com")
    user_b = _user(session, "b@example.com")
    python = skill_service.create_skill(session, "Python")
    b_skill = _claim(session, user_b, python)
    b_evidence = _evidence(session, user_b, "B's project")
    _verify_legitimately(session, b_skill, [b_evidence], VerificationStatus.VERIFIED)
    job = _job(session, user_a)
    _requirement(session, job, skill=python)

    [result] = comparison_service.compare_job_description(session, job)

    assert result.knowledge_status is VerificationStatus.NOT_VERIFIED
    assert result.user_skill is None
    assert result.evidence_links == []


def test_multiple_requirements_produce_one_result_each_in_requirement_id_order(
    session: Session,
) -> None:
    user = _user(session)
    python = skill_service.create_skill(session, "Python")
    postgres = skill_service.create_skill(session, "PostgreSQL")
    job = _job(session, user)
    requirements = [
        _requirement(session, job, skill=postgres),
        _requirement(session, job, skill=None),
        _requirement(session, job, skill=python),
    ]

    results = comparison_service.compare_job_description(session, job)

    assert [r.job_requirement_id for r in results] == [r.id for r in requirements]
    assert [r.job_requirement_id for r in results] == sorted(r.id for r in requirements)
    assert len(results) == 3


def test_requirements_are_queried_with_an_explicit_order_by(session: Session) -> None:
    """SQLite happens to return rows in id order anyway, so check the SQL itself.

    Determinism must come from the query, not from the database's incidental behavior.
    """
    user = _user(session)
    job = _job(session, user)
    _requirement(session, job)
    statements: list[str] = []
    engine = session.get_bind()
    listener = lambda conn, cursor, statement, *args: statements.append(statement)  # noqa: E731
    event.listen(engine, "before_cursor_execute", listener)
    try:
        comparison_service.compare_job_description(session, job)
    finally:
        event.remove(engine, "before_cursor_execute", listener)

    requirement_queries = [s for s in statements if "FROM job_requirements" in s]
    assert requirement_queries
    assert all("ORDER BY job_requirements.id" in s for s in requirement_queries)


def test_is_required_does_not_influence_status(session: Session) -> None:
    user = _user(session)
    python = skill_service.create_skill(session, "Python")
    user_skill = _claim(session, user, python)
    evidence = _evidence(session, user, "FundsApp repo")
    _verify_legitimately(session, user_skill, [evidence], VerificationStatus.VERIFIED)
    job = _job(session, user)
    _requirement(session, job, skill=python, is_required=True)
    _requirement(session, job, skill=python, is_required=False)

    required, optional = comparison_service.compare_job_description(session, job)

    assert required.knowledge_status is optional.knowledge_status is VerificationStatus.VERIFIED


def test_results_are_append_only_snapshots(session: Session) -> None:
    user = _user(session)
    python = skill_service.create_skill(session, "Python")
    user_skill = _claim(session, user, python)
    job = _job(session, user)
    requirement = _requirement(session, job, skill=python)

    [first_run] = comparison_service.compare_job_description(session, job)
    [again] = comparison_service.compare_job_description(session, job)
    assert first_run.id != again.id
    assert session.scalar(select(func.count()).select_from(ComparisonResult)) == 2

    evidence = _evidence(session, user, "FundsApp repo")
    _verify_legitimately(session, user_skill, [evidence], VerificationStatus.VERIFIED)
    [third_run] = comparison_service.compare_job_description(session, job)

    assert session.scalar(select(func.count()).select_from(ComparisonResult)) == 3
    assert third_run.knowledge_status is VerificationStatus.VERIFIED
    assert _evidence_ids(third_run) == {evidence.id}
    # Earlier snapshots are unchanged.
    assert first_run.knowledge_status is VerificationStatus.PROVISIONAL
    assert first_run.evidence_links == []
    assert again.knowledge_status is VerificationStatus.PROVISIONAL
    assert len(requirement.comparison_results) == 3


def test_comparison_does_not_change_user_skill_or_its_evidence_links(session: Session) -> None:
    user = _user(session)
    python = skill_service.create_skill(session, "Python")
    user_skill = _claim(session, user, python)
    evidence = [_evidence(session, user, "one"), _evidence(session, user, "two")]
    _verify_legitimately(session, user_skill, evidence, VerificationStatus.VERIFIED)
    job = _job(session, user)
    _requirement(session, job, skill=python)

    def snapshot() -> tuple:
        links = session.scalars(
            select(UserSkillEvidence.evidence_id).where(
                UserSkillEvidence.user_skill_id == user_skill.id
            )
        ).all()
        return (user_skill.status, sorted(links))

    before = snapshot()
    comparison_service.compare_job_description(session, job)
    comparison_service.compare_job_description(session, job)

    assert snapshot() == before


def test_job_description_with_no_requirements_returns_empty_list(session: Session) -> None:
    user = _user(session)
    job = _job(session, user)

    assert comparison_service.compare_job_description(session, job) == []
    assert session.scalar(select(func.count()).select_from(ComparisonResult)) == 0


# --- read side: latest_results / skill_gaps ----------------------------------


def _count(db: Session, model: type) -> int:
    return db.scalar(select(func.count()).select_from(model))


def _held_skill(db: Session, user: User, name: str, status: VerificationStatus) -> Skill:
    """A skill the user holds at `status` (PROVISIONAL, PARTIAL or VERIFIED), set up legitimately."""
    skill = skill_service.create_skill(db, name)
    user_skill = _claim(db, user, skill)
    if status is not VerificationStatus.PROVISIONAL:
        evidence = [_evidence(db, user, f"{name} evidence")]
        _verify_legitimately(db, user_skill, evidence, status)
    return skill


def test_latest_results_returns_only_the_highest_id_result_per_requirement(
    session: Session,
) -> None:
    user = _user(session)
    python = skill_service.create_skill(session, "Python")
    postgres = skill_service.create_skill(session, "PostgreSQL")
    job = _job(session, user)
    requirements = [
        _requirement(session, job, skill=python),
        _requirement(session, job, skill=None),
        _requirement(session, job, skill=postgres),
    ]
    runs = [comparison_service.compare_job_description(session, job) for _ in range(3)]

    latest = comparison_service.latest_results(session, job)

    assert len(latest) == 3
    assert [r.id for r in latest] == [r.id for r in runs[-1]]
    assert [r.job_requirement_id for r in latest] == [r.id for r in requirements]
    older_ids = {r.id for run in runs[:-1] for r in run}
    assert older_ids.isdisjoint({r.id for r in latest})
    assert _count(session, ComparisonResult) == 9  # history untouched


def test_latest_results_are_ordered_by_requirement_id_not_by_result_id(session: Session) -> None:
    """Results are inserted in the opposite order, so incidental id order would be wrong."""
    user = _user(session)
    job = _job(session, user)
    first_requirement = _requirement(session, job)
    second_requirement = _requirement(session, job)
    for requirement in (second_requirement, first_requirement):  # result ids: 1 -> second, 2 -> first
        session.add(
            ComparisonResult(
                job_requirement=requirement,
                knowledge_status=VerificationStatus.NOT_VERIFIED,
                reasoning=NOT_ENOUGH,
            )
        )
    session.flush()

    latest = comparison_service.latest_results(session, job)

    assert [r.job_requirement_id for r in latest] == [first_requirement.id, second_requirement.id]


def test_latest_results_query_has_an_explicit_order_by(session: Session) -> None:
    user = _user(session)
    job = _job(session, user)
    _requirement(session, job)
    comparison_service.compare_job_description(session, job)
    statements: list[str] = []
    engine = session.get_bind()
    listener = lambda conn, cursor, statement, *args: statements.append(statement)  # noqa: E731
    event.listen(engine, "before_cursor_execute", listener)
    try:
        comparison_service.latest_results(session, job)
    finally:
        event.remove(engine, "before_cursor_execute", listener)

    assert any("ORDER BY comparison_results.job_requirement_id" in s for s in statements)


def test_a_requirement_never_compared_is_absent_and_nothing_is_run(session: Session) -> None:
    user = _user(session)
    job = _job(session, user)
    compared = _requirement(session, job, skill=None)
    comparison_service.compare_job_description(session, job)
    never_compared = _requirement(session, job, skill=None)  # added after the comparison ran

    latest = comparison_service.latest_results(session, job)
    gaps = comparison_service.skill_gaps(session, job)

    assert [r.job_requirement_id for r in latest] == [compared.id]
    assert [g.requirement.id for g in gaps] == [compared.id]
    assert never_compared.comparison_results == []
    assert _count(session, ComparisonResult) == 1  # reading did not trigger a comparison


def test_a_gap_disappears_once_verified_but_the_history_stays(session: Session) -> None:
    """Why gaps are derived, not stored: a stored gap row would now be stale."""
    user = _user(session)
    python = skill_service.create_skill(session, "Python")
    user_skill = _claim(session, user, python)
    job = _job(session, user)
    requirement = _requirement(session, job, skill=python)

    comparison_service.compare_job_description(session, job)
    assert [g.requirement.id for g in comparison_service.skill_gaps(session, job)] == [requirement.id]

    evidence = _evidence(session, user, "FundsApp repo")
    _verify_legitimately(session, user_skill, [evidence], VerificationStatus.VERIFIED)
    comparison_service.compare_job_description(session, job)

    assert comparison_service.skill_gaps(session, job) == []
    [latest] = comparison_service.latest_results(session, job)
    assert latest.knowledge_status is VerificationStatus.VERIFIED
    history = session.scalars(
        select(ComparisonResult.knowledge_status)
        .where(ComparisonResult.job_requirement_id == requirement.id)
        .order_by(ComparisonResult.id)
    ).all()
    assert history == [VerificationStatus.PROVISIONAL, VerificationStatus.VERIFIED]


def test_skill_gaps_exclude_verified_and_include_the_three_other_statuses(
    session: Session,
) -> None:
    user = _user(session)
    verified = _held_skill(session, user, "Verified", VerificationStatus.VERIFIED)
    partial = _held_skill(session, user, "Partial", VerificationStatus.PARTIAL)
    provisional = _held_skill(session, user, "Provisional", VerificationStatus.PROVISIONAL)
    unheld = skill_service.create_skill(session, "Unheld")  # no UserSkill -> NOT_VERIFIED
    job = _job(session, user)
    for skill in (verified, partial, provisional, unheld):
        _requirement(session, job, skill=skill)
    comparison_service.compare_job_description(session, job)

    gaps = comparison_service.skill_gaps(session, job)

    assert {g.skill.name for g in gaps} == {"Partial", "Provisional", "Unheld"}
    assert {g.result.knowledge_status for g in gaps} == {
        VerificationStatus.PARTIAL,
        VerificationStatus.PROVISIONAL,
        VerificationStatus.NOT_VERIFIED,
    }


def test_an_unmapped_requirement_is_a_gap_with_skill_none(session: Session) -> None:
    user = _user(session)
    job = _job(session, user)
    requirement = _requirement(session, job, skill=None)
    comparison_service.compare_job_description(session, job)

    [gap] = comparison_service.skill_gaps(session, job)

    assert gap.requirement is requirement
    assert gap.skill is None
    assert gap.result.knowledge_status is VerificationStatus.NOT_VERIFIED


def test_gaps_are_ordered_required_first_then_by_requirement_id(session: Session) -> None:
    user = _user(session)
    verified = _held_skill(session, user, "Verified", VerificationStatus.VERIFIED)
    partial = _held_skill(session, user, "Partial", VerificationStatus.PARTIAL)
    provisional = _held_skill(session, user, "Provisional", VerificationStatus.PROVISIONAL)
    job = _job(session, user)
    # Creation order is scrambled relative to both gap status and required/optional.
    optional_unmapped = _requirement(session, job, skill=None, is_required=False)
    required_verified = _requirement(session, job, skill=verified, is_required=True)  # not a gap
    required_unmapped = _requirement(session, job, skill=None, is_required=True)
    optional_provisional = _requirement(session, job, skill=provisional, is_required=False)
    required_partial = _requirement(session, job, skill=partial, is_required=True)
    comparison_service.compare_job_description(session, job)

    gaps = comparison_service.skill_gaps(session, job)

    assert [g.requirement.id for g in gaps] == [
        required_unmapped.id,
        required_partial.id,
        optional_unmapped.id,
        optional_provisional.id,
    ]
    assert required_verified.id not in {g.requirement.id for g in gaps}


def test_is_required_affects_only_ordering_not_inclusion(session: Session) -> None:
    user = _user(session)
    verified = _held_skill(session, user, "Verified", VerificationStatus.VERIFIED)
    unheld = skill_service.create_skill(session, "Unheld")
    job = _job(session, user)
    optional_gap = _requirement(session, job, skill=unheld, is_required=False)
    required_gap = _requirement(session, job, skill=unheld, is_required=True)
    _requirement(session, job, skill=verified, is_required=True)
    _requirement(session, job, skill=verified, is_required=False)
    comparison_service.compare_job_description(session, job)

    gaps = comparison_service.skill_gaps(session, job)

    assert [g.requirement.id for g in gaps] == [required_gap.id, optional_gap.id]
    assert {g.result.knowledge_status for g in gaps} == {VerificationStatus.NOT_VERIFIED}


def test_results_and_gaps_are_scoped_to_the_given_job_description(session: Session) -> None:
    user = _user(session)
    python = skill_service.create_skill(session, "Python")
    _claim(session, user, python)
    first_job = _job(session, user)
    second_job = _job(session, user)
    first_requirement = _requirement(session, first_job, skill=python)
    second_requirements = [
        _requirement(session, second_job, skill=python),
        _requirement(session, second_job, skill=None),
    ]
    comparison_service.compare_job_description(session, first_job)
    comparison_service.compare_job_description(session, second_job)
    comparison_service.compare_job_description(session, first_job)  # re-run only the first

    first_latest = comparison_service.latest_results(session, first_job)
    second_latest = comparison_service.latest_results(session, second_job)

    assert [r.job_requirement_id for r in first_latest] == [first_requirement.id]
    assert [r.job_requirement_id for r in second_latest] == [r.id for r in second_requirements]
    assert [g.requirement.id for g in comparison_service.skill_gaps(session, first_job)] == [
        first_requirement.id
    ]
    assert {g.requirement.id for g in comparison_service.skill_gaps(session, second_job)} == {
        r.id for r in second_requirements
    }


def test_read_side_never_writes_or_triggers_a_comparison(session: Session) -> None:
    user = _user(session)
    verified = _held_skill(session, user, "Verified", VerificationStatus.VERIFIED)
    provisional = _held_skill(session, user, "Provisional", VerificationStatus.PROVISIONAL)
    job = _job(session, user)
    _requirement(session, job, skill=verified)
    _requirement(session, job, skill=provisional)
    comparison_service.compare_job_description(session, job)
    _requirement(session, job, skill=None)  # never compared: reading must not "fix" that

    def snapshot() -> tuple:
        user_skills = session.execute(
            select(UserSkill.id, UserSkill.status).order_by(UserSkill.id)
        ).all()
        return (
            _count(session, ComparisonResult),
            _count(session, ComparisonResultEvidence),
            _count(session, UserSkillEvidence),
            [tuple(row) for row in user_skills],
        )

    before = snapshot()
    for _ in range(2):
        comparison_service.latest_results(session, job)
        comparison_service.skill_gaps(session, job)

    assert snapshot() == before


def test_empty_job_description_has_no_results_and_no_gaps(session: Session) -> None:
    user = _user(session)
    job = _job(session, user)

    assert comparison_service.latest_results(session, job) == []
    assert comparison_service.skill_gaps(session, job) == []
