"""An interview prep sheet for one job: what the user can honestly say about each requirement.

READ-ONLY and deterministic. Every sentence is a fixed template filled only with the
user's own stored data (claims, linked evidence and its source, CV presence). Nothing is
generated or guessed: if a skill isn't proven, the sheet says so instead of coaching a
bluff (PROJECT_RULES.md: never invent experience or proficiency).

It uses the user's CURRENT claim status and evidence, not the job's last
ComparisonResult snapshot, so proving a skill shows up here immediately.

Same conventions as the other services: plain functions taking a Session, no HTTP
knowledge, flush before reading (autoflush=False), no writes.
"""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.services import learning_service
from app.db.models import (
    CVSkillPresence,
    Evidence,
    JobDescription,
    JobRequirement,
    User,
    UserSkill,
    UserSkillEvidence,
)
from app.db.models.enums import LearningMode, VerificationStatus

NO_CLAIM = "no_claim"
UNMAPPED = "unmapped"

_PROVEN = {VerificationStatus.VERIFIED, VerificationStatus.PARTIAL}

_GUIDANCE = {
    VerificationStatus.VERIFIED.value: (
        "You can claim {skill}. Back it up with your evidence below, and be ready to "
        "walk through it in detail."
    ),
    VerificationStatus.PARTIAL.value: (
        "You have some proof for {skill}. Be honest about how deep your experience goes, "
        "and review the basics before the interview."
    ),
    VerificationStatus.PROVISIONAL.value: (
        "You've claimed {skill} but haven't proven it yet. Don't overstate it: say you're "
        "learning it, and study it before the interview."
    ),
    VerificationStatus.NOT_VERIFIED.value: (
        "Your claim on {skill} isn't backed by evidence. Don't claim experience with it: "
        "say you're learning it."
    ),
    NO_CLAIM: (
        "You haven't claimed {skill}. Don't claim experience with it. If it comes up, say "
        "it's something you're keen to learn."
    ),
    UNMAPPED: (
        "This requirement isn't linked to a skill in your list, so the app has nothing to "
        "tell you about it. Read it carefully and decide what you can honestly say."
    ),
}

_CV_WARNING = "{skill} is on your CV, so expect to be asked about it."


@dataclass(frozen=True)
class PrepEvidence:
    id: int
    title: str
    url: str | None
    source: str | None  # e.g. "project FundsApp", "Engineer at Acme"


@dataclass(frozen=True)
class StudyLink:
    mode: str
    query: str
    url: str


@dataclass(frozen=True)
class PrepItem:
    requirement: JobRequirement
    status: str  # a VerificationStatus value, NO_CLAIM, or UNMAPPED
    guidance: str
    cv_warning: str | None
    evidence: list[PrepEvidence]
    study_links: list[StudyLink]


def _source(evidence: Evidence) -> str | None:
    if evidence.project is not None:
        return f"project {evidence.project.name}"
    if evidence.work_experience is not None:
        return f"{evidence.work_experience.role} at {evidence.work_experience.company}"
    if evidence.education is not None:
        e = evidence.education
        return f"{e.degree}, {e.institution}" if e.degree else e.institution
    return None


def interview_prep(db: Session, user: User, job_description: JobDescription) -> list[PrepItem]:
    """One item per requirement: required ones first, then by requirement id."""
    db.flush()

    requirements = list(
        db.scalars(
            select(JobRequirement)
            .where(JobRequirement.job_description_id == job_description.id)
            .order_by(JobRequirement.is_required.desc(), JobRequirement.id)
        )
    )
    claims = {c.skill_id: c for c in db.scalars(select(UserSkill).where(UserSkill.user_id == user.id))}
    on_cv = set(
        db.scalars(
            select(CVSkillPresence.skill_id).where(
                CVSkillPresence.user_id == user.id, CVSkillPresence.present.is_(True)
            )
        )
    )
    evidence_by_claim: dict[int, list[Evidence]] = {}
    if claims:
        rows = db.execute(
            select(UserSkillEvidence.user_skill_id, Evidence)
            .join(Evidence, UserSkillEvidence.evidence_id == Evidence.id)
            .where(UserSkillEvidence.user_skill_id.in_([c.id for c in claims.values()]))
            .order_by(Evidence.id)
        )
        for claim_id, evidence in rows:
            evidence_by_claim.setdefault(claim_id, []).append(evidence)

    items = []
    for requirement in requirements:
        if requirement.skill is None:
            items.append(
                PrepItem(requirement, UNMAPPED, _GUIDANCE[UNMAPPED], None, [], [])
            )
            continue

        skill = requirement.skill
        claim = claims.get(skill.id)
        status = claim.status.value if claim is not None else NO_CLAIM
        linked = evidence_by_claim.get(claim.id, []) if claim is not None else []
        proven = claim is not None and claim.status in _PROVEN
        items.append(
            PrepItem(
                requirement=requirement,
                status=status,
                guidance=_GUIDANCE[status].format(skill=skill.name),
                cv_warning=(
                    _CV_WARNING.format(skill=skill.name)
                    if skill.id in on_cv and not proven
                    else None
                ),
                evidence=[PrepEvidence(e.id, e.title, e.url, _source(e)) for e in linked],
                study_links=[
                    StudyLink(
                        mode=mode.value,
                        query=learning_service.search_query(skill.name, mode),
                        url=learning_service.youtube_search_url(skill.name, mode),
                    )
                    for mode in LearningMode
                ],
            )
        )
    return items
