"""Interview flashcards from the RAG guide (stage 85).

docs/RAG_GUIDE.md ends most stages with "### Interview questions you can now answer", a
list of bullets like:

    - *What is RRF?* Reciprocal Rank Fusion: score = Σ 1/(k + rank) ...
      continuation lines are indented by two spaces (and may hold sub-bullets)

Each bullet becomes a card: the italic part is the question, the rest the answer, and
the nearest "## Stage ..." heading above it says which stage it belongs to. The guide
stays the only source: nothing is copied by hand, so new stages add cards by themselves.
A card's id is a hash of its question, so saved progress survives the guide being
reordered or growing.
"""

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

GUIDE = Path(__file__).resolve().parents[3] / "docs" / "RAG_GUIDE.md"
SECTION = "### Interview questions you can now answer"

_STAGE = re.compile(r"^## Stage (?P<stage>\w+): (?P<title>.+?)(?:\s+✅.*)?$")
_CARD = re.compile(r"^- \*(?P<question>.+?)\*\s*(?P<answer>.*)$")


@dataclass(frozen=True)
class Card:
    id: str
    stage: str  # "66a", "79", ...
    stage_title: str
    question: str
    answer: str


def parse(text: str) -> list[Card]:
    cards: list[Card] = []
    stage, stage_title = "", ""
    in_section = False
    question: str | None = None
    answer: list[str] = []

    def finish() -> None:
        nonlocal question, answer
        if question is not None:
            body = "\n".join(answer).strip()
            card_id = hashlib.sha1(question.encode()).hexdigest()[:10]
            cards.append(Card(card_id, stage, stage_title, question, body))
        question, answer = None, []

    for line in text.splitlines():
        heading = _STAGE.match(line)
        if line.startswith("#"):
            finish()
            in_section = line.strip() == SECTION
            if heading:
                stage, stage_title = heading.group("stage"), heading.group("title").strip()
            continue
        if not in_section:
            continue
        card = _CARD.match(line)
        if card:
            finish()
            question, answer = card.group("question").strip(), [card.group("answer").strip()]
        elif question is not None and line.startswith("  "):
            answer.append(line[2:].rstrip())
        elif question is not None and not line.strip():
            continue  # a blank line inside or after a card
        else:
            finish()
    finish()
    return cards


def cards(path: Path = GUIDE) -> list[Card]:
    return parse(path.read_text(encoding="utf-8"))


# --- stage 86: a deck from the user's real jobs ----------------------------------------------


def job_cards(db, user) -> list[Card]:
    """Flashcards from each job's interview prep sheet (interview_prep_service): one per saved
    requirement that's linked to a skill. Nothing new is said: the answer is the sheet's own
    template text (what you can honestly claim, the proof to mention, or "don't bluff" plus
    what to study). Requirements not linked to a skill are skipped: the sheet has nothing to
    say about them, and their text is raw posting text. Each job is a group ("stage"),
    named as the assistant names it."""
    from sqlalchemy import select

    from app.core.services.interview_prep_service import interview_prep
    from app.db.models import JobDescription
    from app.rag.chunker import job_label

    cards: list[Card] = []
    jobs = db.scalars(select(JobDescription).where(JobDescription.user_id == user.id).order_by(JobDescription.id))
    for job in jobs:
        label = job_label(job)
        for item in interview_prep(db, user, job):
            if item.requirement.skill is None:
                continue
            skill = item.requirement.skill.name
            lines = [item.guidance]
            if item.cv_warning:
                lines.append(item.cv_warning)
            for evidence in item.evidence:
                lines.append(f"Talk about: {evidence.title}" + (f" ({evidence.source})" if evidence.source else ""))
            if not item.evidence and item.study_links:
                lines.append("Study: " + "; ".join(link.query for link in item.study_links))
            question = f"{label}: they ask about {skill}. What do you say?"
            cards.append(Card(f"job{job.id}-req{item.requirement.id}", str(job.id), label, question, "\n".join(lines)))
    return cards
