"""Read a CV's text into DRAFT profile entries (projects, work experience, education).

Read-only: nothing is saved here. The user reviews and edits every draft, and saving
goes through the normal profile endpoints and their rules (profile_service), exactly
like typing it by hand.

No AI and no guessing. Every text field in a draft is copied from the CV (whole lines,
or parts of a line split at separators like "|", " at ", ","), so a draft can be wrong
about WHICH box a phrase belongs in, but never contains words the CV doesn't. A field
the rules can't find stays empty rather than being filled in.

How it reads, in order:
1. Sections: a short line that is a known heading ("Experience", "EDUCATION:",
   "Personal Projects", ...) starts a section; other known headings ("Skills",
   "Certifications", ...) end one.
2. Entries: inside a section, each line with a date range ("Jan 2022 - Present",
   "2019 - 2023", "03/2021 to 06/2022") anchors one entry. Its header is the text on that
   line around the dates, plus up to two short non-bullet lines just above it. Bullet
   lines and long lines below are its description. A section with no date ranges at
   all (common for projects) is split at each title-like line instead (6 words or
   fewer, no full stop, not just a link).
3. Fields: the header is split into parts, then keywords decide which part is a role
   ("Engineer", "Intern"...), a degree ("B.Tech", "Bachelor"...) or a school
   ("University", "College"...).

Dates: a CV gives months or years, but profile dates are full dates, so "Mar 2022"
becomes 2022-03-01 and "2019" becomes 2019-01-01 (always the first day of the period;
the CV's own wording is kept in `dates_text` for the review screen). "Present",
"Current" and similar mean no end date.
"""

import re
from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.services.skill_service import normalize_text
from app.db.models import Education, Project, User, WorkExperience

# --- headings -------------------------------------------------------------------------

_HEADINGS = {
    "work": {
        "experience", "work experience", "professional experience", "employment",
        "employment history", "work history", "career history", "relevant experience",
        "internships", "internship", "internship experience", "experience and internships",
    },
    "education": {
        "education", "academic background", "academics", "education and training",
        "qualifications", "academic qualifications", "educational qualifications",
    },
    "projects": {
        "projects", "personal projects", "academic projects", "key projects",
        "selected projects", "project experience", "side projects", "project work",
    },
    "other": {
        "skills", "technical skills", "key skills", "core skills", "certifications",
        "certificates", "awards", "achievements", "honors", "honours", "summary",
        "professional summary", "profile", "objective", "career objective", "languages",
        "interests", "hobbies", "references", "contact", "contact information",
        "publications", "activities", "extracurricular activities", "volunteering",
        "volunteer experience", "courses", "coursework", "relevant coursework",
        "declaration", "personal details", "strengths", "tools", "technologies",
    },
}


def _heading_kind(line: str) -> str | None:
    key = normalize_text(line).strip(":- ")
    if len(key.split()) > 4:
        return None
    for kind, names in _HEADINGS.items():
        if key in names:
            return kind
    return None


# --- dates ----------------------------------------------------------------------------

_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}
_MONTH = r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|sept?(?:ember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\.?"
_DATE = rf"(?:{_MONTH}\s*,?\s*(?:19|20)\d{{2}}|\d{{1,2}}\s*[/.-]\s*(?:19|20)\d{{2}}|(?:19|20)\d{{2}})"
_OPEN_END = r"(?:present|current|now|ongoing|till\s+date|to\s+date|today)"
_RANGE = re.compile(
    rf"(?P<start>{_DATE})\s*(?:-|–|—|to|until|till)\s*(?P<end>{_DATE}|{_OPEN_END})",
    re.IGNORECASE,
)


_TRAILING_DATE = re.compile(rf"\s*\(?\s*{_DATE}\s*\)?\s*$", re.IGNORECASE)


def parse_date(text: str) -> date | None:
    """'Mar 2022' -> 2022-03-01, '03/2022' -> 2022-03-01, '2019' -> 2019-01-01."""
    text = text.strip().lower()
    numeric = re.fullmatch(r"(\d{1,2})\s*[/.-]\s*((?:19|20)\d{2})", text)
    if numeric:
        month, year = int(numeric.group(1)), int(numeric.group(2))
        return date(year, month, 1) if 1 <= month <= 12 else None
    named = re.fullmatch(rf"({_MONTH})\s*,?\s*((?:19|20)\d{{2}})", text)
    if named:
        return date(int(named.group(2)), _MONTHS[named.group(1)[:3]], 1)
    year = re.fullmatch(r"(?:19|20)\d{2}", text)
    return date(int(text), 1, 1) if year else None


# --- lines ----------------------------------------------------------------------------

_BULLET = re.compile(r"^\s*(?:[•●▪◦‣∙·*\-–—]|\d{1,2}[.)])\s+")
_SPLIT = re.compile(r"\s*(?:\||•|·|–|—|\s-\s|,|\bat\b|@)\s*", re.IGNORECASE)
_URL = re.compile(r"https?://[^\s,;|)]+", re.IGNORECASE)
_SHORT_WORDS = 12


@dataclass
class _Line:
    text: str
    bullet: bool


def _lines(text: str) -> list[_Line]:
    lines = []
    for raw in text.replace("\r", "\n").split("\n"):
        if not raw.strip():
            continue
        bullet = bool(_BULLET.match(raw))
        clean = _BULLET.sub("", raw, count=1).strip() if bullet else raw.strip()
        if clean:
            lines.append(_Line(" ".join(clean.split()), bullet))
    return lines


def _sections(lines: list[_Line]) -> dict[str, list[_Line]]:
    sections: dict[str, list[_Line]] = {"work": [], "education": [], "projects": []}
    current: str | None = None
    for line in lines:
        kind = None if line.bullet else _heading_kind(line.text)
        if kind is not None:
            current = kind if kind in sections else None
            continue
        if current is not None:
            sections[current].append(line)
    return sections


# --- entries --------------------------------------------------------------------------


@dataclass
class _Entry:
    header: list[str] = field(default_factory=list)
    description: list[str] = field(default_factory=list)
    start: date | None = None
    end: date | None = None
    dates_text: str | None = None
    open_ended: bool = False


def _is_header_like(line: _Line) -> bool:
    return not line.bullet and len(line.text.split()) <= _SHORT_WORDS


def _is_title_like(line: _Line) -> bool:
    """Starts an entry when a section has no dates: short, no full stop, not just a link."""
    text = line.text
    return (
        not line.bullet
        and len(text.split()) <= 6
        and not text.endswith(".")
        and _URL.sub("", text).strip(" |,–—-:()") != ""
    )


def _entries(section: list[_Line]) -> list[_Entry]:
    anchors = [i for i, line in enumerate(section) if _RANGE.search(line.text)]
    entries: list[_Entry] = []
    if anchors:
        claimed = 0  # lines before this index belong to an earlier entry
        for n, i in enumerate(anchors):
            match = _RANGE.search(section[i].text)
            entry = _Entry(dates_text=match.group(0))
            entry.start = parse_date(match.group("start"))
            end_text = match.group("end")
            entry.open_ended = re.fullmatch(_OPEN_END, end_text, re.IGNORECASE) is not None
            entry.end = None if entry.open_ended else parse_date(end_text)

            # Header lines just above the anchor (at most 2, not already claimed).
            above = []
            j = i - 1
            while j >= claimed and len(above) < 2 and _is_header_like(section[j]):
                above.insert(0, section[j].text)
                j -= 1
            # Lines between the previous entry's anchor and these header lines are that
            # entry's description.
            if entries:
                entries[-1].description.extend(l.text for l in section[claimed:j + 1])
            entry.header = above
            rest = (section[i].text[: match.start()] + " " + section[i].text[match.end():]).strip(" |,–—-:()")
            if rest:
                entry.header.append(rest)
            entries.append(entry)
            claimed = i + 1
            if n == len(anchors) - 1:
                entry.description.extend(l.text for l in section[claimed:])
        return entries

    # No dates anywhere: each title-like line starts an entry; everything else (sentences,
    # bullets, a bare link) is the current entry's description.
    for line in section:
        if _is_title_like(line):
            entries.append(_Entry(header=[line.text]))
        elif entries:
            entries[-1].description.append(line.text)
    return entries


def _parts(header: list[str]) -> list[str]:
    parts: list[str] = []
    for line in header:
        for part in _SPLIT.split(_URL.sub(" ", line)):
            part = part.strip(" |,–—-:()")
            if part and part not in parts:
                parts.append(part)
    return parts


_ROLE_WORDS = re.compile(
    r"\b(engineer|developer|intern|internship|analyst|manager|lead|consultant|designer|architect|"
    r"scientist|specialist|administrator|associate|assistant|officer|director|head|coordinator|"
    r"tester|programmer|trainee|executive|technician|founder|co-founder|freelancer|researcher|"
    r"teacher|tutor|instructor|representative|member)\b",
    re.IGNORECASE,
)
_DEGREE_WORDS = re.compile(
    r"(\bbachelor|\bmaster|\bb\.?\s?tech\b|\bm\.?\s?tech\b|\bb\.?\s?e\.(?=\s|$)|\bb\.?\s?sc\b|\bm\.?\s?sc\b|"
    r"\bmba\b|\bbba\b|\bbca\b|\bmca\b|\bph\.?\s?d\b|\bdiploma\b|\bb\.?\s?a\.(?=\s|$)|\bm\.?\s?a\.(?=\s|$)|"
    r"\bb\.?\s?com\b|\bm\.?\s?com\b|\bhigh school\b|\bhigher secondary\b|\bsecondary\b|\bhsc\b|\bssc\b|"
    r"\bcbse\b|\bclass (?:x|xii|10|12)\b|\bcertificate\b|\bassociate degree\b|\bdegree\b)",
    re.IGNORECASE,
)
_SCHOOL_WORDS = re.compile(
    r"\b(university|college|institute|institution|school|academy|polytechnic|iit|nit|iiit)\b",
    re.IGNORECASE,
)


def _description(lines: list[str]) -> str | None:
    text = "\n".join(lines).strip()
    return text or None


# --- drafts ---------------------------------------------------------------------------


@dataclass(frozen=True)
class WorkDraft:
    company: str | None
    role: str | None
    start_date: date | None
    end_date: date | None
    dates_text: str | None
    description: str | None
    duplicate: bool


@dataclass(frozen=True)
class EducationDraft:
    institution: str | None
    degree: str | None
    field_of_study: str | None
    start_date: date | None
    end_date: date | None
    dates_text: str | None
    description: str | None
    duplicate: bool


@dataclass(frozen=True)
class ProjectDraft:
    name: str | None
    url: str | None
    start_date: date | None
    end_date: date | None
    dates_text: str | None
    description: str | None
    duplicate: bool


@dataclass(frozen=True)
class ProfileDrafts:
    characters: int
    sections_found: list[str]
    work_experiences: list[WorkDraft]
    educations: list[EducationDraft]
    projects: list[ProjectDraft]


def _work(entry: _Entry) -> tuple[str | None, str | None]:
    parts = _parts(entry.header)
    role = next((p for p in parts if _ROLE_WORDS.search(p)), None)
    company = next((p for p in parts if p != role), None)
    if role is None and len(parts) == 1:
        company = parts[0]
    return company, role


def _education(entry: _Entry) -> tuple[str | None, str | None, str | None]:
    parts = _parts(entry.header)
    institution = next((p for p in parts if _SCHOOL_WORDS.search(p)), None)
    degree_part = next((p for p in parts if p != institution and _DEGREE_WORDS.search(p)), None)
    if institution is None:
        institution = next((p for p in parts if p != degree_part), None)
    degree, field_of_study = degree_part, None
    if degree_part:
        split = re.split(r"\s+in\s+", degree_part, maxsplit=1, flags=re.IGNORECASE)
        if len(split) == 2 and split[0].strip() and split[1].strip():
            degree, field_of_study = split[0].strip(), split[1].strip()
    return institution, degree, field_of_study


def _project(entry: _Entry) -> tuple[str | None, str | None]:
    parts = _parts(entry.header)
    url_match = _URL.search(" ".join(entry.header + entry.description))
    url = url_match.group(0).rstrip(".") if url_match else None
    name = parts[0] if parts else None
    if name:
        # "Chess engine (2021)" -> "Chess engine": a trailing date isn't part of the name.
        trimmed = _TRAILING_DATE.sub("", name).strip()
        name = trimmed or name
    return name, url


def read_drafts(db: Session, user: User, text: str) -> ProfileDrafts:
    """Draft profile entries from CV text, flagging ones the profile already has."""
    lines = _lines(text)
    sections = _sections(lines)

    def existing(model: type, *columns: str) -> set[tuple[str, ...]]:
        rows = db.scalars(select(model).where(model.user_id == user.id))
        return {tuple(normalize_text(getattr(r, c) or "") for c in columns) for r in rows}

    have_work = existing(WorkExperience, "company", "role")
    have_edu = existing(Education, "institution")
    have_projects = existing(Project, "name")

    work = []
    for entry in _entries(sections["work"]):
        company, role = _work(entry)
        if company is None and role is None:
            continue
        work.append(
            WorkDraft(
                company, role, entry.start, entry.end, entry.dates_text, _description(entry.description),
                duplicate=(normalize_text(company or ""), normalize_text(role or "")) in have_work,
            )
        )

    educations = []
    for entry in _entries(sections["education"]):
        institution, degree, field_of_study = _education(entry)
        if institution is None and degree is None:
            continue
        educations.append(
            EducationDraft(
                institution, degree, field_of_study, entry.start, entry.end, entry.dates_text,
                _description(entry.description),
                duplicate=(normalize_text(institution or ""),) in have_edu,
            )
        )

    projects = []
    for entry in _entries(sections["projects"]):
        name, url = _project(entry)
        if name is None:
            continue
        projects.append(
            ProjectDraft(
                name, url, entry.start, entry.end, entry.dates_text, _description(entry.description),
                duplicate=(normalize_text(name),) in have_projects,
            )
        )

    return ProfileDrafts(
        characters=len(text),
        sections_found=[kind for kind in ("work", "education", "projects") if sections[kind]],
        work_experiences=work,
        educations=educations,
        projects=projects,
    )
