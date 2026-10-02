"""Domain exceptions raised by the service layer.

These are plain Python exceptions with no HTTP knowledge. The API layer is
responsible for translating them into responses.
"""


class DomainError(Exception):
    """Base class for every business-rule violation raised by a domain service."""


class EvidenceOwnershipError(DomainError):
    """Evidence belongs to a different user than the UserSkill it is being linked to."""

    def __init__(self, user_skill_id: int, evidence_id: int) -> None:
        super().__init__(
            f"Evidence {evidence_id} does not belong to the same user as UserSkill {user_skill_id}."
        )


class EvidenceAlreadyLinkedError(DomainError):
    """The evidence is already linked to this UserSkill."""

    def __init__(self, user_skill_id: int, evidence_id: int) -> None:
        super().__init__(
            f"Evidence {evidence_id} is already linked to UserSkill {user_skill_id}."
        )


class TooManyEvidenceSourcesError(DomainError):
    """After an edit, evidence would point at more than one source record."""

    def __init__(self) -> None:
        super().__init__(
            "Evidence can come from at most one source: a work experience, a project, or an "
            "education record. Clear the current source to pick a different one."
        )


class EvidenceNotLinkedError(DomainError):
    """The evidence isn't linked to this UserSkill, so there's nothing to unlink."""

    def __init__(self, user_skill_id: int, evidence_id: int) -> None:
        super().__init__(f"Evidence {evidence_id} is not linked to UserSkill {user_skill_id}.")


class LastEvidenceError(DomainError):
    """Unlinking would leave a VERIFIED/PARTIAL claim with no evidence at all."""

    def __init__(self, skill_name: str, status: str) -> None:
        super().__init__(
            f"This is the last piece of evidence for {skill_name}, which is {status}. "
            "A skill can't stay verified without proof, so change its status first, "
            "then unlink."
        )


class EvidenceInUseError(DomainError):
    """Evidence can't be deleted while a claim or comparison history depends on it."""

    def __init__(self, title: str, reasons: list[str]) -> None:
        super().__init__(f'"{title}" can\'t be deleted because it is {" and ".join(reasons)}.')


class ClaimInUseError(DomainError):
    """A claim can't be removed while past comparison results cite it (that's history)."""

    def __init__(self, skill_name: str, result_count: int, job_labels: list[str]) -> None:
        results = f"{result_count} past comparison result{'s' if result_count != 1 else ''}"
        jobs = ", ".join(f'"{label}"' for label in job_labels)
        super().__init__(
            f'Your claim on "{skill_name}" can\'t be removed because {results} '
            f"{'uses' if result_count == 1 else 'use'} it "
            f"(job{'s' if len(job_labels) != 1 else ''}: {jobs}). Delete "
            f"{'those jobs' if len(job_labels) != 1 else 'that job'} first, or keep the claim."
        )


class InsufficientEvidenceError(DomainError):
    """A status that requires supporting evidence was requested with none linked."""

    def __init__(self, user_skill_id: int, requested_status: str) -> None:
        super().__init__(
            f"UserSkill {user_skill_id} cannot be {requested_status}: "
            "no linked evidence. Not enough verified information."
        )


class EmptySkillTextError(DomainError):
    """A skill name or alias was blank or whitespace-only."""

    def __init__(self) -> None:
        super().__init__("Skill name or alias must not be blank.")


class SkillNameCollisionError(DomainError):
    """The text already belongs to an existing skill name or alias.

    Skill names and aliases share one namespace, so a new name or alias may not
    normalize to the same text as any existing one.
    """

    def __init__(self, text: str, existing_skill_name: str) -> None:
        super().__init__(
            f'"{text}" already belongs to the skill "{existing_skill_name}" '
            "(skill names and aliases share one namespace)."
        )


class EmptyProfileFieldError(DomainError):
    """A required profile field (project name, company, role, institution) was blank."""

    def __init__(self, field: str) -> None:
        super().__init__(f"{field} must not be blank.")


class InvalidDateRangeError(DomainError):
    """An end date falls before its start date."""

    def __init__(self) -> None:
        super().__init__("The end date can't be before the start date.")


class ProfileRecordInUseError(DomainError):
    """A project/work experience/education can't be removed while evidence cites it."""

    def __init__(self, label: str, count: int) -> None:
        pieces, come = ("piece", "comes") if count == 1 else ("pieces", "come")
        super().__init__(
            f"{label} can't be removed because {count} {pieces} of evidence {come} from it."
        )


class SkillInUseError(DomainError):
    """A skill can't be deleted because other records depend on it."""

    def __init__(self, skill_name: str, reasons: list[str]) -> None:
        super().__init__(
            f'"{skill_name}" can\'t be deleted because it is {", ".join(reasons)}.'
        )


class SkillMergeIntoItselfError(DomainError):
    """A skill can't be merged into itself."""

    def __init__(self, skill_name: str) -> None:
        super().__init__(f'"{skill_name}" can\'t be merged into itself; pick a different skill.')


class SkillMergeConflictError(DomainError):
    """Both skills hold a claim, and combining two claims is the user's call, not the app's."""

    def __init__(self, source_name: str, target_name: str) -> None:
        super().__init__(
            f'Both "{source_name}" and "{target_name}" are claimed, so they can\'t be merged: '
            "combining two claims (their status and evidence) would mean the app deciding "
            "which proof and status win, and that's your decision, not the app's. Remove the "
            "claim you don't want to keep (on its skill page), then merge."
        )


class DismissalNotFoundError(DomainError):
    """This job has no "not for this job" note for that skill."""

    def __init__(self, skill_id: int) -> None:
        super().__init__(f"Skill {skill_id} isn't removed from this job.")


class ImportFileError(DomainError):
    """A backup file isn't a valid Career AI export, or breaks one of the app's rules."""

    def __init__(self, problems: list[str]) -> None:
        self.problems = problems
        super().__init__("This backup can't be restored: " + " ".join(problems))


class AppNotEmptyError(DomainError):
    """Restoring is only allowed into an app with no skills and none of your data."""

    def __init__(self) -> None:
        super().__init__(
            "Restore only works on an empty app (no skills and none of your data yet), so "
            "nothing you already have is overwritten or merged by guesswork."
        )


class ApplicationDateError(DomainError):
    """An applied-on date that can't be right (in the future, or on a job not applied to)."""


class AliasNotFoundError(DomainError):
    """The skill has no alias matching this text."""

    def __init__(self, skill_name: str, alias: str) -> None:
        super().__init__(f'The skill "{skill_name}" has no alias "{alias.strip()}".')


class UnsupportedCVFileError(DomainError):
    """The CV file isn't a type we can read, or it's damaged."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)


class CVFileTooLargeError(DomainError):
    """The CV file or pasted text is over the size limit."""

    def __init__(self, limit_mb: int) -> None:
        super().__init__(f"The CV is too large. The limit is {limit_mb} MB.")


class NoCVTextError(DomainError):
    """No readable text could be found in the CV."""

    def __init__(self) -> None:
        super().__init__(
            "No readable text was found in this CV. If it's a scanned image, "
            "paste the text instead."
        )


class RequirementsAlreadyExistError(DomainError):
    """Extraction was refused because the job description already has requirements."""

    def __init__(self, job_description_id: int) -> None:
        super().__init__(
            f"Job description {job_description_id} already has requirements; "
            "extraction was not run again."
        )


class EmptyResourceTitleError(DomainError):
    """A learning resource's title was blank or whitespace-only."""

    def __init__(self) -> None:
        super().__init__("Learning resource title must not be blank.")


class InvalidResourceUrlError(DomainError):
    """A learning resource's URL isn't an http(s) link with a host."""

    def __init__(self, url: str) -> None:
        super().__init__(f'"{url}" is not a valid http or https link.')


class DuplicateLearningResourceError(DomainError):
    """The same URL is already saved for this skill under this learning mode."""

    def __init__(self, url: str) -> None:
        super().__init__(f'"{url}" is already saved for this skill in this learning mode.')


class AmbiguousSkillMatchError(DomainError):
    """The text matched more than one distinct Skill, so no single answer is safe."""

    def __init__(self, text: str, skill_names: list[str]) -> None:
        super().__init__(
            f'"{text}" is ambiguous: it matches multiple skills ({", ".join(sorted(skill_names))}). '
            "Fix the taxonomy so it maps to exactly one."
        )
