from app.db.models.skill import Skill
from app.db.models.skill_alias import SkillAlias
from app.db.models.user import User
from app.db.models.project import Project
from app.db.models.work_experience import WorkExperience
from app.db.models.education import Education
from app.db.models.evidence import Evidence
from app.db.models.user_skill import UserSkill, UserSkillEvidence
from app.db.models.job_description import JobDescription
from app.db.models.job_requirement import JobRequirement
from app.db.models.comparison_result import ComparisonResult, ComparisonResultEvidence
from app.db.models.cv_skill_presence import CVSkillPresence
from app.db.models.learning_resource import LearningResource

__all__ = [
    "Skill",
    "SkillAlias",
    "User",
    "Project",
    "WorkExperience",
    "Education",
    "Evidence",
    "UserSkill",
    "UserSkillEvidence",
    "JobDescription",
    "JobRequirement",
    "ComparisonResult",
    "ComparisonResultEvidence",
    "CVSkillPresence",
    "LearningResource",
]
