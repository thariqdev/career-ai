"""Start fresh with a new CV (stage 95): replace one person's career with another's.

Career AI holds ONE person. Uploading a second CV (say, a friend's) used to only ADD,
mixing two people's skills, proof and profile. This empties everything personal first,
then reads the new CV in:

- removed: the name, projects, work experience, education, evidence, skill claims (and
  their verification), CV marks, learning progress, job postings with their requirements,
  comparison history and removed-skill notes, and assistant ratings;
- kept: the skill dictionary (skills and nicknames) and saved study links, because those
  describe skills, not a person;
- then "Add all my CV skills" runs on the new CV (skills claimed PROVISIONAL, never
  verified; the name from its top), and the CV's projects, work and education are
  returned as DRAFTS for the user to review and save (nothing is guessed into the profile).

The caller downloads a backup first (the frontend does, via GET /export) and commits.
Same conventions as the other services: flush, never commit, so it's all or nothing.
"""

from dataclasses import dataclass, field

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.services import cv_adopt_service, cv_profile_service
from app.db.models import (
    AssistantFeedback,
    ComparisonResult,
    ComparisonResultEvidence,
    CVSkillPresence,
    DismissedRequirement,
    Education,
    Evidence,
    JobDescription,
    JobRequirement,
    LearningProgress,
    Project,
    User,
    UserSkill,
    UserSkillEvidence,
    WorkExperience,
)


@dataclass
class ReplaceResult:
    removed: dict[str, int] = field(default_factory=dict)  # what was removed, per kind
    adopted: cv_adopt_service.AdoptResult | None = None
    drafts: cv_profile_service.ProfileDrafts | None = None


def clear_person(db: Session, user: User) -> dict[str, int]:
    """Delete everything about this person, children first. Returns counts per kind."""
    job_ids = select(JobDescription.id).where(JobDescription.user_id == user.id)
    requirement_ids = select(JobRequirement.id).where(JobRequirement.job_description_id.in_(job_ids))
    result_ids = select(ComparisonResult.id).where(ComparisonResult.job_requirement_id.in_(requirement_ids))
    claim_ids = select(UserSkill.id).where(UserSkill.user_id == user.id)

    def count(model, *where) -> int:
        return len(db.scalars(select(model).where(*where)).all())

    removed = {
        "jobs": count(JobDescription, JobDescription.user_id == user.id),
        "skill_claims": count(UserSkill, UserSkill.user_id == user.id),
        "evidence": count(Evidence, Evidence.user_id == user.id),
        "projects": count(Project, Project.user_id == user.id),
        "work_experiences": count(WorkExperience, WorkExperience.user_id == user.id),
        "educations": count(Education, Education.user_id == user.id),
    }
    statements = [
        delete(ComparisonResultEvidence).where(ComparisonResultEvidence.comparison_result_id.in_(result_ids)),
        delete(ComparisonResult).where(ComparisonResult.id.in_(result_ids)),
        delete(DismissedRequirement).where(DismissedRequirement.job_description_id.in_(job_ids)),
        delete(JobRequirement).where(JobRequirement.id.in_(requirement_ids)),
        delete(JobDescription).where(JobDescription.user_id == user.id),
        delete(UserSkillEvidence).where(UserSkillEvidence.user_skill_id.in_(claim_ids)),
        delete(UserSkill).where(UserSkill.user_id == user.id),
        delete(CVSkillPresence).where(CVSkillPresence.user_id == user.id),
        delete(LearningProgress).where(LearningProgress.user_id == user.id),
        delete(Evidence).where(Evidence.user_id == user.id),
        delete(Project).where(Project.user_id == user.id),
        delete(WorkExperience).where(WorkExperience.user_id == user.id),
        delete(Education).where(Education.user_id == user.id),
        delete(AssistantFeedback).where(AssistantFeedback.user_id == user.id),
    ]
    for statement in statements:
        db.execute(statement.execution_options(synchronize_session=False))
    user.full_name = None
    db.flush()
    db.expire_all()  # relationships loaded before the bulk deletes must not be reused
    return removed


def replace_with_cv(db: Session, user: User, text: str) -> ReplaceResult:
    removed = clear_person(db, user)
    adopted = cv_adopt_service.add_all_from_cv(db, user, text)
    drafts = cv_profile_service.read_drafts(db, user, text)
    return ReplaceResult(removed=removed, adopted=adopted, drafts=drafts)
