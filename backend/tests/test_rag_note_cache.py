"""Stage 82: cached notes must NEVER be stale. Every kind of data the notes read is edited
here, and the very next notes must show the change."""

from collections.abc import Callable, Iterator

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.models import (
    CVSkillPresence,
    DismissedRequirement,
    Education,
    Evidence,
    JobDescription,
    JobRequirement,
    LearningProgress,
    Project,
    Skill,
    SkillAlias,
    User,
    UserSkill,
    UserSkillEvidence,
    WorkExperience,
)
from app.db.models.enums import ApplicationStatus, LearningStatus, VerificationStatus
from app.rag import note_cache
from app.rag.chunker import build_chunks
from app.rag.evaluate import fill_fixture
from database import Base


@pytest.fixture()
def db() -> Iterator[tuple[Session, User]]:
    note_cache.clear()
    engine = create_engine("sqlite://", poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine, autoflush=False) as session:
        yield session, fill_fixture(session)
    engine.dispose()
    note_cache.clear()


def _text(db: Session, user: User) -> str:
    return "\n".join(f"{c.title} | {c.text}" for c in note_cache.notes(db, user))


def _skill(db: Session, name: str) -> Skill:
    return db.scalar(select(Skill).where(Skill.name == name))


def _claim(db: Session, user: User, name: str) -> UserSkill:
    return db.scalar(select(UserSkill).where(UserSkill.user_id == user.id, UserSkill.skill_id == _skill(db, name).id))


def _job(db: Session, title: str) -> JobDescription:
    return db.scalar(select(JobDescription).where(JobDescription.title == title))


def rename_skill(db, user):
    _skill(db, "Docker").name = "Docker Engine"
    return "Skill: Docker Engine"


def add_alias(db, user):
    db.add(SkillAlias(skill_id=_skill(db, "React").id, alias="ReactJS"))
    return "Also written as: ReactJS"


def change_claim(db, user):
    _claim(db, user, "Git").status = VerificationStatus.NOT_VERIFIED
    return "Skill: Git (Tools). Your status: not verified, no proof"


def link_proof(db, user):
    evidence = db.scalar(select(Evidence).where(Evidence.title == "FundsApp repo"))
    db.add(UserSkillEvidence(user_skill_id=_claim(db, user, "PostgreSQL").id, evidence_id=evidence.id))
    return "It proves these skills: Python (verified), PostgreSQL (provisional)"


def unmark_cv(db, user):
    db.scalar(select(CVSkillPresence).where(CVSkillPresence.skill_id == _skill(db, "Git").id)).present = False
    return "Skill: Git (Tools). Your status: provisional: claimed but not proven yet, no proof or evidence linked. On your CV: no"


def learning(db, user):
    db.scalar(select(LearningProgress).where(LearningProgress.user_id == user.id)).status = LearningStatus.FINISHED
    return "Learning progress: finished studying it"


def application(db, user):
    _job(db, "Backend Engineer").application_status = ApplicationStatus.APPLIED
    return "Application status: applied"


def requirement(db, user):
    db.add(JobRequirement(job_description_id=_job(db, "Frontend Developer").id, requirement_text="Git",
                          skill_id=_skill(db, "Git").id, is_required=True))
    return "Git (Tools). Your status: provisional: claimed but not proven yet, no proof or evidence linked. On your CV: yes. Learning progress: not started learning. Jobs that need it: Frontend Developer at Globex"


def dismissal(db, user):
    db.add(DismissedRequirement(job_description_id=_job(db, "Backend Engineer").id, skill_id=_skill(db, "PostgreSQL").id))
    return "Match: 33%, you have 1 of 3 skills"


def evidence(db, user):
    db.scalar(select(Evidence).where(Evidence.title == "FundsApp repo")).title = "FundsApp source code"
    return "Evidence (proof): FundsApp source code"


def project(db, user):
    db.scalar(select(Project).where(Project.name == "FundsApp")).description = "Now with a mobile app."
    return "About it: Now with a mobile app."


def work(db, user):
    db.scalar(select(WorkExperience)).role = "Backend Developer"
    return "Work experience: Backend Developer at Initech"


def education(db, user):
    db.scalar(select(Education)).degree = "MCA"
    return "Education: MCA at Chinmaya College"


def name(db, user):
    user.full_name = "Jane Doe"
    return "Your name is Jane Doe."


CHANGES: list[Callable] = [
    rename_skill, add_alias, change_claim, link_proof, unmark_cv, learning, application,
    requirement, dismissal, evidence, project, work, education, name,
]


@pytest.mark.parametrize("change", CHANGES, ids=[c.__name__ for c in CHANGES])
def test_every_kind_of_change_is_seen_by_the_very_next_notes(db, change) -> None:
    session, user = db
    before = _text(session, user)

    expected = change(session, user)
    session.flush()
    session.expire_all()  # like the app: each question gets a fresh view of the data
    after = _text(session, user)

    assert expected not in before, "the test's edit must actually change something"
    assert expected in after
    assert after == "\n".join(f"{c.title} | {c.text}" for c in build_chunks(session, user))  # same as uncached


def test_unchanged_data_is_served_from_the_cache(db) -> None:
    session, user = db
    note_cache.stats.update(hits=0, rebuilds=0)

    first = note_cache.notes(session, user)
    second = note_cache.notes(session, user)

    assert second is first
    assert note_cache.stats == {"hits": 1, "rebuilds": 1}


def test_a_rating_doesnt_force_a_rebuild(db) -> None:
    from app.db.models import AssistantFeedback

    session, user = db
    first = note_cache.notes(session, user)
    session.add(AssistantFeedback(user_id=user.id, message_id="m", rating="up", question="q", answer="a", sources=[]))
    session.flush()

    assert note_cache.notes(session, user) is first


def test_if_the_fingerprint_fails_the_notes_are_rebuilt(db, monkeypatch: pytest.MonkeyPatch) -> None:
    session, user = db

    def broken(_db):
        raise RuntimeError("database hiccup")

    monkeypatch.setattr(note_cache, "fingerprint", broken)

    assert [c.id for c in note_cache.notes(session, user)] == [c.id for c in build_chunks(session, user)]


def test_the_sanitizer_switches_are_part_of_the_key(db, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.rag import sanitize

    session, user = db
    key = note_cache.fingerprint(session)
    monkeypatch.setattr(sanitize, "NEUTRAL_LABELS", not sanitize.NEUTRAL_LABELS)

    assert note_cache.fingerprint(session) != key
