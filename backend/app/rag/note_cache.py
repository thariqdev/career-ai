"""Cache the user's notes; rebuild them the moment anything they depend on changes (stage 82).

Building the notes from PostgreSQL took ~700 ms of the ~1.1 s spent preparing a question,
and usually nothing had changed since the last question. So the notes are cached, keyed
by a FINGERPRINT of the data.

Cache invalidation is the hard part: a stale cache would answer from old data (saying a
skill is missing right after you proved it), breaking "PostgreSQL is the source of truth".
So the fingerprint is deliberately strict rather than clever:

- it hashes EVERY ROW of EVERY table (row counts or "last updated" times would miss a
  renamed skill: most tables have no updated_at column);
- tables are skipped only by an explicit IGNORED list, so a table added later is
  included automatically (a forgotten table costs a rebuild, never a stale answer);
- the sanitizer's switches are part of the key (they change the notes' text);
- if anything goes wrong computing it, the notes are simply rebuilt.

One process, one user: a plain dict guarded by a lock is enough.
"""

import hashlib
import threading

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import User
from app.rag import sanitize
from app.rag.chunker import Chunk, build_chunks, job_matches
from database import Base

# Tables the notes never read and that change often: excluded so they don't force rebuilds.
IGNORED = frozenset({"assistant_feedback", "note_embeddings"})

# user id -> (fingerprint, notes, job matches). The matches are shared with the exact-list
# tools (stage 83), so a list and the notes always come from the same computation.
_cache: dict[int, tuple[str, list[Chunk], dict]] = {}
_lock = threading.Lock()
stats = {"hits": 0, "rebuilds": 0}  # for tests and curiosity


def fingerprint(db: Session) -> str:
    """A hash of every row the notes could depend on, plus the sanitizer's switches."""
    db.flush()  # include this session's own unsaved changes
    digest = hashlib.sha256(repr((sanitize.ENABLED, sanitize.ALLOW_LIST, sanitize.NEUTRAL_LABELS)).encode())
    for name, table in sorted(Base.metadata.tables.items()):
        if name in IGNORED:
            continue
        digest.update(name.encode())
        for row in db.execute(select(table).order_by(*table.primary_key.columns)):
            digest.update(repr(tuple(row)).encode())
    return digest.hexdigest()


def _entry(db: Session, user: User) -> tuple[list[Chunk], dict]:
    """(notes, job matches): cached while the data's fingerprint is unchanged."""
    try:
        key = fingerprint(db)
    except Exception:  # never risk stale data: compute afresh, cache nothing
        matches = job_matches(db, user)
        return build_chunks(db, user, matches), matches
    with _lock:
        hit = _cache.get(user.id)
        if hit is not None and hit[0] == key:
            stats["hits"] += 1
            return hit[1], hit[2]
    matches = job_matches(db, user)
    chunks = build_chunks(db, user, matches)
    with _lock:
        _cache[user.id] = (key, chunks, matches)
        stats["rebuilds"] += 1
    return chunks, matches


def notes(db: Session, user: User) -> list[Chunk]:
    """The user's notes: from the cache if the data is unchanged, else freshly built."""
    return _entry(db, user)[0]


def matches(db: Session, user: User) -> dict:
    """job id -> JobMatch, from the same cache entry as the notes (stage 83)."""
    return _entry(db, user)[1]


def clear() -> None:
    with _lock:
        _cache.clear()
