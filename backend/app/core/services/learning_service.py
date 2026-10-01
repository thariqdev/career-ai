"""Learning resources for a skill: derived YouTube search links plus user-saved links.

- Search links are DERIVED, never stored: a fixed query per learning mode, turned into
  a YouTube search URL. The app never calls YouTube; clicking the link runs YouTube's
  own live search, so results are always current. No API key, no scraping, no AI.
- Saved links (LearningResource rows) are only ever added by the user and can be
  removed by them (PROJECT_RULES.md section 15: curated, reviewable, editable).
  Only http(s) links with a host are accepted, which also keeps values like
  "javascript:..." out of anything the frontend renders as a link.

Same conventions as the other services: plain functions taking a Session, no HTTP
knowledge, flush but never commit, and flush before reading (autoflush=False).
"""

from urllib.parse import quote_plus, urlparse

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import (
    DuplicateLearningResourceError,
    EmptyResourceTitleError,
    InvalidResourceUrlError,
)
from app.db.models import LearningResource, Skill
from app.db.models.enums import LearningMode

SEARCH_QUERY_TEMPLATES: dict[LearningMode, str] = {
    LearningMode.THEORY_INTERVIEW: "{skill} interview questions",
    LearningMode.TECHNICAL_PRACTICAL: "{skill} full course tutorial",
}

YOUTUBE_SEARCH_URL = "https://www.youtube.com/results?search_query="


def search_query(skill_name: str, mode: LearningMode) -> str:
    return SEARCH_QUERY_TEMPLATES[mode].format(skill=skill_name)


def youtube_search_url(skill_name: str, mode: LearningMode) -> str:
    return YOUTUBE_SEARCH_URL + quote_plus(search_query(skill_name, mode))


def list_resources(db: Session, skill: Skill) -> list[LearningResource]:
    """The skill's saved resources, oldest first. Read-only."""
    db.flush()
    return list(
        db.scalars(
            select(LearningResource)
            .where(LearningResource.skill_id == skill.id)
            .order_by(LearningResource.created_at, LearningResource.id)
        )
    )


def add_resource(
    db: Session, skill: Skill, mode: LearningMode, title: str, url: str
) -> LearningResource:
    """Save a user-chosen link. Rejects a blank title, a non-http(s) URL, or a duplicate."""
    clean_title = title.strip()
    if not clean_title:
        raise EmptyResourceTitleError()

    clean_url = url.strip()
    parsed = urlparse(clean_url)
    if parsed.scheme.lower() not in ("http", "https") or not parsed.netloc:
        raise InvalidResourceUrlError(clean_url)

    db.flush()
    existing = db.scalar(
        select(LearningResource.id).where(
            LearningResource.skill_id == skill.id,
            LearningResource.mode == mode,
            LearningResource.url == clean_url,
        )
    )
    if existing is not None:
        raise DuplicateLearningResourceError(clean_url)

    resource = LearningResource(skill=skill, mode=mode, title=clean_title, url=clean_url)
    db.add(resource)
    db.flush()
    return resource


def remove_resource(db: Session, resource: LearningResource) -> None:
    db.delete(resource)
    db.flush()
