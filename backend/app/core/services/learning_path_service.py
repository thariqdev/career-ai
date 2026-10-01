"""A four-step learning path per skill, with exactly one "current" step.

READ-ONLY and deterministic: fixed wording, and every step's "done" comes from a fact the
user recorded. Studying never counts as proof (PROJECT_RULES.md section 14):

1. start  - done when LearningProgress is STUDYING or FINISHED
2. finish - done when LearningProgress is FINISHED
3. prove  - done when the user's claim has at least one linked Evidence
4. verify - done when the claim's status is VERIFIED (PARTIAL is proof, not verification)

A step's state is "done", else "current" for the first step not done, else "todo".
Steps can be done out of order (e.g. evidence linked before studying); the current step
is still the first one not done.

Works for several skills at once with a fixed number of queries, so a caller with many
skills (the Dashboard) doesn't need one request per skill.

Same conventions as the other services: plain functions taking a Session, no HTTP
knowledge, flush before reading (autoflush=False), no writes.
"""

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.services import learning_service
from app.db.models import LearningProgress, LearningResource, Skill, User, UserSkill, UserSkillEvidence
from app.db.models.enums import LearningMode, LearningStatus, VerificationStatus

DONE, CURRENT, TODO = "done", "current", "todo"


@dataclass(frozen=True)
class PathLink:
    label: str
    url: str


@dataclass(frozen=True)
class PathStep:
    key: str
    title: str
    detail: str
    state: str
    links: list[PathLink]


@dataclass(frozen=True)
class LearningPath:
    skill: Skill
    steps: list[PathStep]

    @property
    def next_step(self) -> str | None:
        """Title of the current step, or None when every step is done."""
        return next((s.title for s in self.steps if s.state == CURRENT), None)


def _search(skill: Skill, mode: LearningMode, label: str) -> PathLink:
    return PathLink(label, learning_service.youtube_search_url(skill.name, mode))


def learning_paths(db: Session, user: User, skills: list[Skill]) -> list[LearningPath]:
    """One path per skill, in the order given."""
    db.flush()
    if not skills:
        return []
    ids = [s.id for s in skills]

    progress = dict(
        db.execute(
            select(LearningProgress.skill_id, LearningProgress.status).where(
                LearningProgress.user_id == user.id, LearningProgress.skill_id.in_(ids)
            )
        ).all()
    )
    claims = {
        c.skill_id: c
        for c in db.scalars(
            select(UserSkill).where(UserSkill.user_id == user.id, UserSkill.skill_id.in_(ids))
        )
    }
    evidence_counts = dict(
        db.execute(
            select(UserSkillEvidence.user_skill_id, func.count())
            .where(UserSkillEvidence.user_skill_id.in_([c.id for c in claims.values()] or [-1]))
            .group_by(UserSkillEvidence.user_skill_id)
        ).all()
    )
    saved: dict[int, list[PathLink]] = {}
    for resource in db.scalars(
        select(LearningResource)
        .where(LearningResource.skill_id.in_(ids))
        .order_by(LearningResource.created_at, LearningResource.id)
    ):
        saved.setdefault(resource.skill_id, []).append(PathLink(resource.title, resource.url))

    paths = []
    for skill in skills:
        status = progress.get(skill.id)
        claim = claims.get(skill.id)
        has_evidence = claim is not None and evidence_counts.get(claim.id, 0) > 0
        steps = [
            (
                "start",
                "Start learning",
                f"Begin with the basics of {skill.name}, then follow a hands-on tutorial. "
                "Mark it as Studying when you start.",
                status in (LearningStatus.STUDYING, LearningStatus.FINISHED),
                [
                    _search(skill, LearningMode.THEORY_INTERVIEW, "Theory on YouTube"),
                    _search(skill, LearningMode.TECHNICAL_PRACTICAL, "Hands-on course on YouTube"),
                    *saved.get(skill.id, []),
                ],
            ),
            (
                "finish",
                "Finish learning",
                "When you've worked through it, mark it as Finished studying.",
                status == LearningStatus.FINISHED,
                [],
            ),
            (
                "prove",
                "Prove it",
                f"Build something small with {skill.name} (a project, an exercise, a "
                "certificate) and link it as evidence. Finishing a course isn't proof on its own.",
                has_evidence,
                [],
            ),
            (
                "verify",
                "Get verified, then practise interview questions",
                "With evidence linked, set the skill to Verified (or Partial if your proof is "
                "limited). Then practise common interview questions.",
                claim is not None and claim.status == VerificationStatus.VERIFIED,
                [_search(skill, LearningMode.THEORY_INTERVIEW, "Interview questions on YouTube")],
            ),
        ]
        first_open = next((i for i, step in enumerate(steps) if not step[3]), None)
        paths.append(
            LearningPath(
                skill=skill,
                steps=[
                    PathStep(
                        key=key,
                        title=title,
                        detail=detail,
                        state=DONE if done else (CURRENT if i == first_open else TODO),
                        links=links,
                    )
                    for i, (key, title, detail, done, links) in enumerate(steps)
                ],
            )
        )
    return paths
