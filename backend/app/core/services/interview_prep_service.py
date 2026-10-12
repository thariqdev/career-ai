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

from app.core.services import learning_service, match_service
from app.core.services.skill_service import normalize_text
from app.core.skill_catalog import CATALOG
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
    key: str  # stable: "req-<id>" for a saved requirement, else "skill-<id>" / "text-<name>"
    requirement_id: int | None  # None: the skill was found in the posting, not saved
    text: str  # what to show: the saved requirement's own words, else the skill's name
    is_required: bool
    skill_id: int | None
    skill_name: str | None  # None only for UNMAPPED text
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
    """One item per skill the job asks for, required first, then in posting order.

    Since stage 87 the list of skills is the MATCH's (match_service.job_match): skills the
    posting mentions, the saved requirements, and common catalogue skills it names. So the
    sheet and the match percentage can never disagree, and a job with no saved requirements
    still gets a sheet. Each item keeps its saved requirement's id and wording when there is one.
    """
    db.flush()

    match = match_service.job_match(db, user, job_description)
    requirements = list(
        db.scalars(select(JobRequirement).where(JobRequirement.job_description_id == job_description.id))
    )
    by_skill = {r.skill_id: r for r in requirements if r.skill_id is not None}
    by_text = {normalize_text(r.requirement_text): r for r in requirements if r.skill_id is None}
    catalogue = {s.name.lower(): s.name for s in CATALOG}

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

    def study(name: str) -> list[StudyLink]:
        return [
            StudyLink(mode=mode.value, query=learning_service.search_query(name, mode),
                      url=learning_service.youtube_search_url(name, mode))
            for mode in LearningMode
        ]

    items = []
    for asked in sorted(match.asked, key=lambda i: not i.is_required):  # stable: posting order
        if asked.skill_id is None:
            requirement = by_text.get(normalize_text(asked.name))
            key = f"req-{requirement.id}" if requirement else f"text-{normalize_text(asked.name)}"
            known = catalogue.get(asked.name.lower())
            if known is None:  # requirement text matching no skill: nothing to say about it
                items.append(PrepItem(key, requirement.id if requirement else None, asked.name, asked.is_required,
                                      None, None, UNMAPPED, _GUIDANCE[UNMAPPED], None, [], []))
                continue
            # A common skill the posting names that you haven't saved: you haven't claimed it.
            items.append(PrepItem(key, requirement.id if requirement else None, asked.name, asked.is_required,
                                  None, known, NO_CLAIM, _GUIDANCE[NO_CLAIM].format(skill=known), None, [],
                                  study(known)))
            continue

        requirement = by_skill.get(asked.skill_id)
        claim = claims.get(asked.skill_id)
        status = claim.status.value if claim is not None else NO_CLAIM
        linked = evidence_by_claim.get(claim.id, []) if claim is not None else []
        proven = claim is not None and claim.status in _PROVEN
        items.append(
            PrepItem(
                key=f"req-{requirement.id}" if requirement else f"skill-{asked.skill_id}",
                requirement_id=requirement.id if requirement else None,
                text=requirement.requirement_text if requirement else asked.name,
                is_required=asked.is_required,
                skill_id=asked.skill_id,
                skill_name=asked.name,
                status=status,
                guidance=_GUIDANCE[status].format(skill=asked.name),
                cv_warning=(
                    _CV_WARNING.format(skill=asked.name)
                    if asked.skill_id in on_cv and not proven
                    else None
                ),
                evidence=[PrepEvidence(e.id, e.title, e.url, _source(e)) for e in linked],
                study_links=study(asked.name),
            )
        )
    return items
