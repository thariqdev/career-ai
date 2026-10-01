"""Read a CV (PDF, .docx, plain text) and find which saved skills it mentions.

PREVIEW ONLY: nothing here writes anything. The user reviews what was found and
confirms; only then does the API save CV presence (via cv_presence_service). The CV
text itself is never stored. Being on a CV is a claim, not proof, so nothing here
touches UserSkill, Evidence, or verification status.

Skills are found with the same deterministic SkillListExtractor used for job postings
(whole terms, aliases, no AI), so a CV can only ever match skills already saved.

Files are untrusted input, so reading is defensive: a size limit, a cap on how large a
.docx may decompress to (zip bombs), refusing XML with DOCTYPE/ENTITY declarations
(a .docx never needs them), and any parser failure becomes a clear error, not a crash.
"""

import io
import xml.etree.ElementTree as ElementTree
import zipfile
from dataclasses import dataclass

from pypdf import PdfReader
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.providers.skill_list_extractor import SkillListExtractor
from app.core.exceptions import (
    AmbiguousSkillMatchError,
    CVFileTooLargeError,
    NoCVTextError,
    UnsupportedCVFileError,
)
from app.core.services import skill_service
from app.db.models import CVSkillPresence, Skill, User

MAX_CV_MB = 5
MAX_CV_BYTES = MAX_CV_MB * 1024 * 1024
MAX_DOCX_XML_BYTES = 20 * 1024 * 1024  # decompressed word/document.xml

_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


@dataclass(frozen=True)
class FoundSkill:
    skill: Skill
    matched_text: str  # the CV's own words, e.g. "Postgres" for PostgreSQL
    on_cv: bool  # already marked "on my CV" before this scan


@dataclass(frozen=True)
class CVScan:
    characters: int
    found: list[FoundSkill]
    on_cv_not_found: list[Skill]  # marked "on my CV" but not mentioned in this CV


def _pdf_text(content: bytes) -> str:
    try:
        reader = PdfReader(io.BytesIO(content))
        if reader.is_encrypted and not reader.decrypt(""):
            raise UnsupportedCVFileError("This PDF is password-protected. Paste the text instead.")
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    except UnsupportedCVFileError:
        raise
    except Exception as error:  # untrusted file: any parser failure is the file's fault
        raise UnsupportedCVFileError("This PDF couldn't be read. It may be damaged.") from error


def _docx_text(content: bytes) -> str:
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            info = archive.getinfo("word/document.xml")
            if info.file_size > MAX_DOCX_XML_BYTES:
                raise UnsupportedCVFileError("This Word file is too large once unpacked.")
            xml_bytes = archive.read(info)
    except UnsupportedCVFileError:
        raise
    except (zipfile.BadZipFile, KeyError) as error:
        raise UnsupportedCVFileError("This Word file couldn't be read. It may be damaged.") from error

    if b"<!DOCTYPE" in xml_bytes or b"<!ENTITY" in xml_bytes:
        raise UnsupportedCVFileError("This Word file contains unexpected content.")
    try:
        root = ElementTree.fromstring(xml_bytes)
    except ElementTree.ParseError as error:
        raise UnsupportedCVFileError("This Word file couldn't be read. It may be damaged.") from error

    paragraphs = []
    for paragraph in root.iter(f"{_W}p"):
        parts = []
        for node in paragraph.iter():
            if node.tag == f"{_W}t" and node.text:
                parts.append(node.text)
            elif node.tag == f"{_W}tab":
                parts.append("\t")
            elif node.tag in (f"{_W}br", f"{_W}cr"):
                parts.append("\n")
        paragraphs.append("".join(parts))
    return "\n".join(paragraphs)


def _plain_text(content: bytes) -> str:
    try:
        return content.decode("utf-8-sig")
    except UnicodeDecodeError:
        return content.decode("latin-1")  # never fails; good enough for skill names


def extract_text(filename: str, content: bytes) -> str:
    """Turn an uploaded CV file into text. Raises a DomainError for anything unusable."""
    if len(content) > MAX_CV_BYTES:
        raise CVFileTooLargeError(MAX_CV_MB)

    extension = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    if extension == "pdf":
        text = _pdf_text(content)
    elif extension == "docx":
        text = _docx_text(content)
    elif extension == "txt":
        text = _plain_text(content)
    else:
        raise UnsupportedCVFileError(
            "Only PDF, Word (.docx) and plain text (.txt) CVs are supported."
        )

    if not text.strip():
        raise NoCVTextError()
    return text


def check_pasted_text(text: str) -> str:
    if len(text.encode("utf-8")) > MAX_CV_BYTES:
        raise CVFileTooLargeError(MAX_CV_MB)
    if not text.strip():
        raise NoCVTextError()
    return text


def scan_cv(db: Session, user: User, text: str) -> CVScan:
    """Which saved skills this CV mentions, and which "on my CV" skills it doesn't. Read-only."""
    proposals = SkillListExtractor(skill_service.skill_terms(db)).extract_requirements(text)

    found_by_id: dict[int, tuple[Skill, str]] = {}
    for proposal in proposals.requirements:
        try:
            skill = skill_service.resolve_skill(db, proposal.text)
        except AmbiguousSkillMatchError:
            continue  # a broken taxonomy never breaks the scan; that skill is just skipped
        if skill is not None and skill.id not in found_by_id:
            found_by_id[skill.id] = (skill, proposal.text)

    on_cv_ids = set(
        db.scalars(
            select(CVSkillPresence.skill_id).where(
                CVSkillPresence.user_id == user.id, CVSkillPresence.present.is_(True)
            )
        )
    )
    found = [
        FoundSkill(skill=skill, matched_text=matched, on_cv=skill.id in on_cv_ids)
        for skill, matched in found_by_id.values()
    ]
    missing_ids = on_cv_ids - found_by_id.keys()
    on_cv_not_found = (
        list(db.scalars(select(Skill).where(Skill.id.in_(missing_ids)).order_by(Skill.name)))
        if missing_ids
        else []
    )
    return CVScan(characters=len(text), found=found, on_cv_not_found=on_cv_not_found)
