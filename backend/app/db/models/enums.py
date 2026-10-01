import enum


class EvidenceType(str, enum.Enum):
    """The kinds of concrete, reviewable proof PROJECT_RULES.md section 4.1 accepts.

    Self-assessment is deliberately NOT a member here: per section 4.2, self-reported
    knowledge can never become Evidence, only a PROVISIONAL/PARTIAL claim recorded
    elsewhere (on UserSkill, added in the next batch). Leaving it out of this enum
    enforces that rule at the schema level rather than relying on service code alone.
    """

    WORK_EXPERIENCE = "work_experience"
    PROJECT = "project"
    CERTIFICATION = "certification"
    ARTIFACT = "artifact"
    OTHER = "other"


class LearningMode(str, enum.Enum):
    """The two learning modes PROJECT_RULES.md section 14 defines."""

    THEORY_INTERVIEW = "theory_interview"
    TECHNICAL_PRACTICAL = "technical_practical"


class LearningStatus(str, enum.Enum):
    """How far the user says they are in studying a skill (PROJECT_RULES.md section 16).

    "Not started" is deliberately not a member: it is represented by having no
    LearningProgress row at all, so there is only one way to say it.
    """

    STUDYING = "studying"
    FINISHED = "finished"


class VerificationStatus(str, enum.Enum):
    """The four statuses PROJECT_RULES.md section 3 defines for a UserSkill claim.

    Per section 12, a UserSkill starts life as PROVISIONAL. Only the (not-yet-built)
    verification_service can promote it to VERIFIED/PARTIAL, and only once at least
    one Evidence record is linked to it via UserSkillEvidence.
    """

    VERIFIED = "verified"
    PARTIAL = "partial"
    PROVISIONAL = "provisional"
    NOT_VERIFIED = "not_verified"
