# Career AI — Project Handoff Document

> **Date:** 2026-09-23  
> **Current phase:** Phase 1 — Backend Foundation (in progress)  
> **Status (updated 2026-09-29):** The verification data-entry side is now reachable over HTTP too: claim a skill (`/user-skills`), record evidence (`/evidence`), link the two, and request a status change — all thin routes over the unchanged `verification_service`. Combined with the earlier `/job-descriptions` flow (create → extract → compare → gaps), the whole loop this project exists for — claim a skill, prove it, then check it against a real job posting — is now exercisable end to end over HTTP, all scoped to the single hardcoded user via `Depends(get_current_user)`; no `user_id` ever appears in a request. `CVSkillPresence` also now exists as a model (deliberately independent of verification status — see §7), and `cv_service` now combines it with `UserSkill.status` into one read-only view with a recommendation — but neither has an HTTP endpoint yet, and there is still no way to *write* a `CVSkillPresence` at all. Requirement extraction's real LLM provider still does not exist (see §7). Foundation documents approved. Basic FastAPI backend skeleton created. Fourteen SQLAlchemy models now exist — `Skill`, `SkillAlias`, `User`, `Project`, `WorkExperience`, `Education`, `Evidence`, `UserSkill`, `UserSkillEvidence`, `JobDescription`, `JobRequirement`, `ComparisonResult`, `ComparisonResultEvidence`, `CVSkillPresence` — with migrations applied to a live local PostgreSQL database. Four domain services exist (`verification_service`, `skill_service`, `comparison_service`, `cv_service`), and the first HTTP endpoints (`/skills`) sit on top of `skill_service`. No AI, auth, or frontend yet.
>
> **Note (updated 2026-09-29):** the psycopg2 / Application Control blocker described in §9 below **did recur** on this machine — Windows Smart App Control started blocking `psycopg2`'s compiled `_psycopg....pyd` file (confirmed via the `Microsoft-Windows-CodeIntegrity/Operational` event log, not a guess). Rather than fight that policy, the project **permanently switched database drivers** from `psycopg2-binary` to `pg8000` (a pure-Python PostgreSQL driver with no compiled extension, so there's nothing for the policy to block). See §9 for full detail. `psycopg2` is no longer a dependency of this project at all.

---

## 1. Project Purpose

Career AI is a **personal career and technical-knowledge system**.

It will:

1. Store verified technical knowledge, skills, projects, work experience, and evidence.
2. Let the user paste a job description.
3. Extract technical requirements from the job description.
4. Compare those requirements against the user's verified knowledge.
5. Categorize each requirement as:
   - `VERIFIED`
   - `PARTIAL`
   - `PROVISIONAL`
   - `NOT_VERIFIED`
6. Identify skill gaps.
7. Recommend learning resources (official docs, YouTube, reputable platforms).
8. Provide two learning modes per skill:
   - **THEORY / INTERVIEW**
   - **TECHNICAL / PRACTICAL**
9. Track learning progress explicitly.
10. Eventually support interview preparation for a specific job.

---

## 2. Core Anti-Hallucination Rules (Non-Negotiable)

These rules are the soul of the project. **Do not violate them.**

- PostgreSQL is the **only source of truth** for personal career information.
- The LLM is an **assistant, not an authority**.
- `VERIFIED` requires **concrete, reviewable evidence** (work experience, project contribution, public artifact, certification, documented responsibility).
- **Self-assessment alone must never result in `VERIFIED`.**
- The system must never:
  - Infer years of experience from a technology appearing in a project.
  - Automatically mark an unknown technology as a skill.
  - Automatically add a technology to the CV.
  - Upgrade `PARTIAL` or `PROVISIONAL` to `VERIFIED` without evidence.
- If data is missing, respond with:
  > "Not enough verified information."
- Distinguish between:
  - **Verified knowledge** (`VERIFIED` / `PARTIAL` / `PROVISIONAL` / `NOT_VERIFIED`)
  - **CV presence** (`PRESENT` / `MISSING_FROM_CV` / `NOT_PRESENT`)
  - **Job requirements**
- Use a **canonical skill taxonomy** for matching. Do not rely on simple keyword matching.
- The backend verification/comparison logic — not the LLM — decides final statuses.

---

## 3. Technology Stack

| Layer | Technology |
|-------|------------|
| Frontend | Next.js, TypeScript, Tailwind CSS *(not built yet)* |
| Backend | Python 3.12+, FastAPI, SQLAlchemy 2.x, Pydantic |
| Database | PostgreSQL |
| Migrations | Alembic |
| AI | LLM API with structured outputs *(not integrated yet)* |
| Future | RAG, pgvector *(not integrated yet)* |
| Dev tools | VS Code, Git, Bionic |

---

## 4. Approved Architecture Principles

- **Backend-first development.** Build backend core before frontend.
- **Simple architecture:** `API → Service → SQLAlchemy → PostgreSQL`.
- **No generic repository abstraction** in Version 1 unless a real need appears.
- **Clean separation:** frontend, backend, database, AI logic, and documentation are independent layers.
- **Domain services** hold business logic and verification rules.
- **FastAPI dependencies** provide database sessions per request.
- **Alembic** is the single migration system, located at `backend/alembic/`.
- **Build incrementally** and explain each step.

---

## 5. Foundation Documents

These documents are the project contract:

- `PROJECT_RULES.md` — anti-hallucination, evidence rules, AI boundaries.
- `ARCHITECTURE.md` — system design, data flow, development phases.
- `FOLDER_STRUCTURE.md` — proposed folder layout.
- `README.md` — setup instructions and project overview.

**Any material change to architecture or rules must be documented before implementation.**

---

## 6. Current Backend Structure

```
career-ai/
├── .gitignore
├── README.md
├── HANDOFF.md                  ← this file
├── PROJECT_RULES.md
├── ARCHITECTURE.md
├── FOLDER_STRUCTURE.md
└── backend/
    ├── .env                    ← gitignored; contains DATABASE_URL
    ├── .env.example
    ├── pyproject.toml
    ├── requirements.txt
    ├── requirements-dev.txt
    ├── database.py             ← engine, SessionLocal, Base, .env loading
    ├── alembic.ini
    ├── alembic/
    │   ├── env.py              ← Alembic entry point; imports app.db.models
    │   ├── README
    │   ├── script.py.mako
    │   └── versions/
    │       ├── c844c1e832a2_create_skills_table.py
    │       ├── 8ac9a8427368_create_skill_aliases_table.py
    │       ├── fdf101337f27_create_users_table.py
    │       ├── dc3241d510d0_create_projects_work_experiences_.py
    │       ├── a2829026c599_create_evidence_table.py
    │       ├── 2e2ab2aa40bd_create_user_skills_and_user_skill_.py
    │       ├── e78e547c3ccc_create_job_descriptions_table.py
    │       ├── ed7c26469959_create_job_requirements_table.py
    │       ├── 845323acae55_create_comparison_results_and_.py
    │       └── 8b7d8f0de9ae_create_cv_skill_presences_table.py
    ├── app/
    │   ├── __init__.py
    │   ├── main.py             ← FastAPI app; registers the DomainError handler + health/skills/me/job-descriptions/user-skills/evidence routers
    │   ├── dependencies.py     ← get_db(); get_current_user(); get_requirement_extractor() (default: the safe stub)
    │   ├── api/
    │   │   ├── __init__.py
    │   │   ├── health.py       ← GET /health endpoint
    │   │   ├── skills.py       ← /skills endpoints (thin routes over skill_service)
    │   │   ├── user_skills.py  ← /user-skills endpoints (claim, list, link evidence, status)
    │   │   ├── evidence.py     ← /evidence endpoints (create, list)
    │   │   ├── me.py           ← GET /me (proof endpoint for the single-user bootstrap)
    │   │   ├── job_descriptions.py  ← /job-descriptions endpoints (create, read, extract, compare, gaps)
    │   │   └── errors.py       ← DomainError → HTTP status mapping + handler
    │   ├── core/
    │   │   ├── __init__.py
    │   │   ├── models.py       ← Pydantic schemas (Health/Skill*/User* + JobDescription*/JobRequirement*/Extraction*/ComparisonResult*/Gap*)
    │   │   ├── services/
    │   │   │   ├── __init__.py
    │   │   │   ├── verification_service.py  ← link_evidence(), set_status()
    │   │   │   ├── skill_service.py         ← resolve_skill(), create_skill(), add_alias(), list_skills(), get_skill(), normalize_text()
    │   │   │   ├── comparison_service.py    ← compare_job_description(), latest_results(), skill_gaps(), RequirementGap
    │   │   │   ├── requirement_service.py   ← extract_requirements() (validates an extractor's proposals)
    │   │   │   ├── user_service.py          ← get_or_create_default_user() (single-hardcoded-user bootstrap)
    │   │   │   └── cv_service.py            ← combined_status(), combined_status_for_all(), CVStatus, CombinedSkillStatus
    │   │   └── exceptions.py   ← DomainError + 3 evidence-rule + 3 skill-taxonomy exceptions + RequirementsAlreadyExistError
    │   ├── db/
    │   │   ├── __init__.py
    │   │   └── models/
    │   │       ├── __init__.py     ← registers all 14 models
    │   │       ├── skill.py
    │   │       ├── skill_alias.py
    │   │       ├── user.py
    │   │       ├── project.py
    │   │       ├── work_experience.py
    │   │       ├── education.py
    │   │       ├── evidence.py
    │   │       ├── user_skill.py           ← UserSkill + UserSkillEvidence
    │   │       ├── job_description.py
    │   │       ├── job_requirement.py
    │   │       ├── comparison_result.py    ← ComparisonResult + ComparisonResultEvidence
    │   │       ├── cv_skill_presence.py    ← CVSkillPresence
    │   │       └── enums.py        ← EvidenceType, VerificationStatus
    │   └── ai/                 ← interface + schemas + a safe placeholder only; NO real provider, prompt, key or network code yet
    │       ├── __init__.py
    │       ├── client.py       ← RequirementExtractor (typing.Protocol)
    │       ├── providers/
    │       │   ├── __init__.py
    │       │   └── stub_extractor.py  ← NoOpRequirementExtractor (TEMPORARY placeholder, wired as the default)
    │       ├── prompts/        ← empty
    │       └── schemas.py      ← ExtractedRequirement, ExtractionResult (structured-output contract)
    └── tests/
        ├── __init__.py
        ├── test_health.py
        ├── test_profile_models.py       ← User/Project/WorkExperience/Education/Evidence (in-memory SQLite)
        ├── test_user_skill.py
        ├── test_job_description.py
        ├── test_job_requirement.py
        ├── test_comparison_result.py
        ├── test_verification_service.py
        ├── test_skill_service.py
        ├── test_comparison_service.py
        ├── test_skills_api.py
        ├── test_requirement_service.py
        ├── test_user_service.py
        ├── test_me_api.py
        ├── test_job_descriptions_api.py
        ├── test_user_skills_api.py
        ├── test_evidence_api.py
        ├── test_cv_skill_presence.py
        └── test_cv_service.py
```

---

## 7. Key Files and Their Roles

### `backend/database.py`

The single database connection file.

```python
import os
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")

if DATABASE_URL is None:
    raise ValueError("DATABASE_URL is not set. Please check your .env file.")

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

class Base(DeclarativeBase):
    pass
```

- Loads `.env`.
- Creates the SQLAlchemy `engine`.
- Creates `SessionLocal`, a factory for per-request sessions.
- Defines `Base`, the parent class for all ORM models.

### `backend/app/dependencies.py`

FastAPI database session dependency.

```python
from collections.abc import Generator
from sqlalchemy.orm import Session
from database import SessionLocal


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

- Creates a fresh `Session` for each request.
- Always closes the session, even on exceptions.
- Will be used later as `db: Session = Depends(get_db)`.

### `backend/app/main.py`

FastAPI entry point.

```python
from fastapi import FastAPI
from app.api import health

app = FastAPI(title="Career AI API", version="0.1.0")
app.include_router(health.router)
```

### `backend/app/api/health.py`

```python
from fastapi import APIRouter
from app.core.models import HealthResponse

router = APIRouter()

@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok")
```

### `backend/app/db/models/skill.py`

```python
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from database import Base


class Skill(Base):
    __tablename__ = "skills"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    category: Mapped[str | None] = mapped_column(String, nullable=True)

    aliases: Mapped[list["SkillAlias"]] = relationship(
        "SkillAlias", back_populates="skill"
    )
```

### `backend/app/db/models/skill_alias.py`

```python
from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from database import Base


class SkillAlias(Base):
    __tablename__ = "skill_aliases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    skill_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("skills.id"), nullable=False
    )
    alias: Mapped[str] = mapped_column(String, nullable=False)

    skill: Mapped["Skill"] = relationship("Skill", back_populates="aliases")
```

### `backend/app/db/models/user.py`, `project.py`, `work_experience.py`, `education.py`, `evidence.py`

Added 2026-09-23. Together these form the "profile" cluster:

- **`User`** — the single career profile (`id`, `email` unique, `full_name`, `created_at`). Has one-to-many relationships to `Project`, `WorkExperience`, `Education`, and `Evidence`.
- **`Project`**, **`WorkExperience`**, **`Education`** — each has a `user_id` FK back to `User`, plus its own domain fields (e.g. `WorkExperience.company/role/start_date/end_date`). Each also has an `evidence_records` back-reference.
- **`Evidence`** (`app/db/models/evidence.py`) — the model that makes the anti-hallucination rules concrete. Every row has an `evidence_type` (see `enums.py`) and optional FKs `work_experience_id` / `project_id` / `education_id` — at most one is normally set, pointing back to the record the evidence was drawn from. `evidence_type` **excludes** any "self-assessment" option by design, so a self-reported skill can never be stored as `Evidence` (per `PROJECT_RULES.md` §4.2) — self-assessment will instead live as a flag/status on `UserSkill` when that model is added next.
- **`app/db/models/enums.py`** — `EvidenceType` (`WORK_EXPERIENCE`, `PROJECT`, `CERTIFICATION`, `ARTIFACT`, `OTHER`), a Python `str, enum.Enum` mapped to a native Postgres `ENUM` column via SQLAlchemy's `Enum` type.

### `backend/app/core/services/verification_service.py` and `backend/app/core/exceptions.py`

Added 2026-09-25 — the first domain service (the "Service" layer in `API → Service → SQLAlchemy → PostgreSQL`). Plain functions taking a SQLAlchemy `Session`; no HTTP/FastAPI imports, no schema change.

- **`link_evidence(db, user_skill, evidence) -> UserSkillEvidence`** — attaches an `Evidence` record to a `UserSkill`. Raises `EvidenceOwnershipError` if the evidence belongs to a different user, `EvidenceAlreadyLinkedError` if the link already exists. **Never changes status** — linking is not promotion.
- **`set_status(db, user_skill, new_status) -> UserSkill`** — the explicit way to change `UserSkill.status`. `VERIFIED` and `PARTIAL` require ≥1 linked `Evidence` (counted from the database, not a possibly stale collection), otherwise `InsufficientEvidenceError` and the status is unchanged. `PROVISIONAL` and `NOT_VERIFIED` are always allowed (downgrades included).
- **Conventions:** (1) the service **flushes but never commits** — the caller owns the transaction; (2) **this module is the only place that should write `UserSkill.status` or create `UserSkillEvidence` links** — Postgres cannot cheaply enforce "VERIFIED requires evidence" across tables, so callers must go through it. This is a convention, not a database guarantee: nothing stops other code from assigning `status` directly, so keep checking with grep (`\.status\s*=` / `UserSkillEvidence\(` outside this module and tests). (3) Each function calls `db.flush()` first because `SessionLocal` uses `autoflush=False`, so freshly-added objects would otherwise still have `id`/`user_id` of `None`.
- **Exceptions** (`app/core/exceptions.py`): `DomainError` (base) → `EvidenceOwnershipError`, `EvidenceAlreadyLinkedError`, `InsufficientEvidenceError` (evidence rules) and `EmptySkillTextError`, `SkillNameCollisionError`, `AmbiguousSkillMatchError` (skill taxonomy). Pure Python; the future API layer will map them to HTTP responses.
- **Known gaps:** there is no `unlink_evidence` yet — if one is added it must re-check that a `VERIFIED`/`PARTIAL` skill still has ≥1 link. New `UserSkill` rows still get their initial `PROVISIONAL` status from the model default (an insert default, not a service call).

### `backend/app/core/services/skill_service.py`

Added 2026-09-25 — canonical skill resolution and safe taxonomy maintenance (`PROJECT_RULES.md` §6, `ARCHITECTURE.md` §10). Same conventions as `verification_service`: plain functions taking a `Session`, no HTTP knowledge, flush-never-commit, flush before reading (`autoflush=False`). No schema change.

- **`resolve_skill(db, text) -> Skill | None`** — normalizes the text and returns the single `Skill` whose name or alias matches; `None` if nothing matches or the text is blank; raises `AmbiguousSkillMatchError` if it maps to more than one *distinct* Skill (a name match and an alias match to the *same* Skill is fine). **Read-only: never creates a Skill or alias.**
- **`create_skill(db, name, category=None) -> Skill`** — rejects blank names (`EmptySkillTextError`) and any name whose normalized text already belongs to any skill name or alias (`SkillNameCollisionError`, message names the owning skill). Stores the display name as typed, stripped.
- **`add_alias(db, skill, alias) -> SkillAlias`** — same blank + collision checks over the whole namespace, including the skill's *own* name/aliases (an alias equal to its own skill's name is redundant, so rejected).
- **Conventions:** (1) **exact match only, by design** — normalization is only strip + collapse-whitespace + `casefold`; no stemming/punctuation/fuzzy logic, so related technologies are never equivalent (`SQL` ≠ `PostgreSQL`, `NodeJS` ≠ `Node.js`) unless an alias explicitly says so; (2) **lookups never create** skills (anti-hallucination rule); (3) **the backend, not an LLM, owns the final mapping**; (4) names and aliases share **one normalized namespace**, enforced in the service. Matching loads names + aliases and compares in Python (SQL can't collapse internal whitespace portably; fine at taxonomy scale).
- **Read helpers (added with the API, 2026-09-25):** `list_skills(db)` (all skills ordered by name) and `get_skill(db, skill_id)` (lookup by id or `None`) — read-only, additive; existing function logic was not changed. They exist so routes never query SQLAlchemy directly (`API → Service → SQLAlchemy`).
- **Known gaps:** (a) **no DB-level uniqueness** — `skills.name` is only case-sensitively unique and `skill_aliases.alias` has no constraint, so the namespace guarantee holds only for code that goes through this module (a unique index on a stored normalized column is a possible later hardening step, deliberately not added); (b) **no skill/alias deletion or rename functions**; (c) optional related-skill / parent-child relationships from `PROJECT_RULES.md` §6 are not modeled; (d) each lookup reads the whole taxonomy (O(n)) — fine now, revisit if it grows; (e) direct `Skill(...)`/`SkillAlias(...)` construction elsewhere would bypass the checks — keep grepping (`\bSkill\(` / `\bSkillAlias\(` in app code outside this module).

### `backend/app/core/services/comparison_service.py`

Added 2026-09-25 — the deterministic engine that compares a job description's requirements against the user's verified knowledge and stores `ComparisonResult` rows. Same conventions as the other services (plain functions taking a `Session`, no HTTP knowledge, flush-never-commit, flush before reading). No schema change.

- **`compare_job_description(db, job_description) -> list[ComparisonResult]`** — for each `JobRequirement` of the job description (ordered by requirement id, enforced with an explicit `ORDER BY`), creates one **new** `ComparisonResult` and returns them in that order. The user is `job_description.user_id`. Decision rules, first match wins:
  1. `requirement.skill_id` is `None` → `NOT_VERIFIED`, no `user_skill`, reasoning says the requirement is not mapped to a canonical skill + "Not enough verified information."
  2. Skill mapped but the user has no `UserSkill` for `(user_id, skill_id)` → `NOT_VERIFIED`, no `user_skill`, reasoning says no claim is recorded + "Not enough verified information."
  3. `UserSkill` exists → `knowledge_status` = its status, `user_skill` set, and one `ComparisonResultEvidence` link per `Evidence` currently linked to it.
  4. **Defensive cap:** the `UserSkill` says `VERIFIED`/`PARTIAL` but has **zero** linked evidence (data written around `verification_service`) → recorded as `PROVISIONAL`, and the reasoning says the claim was not backed by evidence. The comparison never repeats an evidence-less `VERIFIED`/`PARTIAL` claim.
- **Reasoning** is a fixed template built from record ids and titles only (e.g. `UserSkill #4 is VERIFIED; supported by 2 evidence record(s): #7 'FundsApp repo', #9 'Py cert'.`) — no generated prose, no LLM.
- **Read side (added 2026-09-26):**
  - **`latest_results(db, job_description) -> list[ComparisonResult]`** — for each requirement that has at least one result, its **highest-id** result (ids only grow; timestamps can tie), ordered by requirement id via an explicit `ORDER BY`. One query (a `max(id)` grouped subquery). A requirement that was never compared has no result and is **absent** — never guessed.
  - **`RequirementGap`** — a small frozen dataclass (`requirement`, `result`, and a convenience `skill` property that is `None` for an unmapped requirement). Plain Python, not an ORM model, never persisted; named to avoid confusion with a `SkillGap` table, which deliberately does not exist.
  - **`skill_gaps(db, job_description) -> list[RequirementGap]`** — `latest_results` minus `VERIFIED` (so `PARTIAL`, `PROVISIONAL`, `NOT_VERIFIED`), ordered required-before-optional, then requirement id. Unmapped requirements **are** gaps (`skill is None`). `is_required` affects only the ordering, never inclusion or status.
  - **A skill gap is derived, never stored** (see `ARCHITECTURE.md` §4): storing it would duplicate `ComparisonResult` and go stale when evidence is added — e.g. after linking evidence + `VERIFIED` + a re-run, the requirement drops out of `skill_gaps` while its older `PROVISIONAL`/`NOT_VERIFIED` rows remain as history. Both functions are **read-only and never trigger a comparison**. A table can be added later only if gap-specific state (priority/dismissed/notes) is ever needed.
- **Conventions:** (1) **deterministic** — same data, same result; (2) **reports, never promotes** — it reads `UserSkill.status` but never writes it, never modifies `UserSkill`/`Evidence`/their links, and never calls `verification_service`; (3) **append-only snapshots** — every run adds new rows and never updates or deletes older ones; the current state is read back with `latest_results`; (4) `JobRequirement.is_required` does **not** influence status; (5) **no `cv_status` yet** — deferred until `CVSkillPresence` exists; (6) **requirement extraction is a separate step** (`requirement_service`, below) — this only compares requirements that already exist.
- **Known gaps / still pending:** HTTP endpoints and `cv_status`.

### LLM boundary: `app/ai/schemas.py`, `app/ai/client.py`, `app/core/services/requirement_service.py`

Added 2026-09-26 — requirement extraction where the **LLM is an untrusted proposer**. **There is no real LLM, provider, prompt, API key or network code yet**: only an interface, a typed schema, the validating service, and a fake extractor in the tests. No schema change, no API endpoint.

- **`ExtractedRequirement`** (`text`, `is_required=True`, `skill_mention=None`) and **`ExtractionResult`** (`requirements: list[...]`) in `app/ai/schemas.py` — the structured-output contract. Shape/types only; no business rules. `skill_mention` is a *name/alias mention*, never a skill id.
- **`RequirementExtractor`** — a `typing.Protocol` in `app/ai/client.py` (per `FOLDER_STRUCTURE.md`: "provider-agnostic LLM client interface") with one method, `extract_requirements(raw_text) -> ExtractionResult`. Its sole job is text → typed proposal; it knows nothing about the database. The real LLM-backed implementation will plug in later behind it (`app/ai/providers/`).
- **`extract_requirements(db, job_description, extractor) -> ExtractionOutcome`** (`requirement_service.py`) where `ExtractionOutcome` is a frozen dataclass of `accepted: list[JobRequirement]` and `rejected: list[RejectedRequirement]` (a frozen dataclass of the `proposal` and a fixed `reason` string). Order of operations:
  1. Flush, then check the **database** (not a possibly stale relationship) for any existing `JobRequirement` of this job description; if any, raise `RequirementsAlreadyExistError` (HTTP 409) **before calling the extractor** — no LLM cost or side effects when refused, and requirements are never silently duplicated.
  2. Call the extractor once with `raw_text`. If it raises, the exception propagates and nothing is stored.
  3. For each proposal, in order: blank text → rejected (`"blank requirement text"`); **grounding check** fails → rejected (`"not found in job description text"`); duplicate (after normalization) of an earlier accepted proposal → rejected (`"duplicate requirement text"`, first wins); otherwise accepted.
  4. Accepted proposals become `JobRequirement` rows (`requirement_text` = proposed text stripped, `is_required` = proposed flag), flushed, returned in creation order.
- **Grounding check (strict on purpose):** the proposed text must appear in the job description's `raw_text`, compared with `skill_service.normalize_text` (strip, casefold, collapse whitespace — the *same* helper `skill_service` uses; it was renamed from private `_normalize` to public `normalize_text`, no behavior change). Only case/whitespace differences are tolerated; a **paraphrase is rejected**. That costs recall but can never admit a fabricated requirement; loosening it is a later decision to make with evidence. **Known limitation:** it is a substring check, so a very short proposal (e.g. one or two letters) can match inside a longer word — a word-boundary rule is a possible later tightening.
- **Skill mapping only through `skill_service.resolve_skill(skill_mention)`** (unmodified, read-only). No match, a blank/`None` mention, or `AmbiguousSkillMatchError` → `skill_id` stays `None` (never guessed; a taxonomy problem never fails the whole extraction). **The LLM cannot create skills** — a test asserts the `Skill`/`SkillAlias` counts don't change for an unknown mention.
- **Rejects are returned, not persisted**, so the caller can see what the model proposed and why it was dropped.
- **Conventions:** plain functions taking a `Session`, no HTTP knowledge, flush-never-commit (a test rolls back after the call and finds nothing persisted), no writes to `UserSkill`/`ComparisonResult`.
- **Still pending:** the real LLM provider implementation and its prompt, an API endpoint that runs extraction, and any re-extraction workflow (today a re-run is simply refused).

### API layer: `backend/app/api/skills.py`, `app/api/errors.py`, schemas in `app/core/models.py`

Added 2026-09-25 — the first HTTP layer. No schema change, no auth, no user scoping.

**Endpoints** (`app/api/skills.py`, router prefix `/skills`; each route uses `db: Session = Depends(get_db)`):

| Method + path | Calls | Success | Notes |
|---|---|---|---|
| `POST /skills` | `create_skill` | `201` `SkillResponse` | body `{name, category?}` |
| `GET /skills` | `list_skills` | `200` `list[SkillResponse]` | ordered by name |
| `GET /skills/resolve?text=...` | `resolve_skill` | `200` `SkillResponse` | `404 {"detail": ...}` if no match; **read-only, never creates anything**; declared before any future `/{skill_id}` GET so it cannot be shadowed |
| `POST /skills/{skill_id}/aliases` | `get_skill` + `add_alias` | `201` `SkillResponse` (updated skill) | body `{alias}`; `404` if the skill id doesn't exist |

**Conventions**
- **Routes are thin:** they call `skill_service` and nothing else — no SQLAlchemy queries, no business rules, **no `try/except` for `DomainError`**.
- **The route owns the transaction:** services flush but never commit, so each write route calls `db.commit()` after a successful service call. If the service raises, the route never reaches `commit()`; `get_db` closes the session, which rolls back.
- **Schemas are separate from ORM models** and live in `app/core/models.py` (per `FOLDER_STRUCTURE.md`): `SkillCreate`, `AliasCreate`, `SkillResponse` (`id`, `name`, `category`, `aliases: list[str]` — alias *text* only, built from the ORM object with `from_attributes`). Schemas enforce **shape/types only**; blank/collision/ambiguity rules stay in `skill_service`.
- **One app-wide error handler** (`app/api/errors.py`, registered in `main.py`) maps `DomainError` → `{"detail": "<message>"}` (FastAPI's own error shape):

| DomainError | HTTP status |
|---|---|
| `EmptySkillTextError` | 422 |
| `SkillNameCollisionError` | 409 |
| `AmbiguousSkillMatchError` | 409 |
| `EvidenceOwnershipError`, `EvidenceAlreadyLinkedError`, `InsufficientEvidenceError` | 409 (mapped now, not yet used by any endpoint) |
| `RequirementsAlreadyExistError` | 409 |
| any other `DomainError` subclass | 400 |

  Subclasses of a mapped error inherit its status (the handler walks the class hierarchy).
- **No auth yet, and skills are a shared taxonomy, not user-scoped** — so these endpoints take no user identity. Auth must be added before any deployment (`ARCHITECTURE.md` §16).
- **Tests** (`tests/test_skills_api.py`) use `TestClient` with `app.dependency_overrides[get_db]` → in-memory SQLite (`StaticPool` + `check_same_thread=False`, needed because `TestClient` runs the app in another thread; override cleared after every test).
- **Still pending:** endpoints for everything else (`/experience`, `/projects`, `/job-descriptions`, `/comparisons`, `/learning`), skill rename/delete and `GET /skills/{id}`, and any endpoint that uses `verification_service` / `comparison_service`.

### Single-hardcoded-user bootstrap: `app/core/services/user_service.py`, `app/dependencies.py`, `app/api/me.py`

Added 2026-09-27 — this system runs as **one fixed user account**. There is no auth, no login, and **no `user_id` ever appears in any request** (path, query, or body) — a grep across `app/api/*.py` and `app/core/models.py` confirms it.

- **`user_service.DEFAULT_USER_EMAIL`** (`"me@career-ai.local"`) — a fixed constant, deliberately **not configurable**. This is a single-user bootstrap, not multi-tenant auth, so nothing about it should look like a setting.
- **`get_or_create_default_user(db) -> User`** — looks up the `User` by that email; creates it (email only, `full_name` stays `None`) on first use. Flushes before the lookup so a pending user added earlier in the same session is found rather than colliding with the unique-email constraint on insert. Same convention as every other service: **it does not commit.** Plumbing, not a domain rule — it decides nothing about verification, taxonomy, or comparisons.
- **`get_current_user(db)` in `app/dependencies.py`** — a FastAPI dependency (not a service) that calls `get_or_create_default_user` and then **does commit**. This is the one deliberate exception to "services flush, routes commit": the dependency runs *before* the route body, so the user must already be durably in the database before anything downstream in the same request — the route's own service calls (which may reference `user_id`) and the route's own commit — can safely rely on it existing. It is narrow bootstrap plumbing, not a new pattern.
- **`GET /me` (`app/api/me.py`)** — the proof endpoint. `user: User = Depends(get_current_user)`; the route does nothing but return what the dependency resolved. Response schema `UserResponse` (`id`, `email`, `full_name`).
- **Looking ahead:** `/job-descriptions`, `/user-skills` and `/evidence` (below) all do exactly this. A dedicated `/comparisons` is still not built (comparing/gaps live under `/job-descriptions/{id}/...`).

### Job-descriptions API: `app/api/job_descriptions.py`, `app/ai/providers/stub_extractor.py`, schemas in `app/core/models.py`

Added 2026-09-28 — the first end-to-end path over HTTP: create a job description, extract its requirements, compare them against verified knowledge, read the gaps. No schema change; wires up `requirement_service` and `comparison_service` exactly as they already were.

**Routes** (prefix `/job-descriptions`; every route takes `user: User = Depends(get_current_user)`, no route or schema takes a `user_id`):

| Method + path | Calls | Success | Notes |
|---|---|---|---|
| `POST ""` | *(built directly — see below)* | `201` `JobDescriptionResponse` | body `{raw_text, title?, company?, source_url?}` |
| `GET "/{id}"` | — | `200` `JobDescriptionResponse` (with `requirements`) | `404` if missing or not owned |
| `POST "/{id}/extract"` | `requirement_service.extract_requirements` | `200` `ExtractionResponse` (`accepted`/`rejected`) | `404` ownership check; `RequirementsAlreadyExistError` flows to the existing handler → `409` |
| `POST "/{id}/compare"` | `comparison_service.compare_job_description` | `200` `list[ComparisonResultResponse]` | `404` ownership check; append-only, so calling twice doubles the stored count |
| `GET "/{id}/gaps"` | `comparison_service.skill_gaps` | `200` `list[GapResponse]` | `404` ownership check; **read-only, no commit** — `skill_gaps` only reads, and the one write this request could ever need (bootstrapping the user) already happened and committed inside `get_current_user` |

**Ownership check is 404, never 403 — and lives in the API layer, not a service.** A missing id and an id that exists but belongs to someone else return the *exact same* 404 body, so a response can never be used to learn whether some other user's job description id exists. This is a decision about what an HTTP response is allowed to reveal, not a business rule about data, so it belongs in `job_descriptions.py`'s one shared helper (`_get_owned_job_description`) rather than in a service — `requirement_service` and `comparison_service` already take a `JobDescription` object, not an id, so they never need to know about ownership at all.

**`POST ""` has no service call.** There is no business rule to enforce beyond shape, which Pydantic's `JobDescriptionCreate` already checks — no blank check, no uniqueness, nothing like `create_skill`'s collision rules. So the route builds the `JobDescription` row directly, the same way `SkillCreate` itself needs no service (only `create_skill`'s actual rules warrant one).

**The stub extractor (`app/ai/providers/stub_extractor.py`):** `NoOpRequirementExtractor` — **a TEMPORARY placeholder**, always returns zero proposed requirements. It never guesses, matching the same anti-hallucination stance as everything else in this project. It's wired as the *default* via `get_requirement_extractor` in `app/dependencies.py`, a module-level singleton (it holds no state) — so `/extract` is a real, provable endpoint today. **Swapping in a real LLM-backed provider later means changing only that one dependency; no endpoint or service changes.** Tests override the dependency with a fake extractor to exercise real accept/reject behavior over HTTP.

**New schemas** (`app/core/models.py`): `JobDescriptionCreate`, `JobDescriptionResponse`, `JobRequirementResponse`, `RejectedRequirementResponse`, `ExtractionResponse`, `ComparisonResultResponse`, `GapResponse`. Two of these needed something other than `SkillResponse`'s `field_validator(mode="before")` pattern: `JobRequirementResponse.skill_name` and `ComparisonResultResponse.evidence_ids` have **no matching attribute at all** on their ORM source (`JobRequirement` has `.skill`, not `.skill_name`; `ComparisonResult` has `.evidence_links`, not `.evidence_ids`) — a per-field `from_attributes` lookup fails before a `field_validator` ever runs (confirmed: raises `pydantic.ValidationError: Field required`). Both use `model_validator(mode="before")` instead, which intercepts the whole source object first. `RejectedRequirementResponse` and `GapResponse` build from `requirement_service`'s/`comparison_service`'s plain dataclasses (not ORM objects) via small `from_rejection`/`from_gap` classmethods rather than `from_attributes`.

**Still pending:** `DELETE`/update on any of this, and — still — the real LLM provider implementation. Evidence-linking and user-skill endpoints are now done (below).

### User-skills API: `app/api/user_skills.py`

Added 2026-09-29 — thin routes over `verification_service` (unchanged) and `skill_service.get_skill` (unchanged). No schema change.

| Method + path | Calls | Success | Notes |
|---|---|---|---|
| `POST "/user-skills"` | `skill_service.get_skill` + explicit checks | `201` `UserSkillResponse` | `404` if `skill_id` doesn't exist; `409` if already claimed |
| `GET "/user-skills"` | — | `200` `list[UserSkillResponse]` | the current user's claims only, ordered by skill name |
| `POST "/user-skills/{id}/evidence-links"` | `verification_service.link_evidence` | `201` `UserSkillResponse` (updated) | `404` if the claim isn't owned, or the evidence id doesn't exist at all; `409` (`EvidenceAlreadyLinkedError`/`EvidenceOwnershipError`, already mapped) for a duplicate link or evidence owned by someone else |
| `POST "/user-skills/{id}/status"` | `verification_service.set_status` | `200` `UserSkillResponse` | `404` ownership check; `409` (`InsufficientEvidenceError`, already mapped) for `VERIFIED`/`PARTIAL` with no linked evidence |

**Two decisions, made and documented in the router's own docstring:**
- **Claiming the same skill twice is checked explicitly in the route and returns `409`**, rather than letting `UserSkill`'s DB-level unique constraint (`uq_user_skill`) fail. **Mutation-checked:** removing that check turned the failure into a raw, unhandled `sqlite3.IntegrityError` instead of a clean `{"detail": ...}` body — confirming exactly the trade-off the docstring describes. There's exactly one caller of "create a UserSkill" today (this route); if a second appears, this belongs in a small `user_skill_service`.
- **Linking evidence checks that the evidence *exists* (404 if not), but deliberately does *not* check whether it's *owned* by the current user** — that's `verification_service.link_evidence`'s own job (`EvidenceOwnershipError` → 409, already mapped), so the route doesn't duplicate the service's rule.
- Same "404, never 403" ownership helper pattern as `job_descriptions.py` (`_get_owned_user_skill`).

### Evidence API: `app/api/evidence.py`

Added 2026-09-29 — thin routes; `POST` builds the `Evidence` row directly (no service), same reasoning as `JobDescriptionCreate`: no business rule beyond shape, which `EvidenceCreate.evidence_type: EvidenceType` already enforces via Pydantic.

| Method + path | Success | Notes |
|---|---|---|
| `POST "/evidence"` | `201` `EvidenceResponse` | body `{evidence_type, title, description?, url?, work_experience_id?, project_id?, education_id?}` |
| `GET "/evidence"` | `200` `list[EvidenceResponse]` | the current user's evidence only, ordered by `created_at` |

**Sub-record ownership is checked at creation time:** if `work_experience_id`/`project_id`/`education_id` is given, it must exist **and** belong to the current user, or the route responds `404` — extending the same "exists-and-mine, or 404" rule `job_descriptions.py` established, via one small local helper (`_require_owned_reference`), reused for all three reference types.

**New schemas** (`app/core/models.py`): `UserSkillCreate`, `UserSkillResponse`, `EvidenceCreate`, `EvidenceResponse`, `EvidenceLinkCreate`, `StatusUpdate`. `UserSkillResponse.skill_name` needed `model_validator(mode="before")` — same reason as `JobRequirementResponse.skill_name`: `UserSkill` has `.skill`, not `.skill_name`, so a per-field `from_attributes` lookup fails before a `field_validator` would run. `EvidenceCreate.evidence_type` and `StatusUpdate.status` are typed directly as `EvidenceType`/`VerificationStatus`, so Pydantic itself rejects a bad value with `422` before any route code runs — the same "schemas validate shape/types only" convention, since these two are fixed, known enums rather than free text.

**Mutation-checked and caught:** the evidence sub-record ownership check (removing it let a foreign-owned reference through instead of `404`), and the `user_skills.py` ownership check (removing it let a not-owned claim's evidence-link/status routes proceed instead of `404`).

### `backend/app/core/services/cv_service.py`

Added 2026-09-29 — combines `UserSkill.status` and `CVSkillPresence.present` into one read-only view with a recommendation. Same shape as `comparison_service`'s read side (`latest_results`/`skill_gaps`): derives a view from two independently-changing facts without storing anything new. **Read-only — writes nothing, including no `CVSkillPresence`** (there is still no way to create/update one; that's a separate future task). No schema change.

- **`CVStatus`** — a plain Python `str, enum.Enum` (`PRESENT`, `MISSING_FROM_CV`, `NOT_PRESENT`), **not** mapped to any database column.
- **`CombinedSkillStatus`** — a frozen dataclass: `skill`, `knowledge_status` (`VerificationStatus | None`), `cv_status`, `recommendation` (`str | None`).
- **`combined_status(db, user, skill) -> CombinedSkillStatus`** — the view for one `(user, skill)` pair.
- **`combined_status_for_all(db, user) -> list[CombinedSkillStatus]`** — every skill with a `UserSkill` **or** `CVSkillPresence` row for that user (a skill with neither is excluded — nothing to say about it), ordered by skill name then id. **Three queries total** (this user's `UserSkill`s, this user's `CVSkillPresence`s, the relevant `Skill`s), joined in Python — not one query per skill.
- **The exact decision table** (generalizes `PROJECT_RULES.md` §5's two worked examples to all 10 combinations; implemented once, in a shared internal `_derive` helper, so it can't drift between the two public functions):

  | `cv_present` | `knowledge_status` | `cv_status` | `recommendation` |
  |---|---|---|---|
  | `True` | any | `PRESENT` | "listed on your CV without verified evidence…" if `knowledge_status` is `None`/`NOT_VERIFIED`/`PROVISIONAL`; else `None` |
  | `False` | `VERIFIED` or `PARTIAL` | `MISSING_FROM_CV` | "Consider adding {skill} to your CV — you have {status} evidence for it." |
  | `False` | `PROVISIONAL`, `NOT_VERIFIED`, or `None` | `NOT_PRESENT` | `None` |

- **`None` vs `NOT_VERIFIED` are kept distinct in the output** — `None` means "never claimed," `NOT_VERIFIED` means "an explicit claim exists and isn't backed by evidence." Neither function collapses this distinction anywhere.
- **Mutation-checked, all four caught:** removing the `MISSING_FROM_CV` branch, removing the "unproven but on CV" recommendation, including skills with neither row in `combined_status_for_all`, and dropping the user filter (leaking another user's rows) — each broke exactly the test named for it, then the file was restored byte-identical.
- **Still pending:** an API endpoint to *read* this view, and — separately — any way to *write* a `CVSkillPresence` at all (no service or endpoint creates/updates one yet).

### `backend/app/db/models/__init__.py`

```python
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

__all__ = [
    "Skill", "SkillAlias", "User", "Project", "WorkExperience", "Education", "Evidence",
    "UserSkill", "UserSkillEvidence", "JobDescription", "JobRequirement",
    "ComparisonResult", "ComparisonResultEvidence",
]
```

This centralizes model registration. `alembic/env.py` imports `app.db.models`, which triggers this file and populates `Base.metadata`.

### `backend/alembic/env.py`

```python
from database import Base, DATABASE_URL
from app.db import models  # noqa: F401

config.set_main_option("sqlalchemy.url", DATABASE_URL)
target_metadata = Base.metadata
```

### Existing Migrations

Nine migrations exist, applied in order, all consistent with the models (`alembic current` → `845323acae55 (head)`, `alembic check` reports no drift):

- `c844c1e832a2_create_skills_table.py`
- `8ac9a8427368_create_skill_aliases_table.py`
- `fdf101337f27_create_users_table.py`
- `dc3241d510d0_create_projects_work_experiences_.py` — creates `projects`, `work_experiences`, `educations` together (one migration for the sibling group, per the "coherent group of models" convention).
- `a2829026c599_create_evidence_table.py` — creates `evidence` plus the `evidence_type` Postgres enum type. Its `downgrade()` was hand-edited to also drop the enum type (Alembic's autogenerate doesn't do this itself, which would otherwise break a downgrade→upgrade cycle).
- `2e2ab2aa40bd_create_user_skills_and_user_skill_.py` — creates `user_skills` (with the `verification_status` Postgres enum type and a `(user_id, skill_id)` unique constraint) and the `user_skill_evidence` join table. Its `downgrade()` also drops the enum type; this migration **owns** `verification_status`.
- `e78e547c3ccc_create_job_descriptions_table.py` — creates `job_descriptions`.
- `ed7c26469959_create_job_requirements_table.py` — creates `job_requirements`.
- `845323acae55_create_comparison_results_and_.py` — creates `comparison_results` and the `comparison_result_evidence` join table. It **reuses** the existing `verification_status` type via `postgresql.ENUM(..., create_type=False)` (autogenerate emitted a plain `sa.Enum`, which would have tried to re-create the type — corrected by hand), and its `downgrade()` deliberately does **not** drop the type because `user_skills` still uses it.
- `8b7d8f0de9ae_create_cv_skill_presences_table.py` — creates `cv_skill_presences` (`present` is a plain `Boolean`, no enum involved, so no downgrade hand-edit was needed — autogenerate's output was used as-is after review).

The SQL below covers the tables from the first five migrations only (later tables are described in §10 and in their model files' docstrings):

```sql
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    email VARCHAR NOT NULL UNIQUE,
    full_name VARCHAR,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE projects (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    name VARCHAR NOT NULL,
    description TEXT,
    role VARCHAR,
    url VARCHAR,
    start_date DATE,
    end_date DATE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE work_experiences (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    company VARCHAR NOT NULL,
    role VARCHAR NOT NULL,
    start_date DATE NOT NULL,
    end_date DATE,
    description TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE educations (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    institution VARCHAR NOT NULL,
    degree VARCHAR,
    field_of_study VARCHAR,
    start_date DATE,
    end_date DATE,
    description TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TYPE evidence_type AS ENUM ('WORK_EXPERIENCE', 'PROJECT', 'CERTIFICATION', 'ARTIFACT', 'OTHER');

CREATE TABLE evidence (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    evidence_type evidence_type NOT NULL,
    title VARCHAR NOT NULL,
    description TEXT,
    url VARCHAR,
    work_experience_id INTEGER REFERENCES work_experiences(id),
    project_id INTEGER REFERENCES projects(id),
    education_id INTEGER REFERENCES educations(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

---

## 8. What Is Already Working

- FastAPI server starts (also verified against the live Postgres).
- `GET /health` returns `{"status": "ok"}`.
- `/skills` endpoints work end to end: `POST /skills`, `GET /skills`, `GET /skills/resolve`, `POST /skills/{id}/aliases`, with domain errors mapped to HTTP statuses (see §7).
- Health test passes without a database.
- SQLAlchemy mappings for `Skill` and `SkillAlias` load correctly. Bidirectional relationship (`skill.aliases` / `alias.skill`) works.
- All 13 models (`Skill`, `SkillAlias`, `User`, `Project`, `WorkExperience`, `Education`, `Evidence`, `UserSkill`, `UserSkillEvidence`, `JobDescription`, `JobRequirement`, `ComparisonResult`, `ComparisonResultEvidence`) are mapped, migrated, and confirmed against a **live local PostgreSQL database** (`career_ai`) — not just SQLite. `alembic current` → `845323acae55 (head)`, `alembic check` → no drift, table/column shapes verified with `sqlalchemy.inspect`.
- `User → Project/WorkExperience/Education → Evidence` relationships verified in `tests/test_profile_models.py` (in-memory SQLite, 3 tests): ownership relationships, evidence linking back to its source record, and evidence standing alone (e.g. a certification) without a source record.
- Model relationship/constraint tests for every model group live in `tests/test_user_skill.py`, `test_job_description.py`, `test_job_requirement.py`, `test_comparison_result.py` (all in-memory SQLite).
- `tests/test_verification_service.py` (11 tests, in-memory SQLite with `autoflush=False` to mirror `SessionLocal`) covers the evidence rules: link happy path leaves status unchanged, cross-user and duplicate links rejected, `VERIFIED`/`PARTIAL` rejected without evidence, `VERIFIED` allowed after linking in the same session, conservative statuses and downgrades allowed, and pending (never-flushed) objects handled.
- `tests/test_skill_service.py` (26 test cases incl. parametrized; same `autoflush=False` in-memory SQLite setup) covers: resolution by name/alias ignoring case and whitespace, unknown text → `None` with row counts unchanged, related-but-different text not resolving, blank text, `create_skill`/`add_alias` blank and collision rejection (name, alias, own name), alias happy path, ambiguous duplicate-alias data raising, and name+alias on the same skill not being ambiguous.
- `tests/test_comparison_service.py` (26 tests, same `autoflush=False` in-memory SQLite setup, using `skill_service`/`verification_service` for legitimate fixtures) covers each decision rule (unmapped, no claim, `PROVISIONAL`, `VERIFIED` with exactly its two evidence ids, `PARTIAL`, the defensive cap for evidence-less `VERIFIED`/`PARTIAL`), another user's `UserSkill` never being used, requirement-id ordering (plus a test that the SQL has an explicit `ORDER BY`, because SQLite returns id order anyway), `is_required` not affecting status, append-only snapshots, no change to `UserSkill`/evidence links, and an empty job description. The cap, user-filter, evidence-link and ordering guarantees were each mutation-checked (deliberately broken → the intended test failed).
- The 12 read-side tests in the same file cover `latest_results`/`skill_gaps`: only the highest-id result per requirement (ids asserted, history intact), ordering by requirement id (including a reverse-insertion test so incidental id order would fail, plus an SQL `ORDER BY` check), a never-compared requirement being absent with nothing auto-run, a gap disappearing after `VERIFIED` + re-run while older results remain, `VERIFIED` excluded and `PARTIAL`/`PROVISIONAL`/`NOT_VERIFIED` included, unmapped requirements as gaps with `skill is None`, required-before-optional ordering with a scrambled creation order, `is_required` not changing inclusion, scoping to one job description, no writes / no implicit comparison, and empty job descriptions. Seven mutations (lowest instead of highest id, including `VERIFIED`, silently running a comparison, ignoring `is_required` ordering, dropping `ORDER BY`, leaking other job descriptions, letting `is_required` change inclusion) were each caught by at least one test.
- `tests/test_skills_api.py` (19 test cases incl. parametrized) covers every endpoint and error path: create (201, persisted, blank → 422, collision → 409, bad body → FastAPI 422), alias (201 then resolvable, collision → 409, unknown skill → 404, blank → 422), resolve (case/whitespace-insensitive, unknown → 404 with row counts unchanged, missing param → 422, ambiguous data → 409), list ordering, rollback of a write that flushes then fails, the 400 fallback / evidence-error mapping, and `/docs` + `/openapi.json` generating. The commit-in-route and handler-registration guarantees were mutation-checked.
- **Live check (2026-09-25):** `uvicorn app.main:app` was run against the live local Postgres and every skills endpoint exercised (create, alias, resolve, unknown → 404 with nothing created, duplicate → 409, blank → 422, missing skill → 404, `/docs` 200); the rows it created were then deleted and the id sequences reset, leaving `career_ai` exactly as found (all tables empty).
- `tests/test_requirement_service.py` (16 test cases incl. parametrized; a fake extractor with a call counter, no real LLM) covers: grounded proposals stored in order with flags and stripped text; an invented requirement rejected and not stored; grounding tolerant only of case/whitespace (paraphrase rejected); blank text rejected; duplicates stored once (first wins); skill mention resolving by name and by alias; an unknown mention staying unmapped with no `Skill`/`SkillAlias` created; blank/`None` mentions; an ambiguous mention stored unmapped without failing; refusal when requirements already exist with the extractor **not called** (and reading the DB, not a stale relationship); an extractor failure storing nothing; no commit (rollback leaves nothing) and no writes to `UserSkill`/`ComparisonResult`; and an end-to-end run through `compare_job_description` and `skill_gaps`. Eight mutations (grounding disabled, guard removed, extractor called before the guard, guard reading a stale relationship, duplicate check removed, ambiguity unhandled, unknown mention creating a skill, service committing) were each caught. The API error-mapping test now also covers `RequirementsAlreadyExistError` → 409.
- `tests/test_user_service.py` (4 tests, in-memory SQLite) covers `get_or_create_default_user`: creates the user on first call; finds a *pending, unflushed* user instead of duplicating it (the exact scenario the pre-lookup flush exists for — proven by mutation-check: removing that flush raised a `UNIQUE constraint failed` `IntegrityError`); calling it twice in one session returns the same row; and two different `Session`s against the same on-disk database find the same row (proves the lookup goes through the database, not in-session object identity — uses a real temp SQLite file since two `:memory:` connections are two different databases).
- `tests/test_me_api.py` (2 tests, `TestClient` + `dependency_overrides`) covers: `GET /me` on a fresh database creates the user (row count 0→1) and returns its email; calling it twice returns the same id both times with the row count staying at 1. Removing `db.commit()` from `get_current_user` was mutation-checked and both tests failed.
- `tests/test_job_descriptions_api.py` (14 tests) covers: create-then-get round trip; `404` for a missing id and for another user's id (inserted directly, bypassing the API, to prove the check actually filters by owner and not just existence); `/extract` splitting a mix of grounded/invented/duplicate/unmapped-skill proposals into the right accepted/rejected lists, with accepted ones then visible via `GET`; extracting twice → `409` with the fake extractor's call counter proving it was **not** called the second time; extracting with the **default, non-overridden stub** → `{"accepted": [], "rejected": []}`, proving the safe placeholder is actually wired; `/compare` producing correct statuses (including a real `VERIFIED` claim built via `verification_service`/`skill_service` and an unmapped requirement), and doubling the stored count on a second call; `/gaps` empty before compare, reflecting non-`VERIFIED` requirements after, and a requirement disappearing from gaps (while the older stored result is untouched) once evidence is linked and `set_status(VERIFIED)` is applied directly and compare re-run; `404` on every id-based route for a missing/not-owned id; and `/openapi.json`/`/docs` including the five new paths. The ownership check and the stub extractor's "returns nothing" guarantee were each mutation-checked.
- `tests/test_user_skills_api.py` (15 tests) covers: claim → list, unknown skill → 404, duplicate claim → 409 with only one row, list ordering, linking evidence (visible via a follow-up load), duplicate link → 409, evidence owned by another user → 409, linking to a not-owned/nonexistent claim → 404, linking nonexistent evidence → 404, `VERIFIED` with no evidence → 409 with status unchanged, linking then verifying → 200, downgrading to `PROVISIONAL` always succeeding, a bad status value → 422, and status updates on a not-owned/nonexistent claim → 404.
- `tests/test_evidence_api.py` (8 tests) covers: create → list, a bad `evidence_type` → 422, referencing a nonexistent or another user's work-experience/education record → 404, listing only the current user's evidence, and ordering by `created_at`.
- `tests/test_cv_skill_presence.py` (5 tests incl. parametrized) covers: a presence row linking to its `User` and `Skill`; `present=True`/`False` both persisting correctly (no third "unknown" state exists — a skill with no row simply has never had its CV presence stated); the `(user_id, skill_id)` unique constraint raising `IntegrityError` on a duplicate; and independence from `UserSkill` — a presence row coexisting with no `UserSkill` at all, with a `VERIFIED` claim, and with a `NOT_VERIFIED` claim, in every combination, without conflict.
- `tests/test_cv_service.py` (15 tests incl. parametrized) covers: **all 10 cells of the decision table** (the 5 `knowledge_status` values crossed with `cv_present` `True`/`False`), asserting both `cv_status` and `recommendation` (or its absence) exactly against a hand-written expectation table; the "no row at all" case; `combined_status_for_all` including only skills with at least one row and excluding one with neither, ordered by name; scoping correctly to the given user (a second user's rows never leak in); a realistic mixed set (verified-not-on-CV, on-CV-with-no-claim, provisional-on-CV) combined correctly; and that neither function writes anything (`UserSkill`/`CVSkillPresence` row counts unchanged after calling both). Four deliberate breakages (removing the `MISSING_FROM_CV` branch, removing the "unproven but on CV" recommendation, including all skills regardless of having a row, and leaking another user's rows) were each caught by name before the file was restored byte-identical.
- **Live check (2026-09-29):** the same server pattern was walked through the exact flow requested: claim a skill, attempt `VERIFIED` with no evidence → `409`, add evidence, link it, set `VERIFIED` → `200` with `status: "verified"`. A duplicate claim also returned `409` mid-flow. `/docs`/`/openapi.json` both returned 200 and listed the new paths. The one user, skill, user-skill, evidence, and evidence-link row created were all deleted afterward (in FK-safe order) and every id sequence reset, leaving `career_ai` exactly as found (every table checked back at 0 rows).
- Full test suite: `176 passed` (`test_health.py` 1, `test_profile_models.py` 3, `test_user_skill.py` 3, `test_job_description.py` 1, `test_job_requirement.py` 2, `test_comparison_result.py` 3, `test_verification_service.py` 11, `test_skill_service.py` 28, `test_comparison_service.py` 26, `test_skills_api.py` 19, `test_requirement_service.py` 16, `test_user_service.py` 4, `test_me_api.py` 2, `test_job_descriptions_api.py` 14, `test_user_skills_api.py` 15, `test_evidence_api.py` 8, `test_cv_skill_presence.py` 5, `test_cv_service.py` 15).
- **Live check (2026-09-27):** `uvicorn app.main:app` was run against the live local Postgres; `GET /me` called twice returned `{"id": 1, "email": "me@career-ai.local", "full_name": null}` both times (same id); `/docs` and `/openapi.json` (listing `/me`) both returned 200. The one row it created was then deleted and the `users_id_seq` reset, leaving `career_ai` exactly as found (all tables empty).
- **Live check (2026-09-28):** the same server was walked through the full job-description flow: `GET /me` bootstrapped the user; `POST /job-descriptions` created a row; `GET` returned it with empty requirements; `POST .../extract` with the **default** stub extractor returned `{"accepted": [], "rejected": []}`; `POST .../compare` on zero requirements returned `[]`; `GET .../gaps` returned `[]`; `GET /job-descriptions/999999` returned `404` naming only the id. `/openapi.json` listed all five new paths and `/docs` returned 200. The one user row and one job description row created were then deleted and both id sequences reset, leaving `career_ai` exactly as found (every table checked back at 0 rows).

---

## 9. Environment-Specific Notes

- The local `.venv` was created with **Python 3.14.2**, but `pyproject.toml` requires `>=3.12,<3.13`. This mismatch hasn't caused problems in practice (tests and migrations run fine), but it's still worth recreating the venv with 3.12 at some point for strict reproducibility.
- **The project uses `pg8000` as its PostgreSQL driver — `psycopg2` is not a dependency at all anymore (switched 2026-09-29).** `DATABASE_URL` uses the scheme `postgresql+pg8000://...` (both `.env` and `.env.example` updated; `backend/requirements.txt` lists `pg8000`, not `psycopg2-binary`). Neither `database.py` nor `alembic/env.py` names a driver directly — both just read `DATABASE_URL` and hand it to SQLAlchemy — so this swap touched no application code, only the connection string and the installed dependency.
- **Why the switch happened, and why it's permanent, not a workaround:** on 2026-09-23 `psycopg2` was working fine on this machine. On 2026-09-28–29 it started failing with `ImportError: DLL load failed while importing _psycopg: An Application Control policy has blocked this file` — reproduced three times in a row, not a fluke. The Windows `Microsoft-Windows-CodeIntegrity/Operational` event log confirmed the exact cause: **Windows Smart App Control** (`VerifiedAndReputablePolicyState = 1`, enforced) blocking `psycopg2`'s compiled native extension (`_psycopg.cp314-win_amd64.pyd`) for not meeting its signing/reputation requirements. Smart App Control gives end users **no per-file exception mechanism** — the only Windows-side fix is to turn it off entirely, which is a one-way action (can't be turned back on without reinstalling Windows). Rather than take that trade-off, the project switched to `pg8000`, a pure-Python driver with no compiled extension — there's nothing left for an Application Control policy to block, on this machine or any other. This was verified against the live database (`alembic check`, full `pytest`, and a live `uvicorn` run doing a real `POST`/`GET` round trip) after the switch.
- If a similar Application-Control-style block ever appears again for some *other* compiled dependency, the same reasoning applies: prefer a pure-Python alternative over weakening a Windows security feature, when one exists.
- The real `.env` file exists and is gitignored. Do not commit it.

---

## 10. What to Build Next

### Immediate next steps (Phase 1 — Backend Foundation)

Continue building the backend incrementally. Each step should be small, tested, and explained.

1. **Create the remaining core domain models** in `backend/app/db/models/`:
   - ~~`User`~~ ✅ done 2026-09-23
   - ~~`Evidence`~~ ✅ done 2026-09-23
   - ~~`Project`~~ ✅ done 2026-09-23
   - ~~`WorkExperience`~~ ✅ done 2026-09-23
   - ~~`Education`~~ ✅ done 2026-09-23
   - ~~`UserSkill`~~ ✅ done 2026-09-23 (`app/db/models/user_skill.py`; association-object pattern for User↔Skill with a `status`/`notes` payload, `UserSkillEvidence` as a plain composite-PK join table to `Evidence`, `(user_id, skill_id)` unique constraint, defaults to `PROVISIONAL`)
   - ~~`JobDescription`~~ ✅ done 2026-09-23 (`app/db/models/job_description.py`; raw-text capture only — `title`/`company`/`source_url` are optional user-supplied metadata, no AI extraction yet. Does **not** yet reference `JobRequirement`, which is a separate not-yet-started task)
   - ~~`JobRequirement`~~ ✅ done 2026-09-25 (`app/db/models/job_requirement.py`; FK to `JobDescription`, nullable FK to `Skill` so unknown technologies stay unmapped instead of inventing skills; `requirement_text` verbatim + `is_required` flag; no verification status — that belongs to `ComparisonResult`)
   - ~~`ComparisonResult`~~ ✅ done 2026-09-25 (`app/db/models/comparison_result.py` + `ComparisonResultEvidence` join table; append-only snapshots (no unique constraint on `job_requirement_id`), nullable `user_skill_id` (null = no claim exists), `knowledge_status` has no default so the future service must decide it explicitly, evidence cited via join table; `cv_status` intentionally deferred until `CVSkillPresence` exists)
   - ~~`SkillGap`~~ ✅ done 2026-09-26 **as a derived query, not a model/table** — `comparison_service.skill_gaps` (latest `ComparisonResult` per requirement with status ≠ `VERIFIED`), see §7 and `ARCHITECTURE.md` §4. No `SkillGap` model or migration exists or is planned; a table could be added later only for gap-specific state (priority/dismissed/notes).
   - `LearningResource` — not started
   - `LearningPlan` — not started
   - `LearningProgress` — not started
   - ~~`CVSkillPresence`~~ ✅ done 2026-09-29 (`app/db/models/cv_skill_presence.py`; `(user_id, skill_id)` unique constraint, one evolving row like `UserSkill` rather than an append-only history like `ComparisonResult`; `present: Boolean` has no default — the caller must always state it explicitly; **deliberately independent** of `UserSkill`/`Evidence`/`ComparisonResult` — no FK to any of them, so a skill can be `VERIFIED` and not on the CV, or `NOT_VERIFIED` and on the CV, with no conflict — verified with real coexisting rows in `tests/test_cv_skill_presence.py`). The combined "knowledge + CV" view is now ✅ done too, at the service level — see `cv_service.py` in §7. Still pending: an API endpoint to read it, and any way to write a `CVSkillPresence` at all — no service or endpoint creates/updates one yet.

   Reference these concepts from `ARCHITECTURE.md` and `PROJECT_RULES.md`. Suggested next sub-batch: `UserSkill` alone (it's the piece that finally connects `Skill` to `User`/`Evidence` and lets verification-status rules become testable), since everything from `JobRequirement` onward depends on it existing.

2. **Generate Alembic migrations** for each new model or coherent group of models. (Convention established: one migration per model, or per tightly-coupled sibling group — see the `projects_work_experiences_educations` migration.)

3. **Create Pydantic schemas** in `backend/app/core/models.py` for request/response validation. (Partially done 2026-09-25: `SkillCreate`, `AliasCreate`, `SkillResponse`. Schemas for every other domain are still pending.)

4. **Create domain services** in `backend/app/core/services/`:
   - ~~`verification_service.py`~~ ✅ done 2026-09-25 — `link_evidence` + `set_status` (see §7). Still pending: HTTP endpoints that call it, and any `unlink_evidence`.
   - ~~`skill_service.py`~~ ✅ partially done 2026-09-25 — canonical skill lookup (`resolve_skill`) + safe creation (`create_skill`, `add_alias`) + read helpers (`list_skills`, `get_skill`), see §7. HTTP endpoints for these now exist (see item 5). Still pending: skill/alias rename/deletion.
   - ~~`comparison_service.py`~~ ✅ done 2026-09-25 — `compare_job_description`; read side added 2026-09-26 — `latest_results` + `skill_gaps` (see §7). Still pending: HTTP endpoints. `comparison_service` itself does **not** read `CVSkillPresence` — that combined view is `cv_service.py` instead, kept as its own module (see item below), not folded into `comparison_service`.
   - ~~`requirement_service.py`~~ ✅ done 2026-09-26 **at the service level with a FAKE extractor** — `extract_requirements` validates an untrusted extractor's proposals (grounding check, dedup, skill mapping only via `resolve_skill`) and stores `JobRequirement` rows (see §7). Still pending: the **real LLM provider implementation + prompt** (`app/ai/providers/`, `app/ai/prompts/`), an **API endpoint** that runs extraction, and any **re-extraction workflow** (a re-run is currently refused).
   - ~~`cv_service.py`~~ ✅ done 2026-09-29 — `combined_status` + `combined_status_for_all` (see §7). Read-only; still pending: an HTTP endpoint, and any way to write a `CVSkillPresence` at all.
   - `learning_service.py` — learning plans and progress.

5. **Create REST API endpoints** in `backend/app/api/`:
   - ~~`/skills/*`~~ ✅ partially done 2026-09-25 — `POST /skills`, `GET /skills`, `GET /skills/resolve`, `POST /skills/{id}/aliases` (see §7). Not done: `GET /skills/{id}`, rename, delete.
   - ~~`GET /me`~~ ✅ done 2026-09-27 — proof endpoint for the single-hardcoded-user bootstrap (see §7). **Every future user-scoped endpoint below can use `user: User = Depends(get_current_user)` instead of taking a `user_id` — no endpoint should ever take one as a parameter.**
   - `/experience/*`
   - `/projects/*`
   - ~~`/job-descriptions/*`~~ ✅ done 2026-09-28 — `POST ""`, `GET "/{id}"`, `POST "/{id}/extract"`, `POST "/{id}/compare"`, `GET "/{id}/gaps"` (see §7). Uses `Depends(get_current_user)`, not a `user_id` parameter, exactly as planned. Not done: `DELETE`/update, and a dedicated `/comparisons/*` (comparing and reading gaps currently live under `/job-descriptions/{id}/...` since that's the natural scope).
   - ~~`/user-skills/*`~~ ✅ done 2026-09-29 — claim, list, link evidence, status update (see §7). Not done: `DELETE`/update, unlinking evidence.
   - ~~`/evidence/*`~~ ✅ done 2026-09-29 — create, list (see §7). Not done: `DELETE`/update, and `GET /evidence/{id}`.
   - `/learning/*`

6. **Implement verification rules** (partially done — `UserSkill` rules only):
   - Only `VERIFIED` evidence can be used for factual claims. — **not done** (applies to comparison/AI layers, not built yet).
   - ~~`PARTIAL` and `PROVISIONAL` cannot be auto-upgraded.~~ ✅ done for `UserSkill`: linking evidence never changes status; promotion only via explicit `set_status`.
   - ~~Evidence traceability: every `VERIFIED` skill links to evidence records.~~ ✅ done for `UserSkill`: `set_status` refuses `VERIFIED`/`PARTIAL` with zero linked evidence. (Enforced by the service convention, not by a DB constraint; no unlink path exists yet.)

7. **Implement canonical skill taxonomy** (partially done):
   - ~~Store canonical names and aliases.~~ ✅ models exist, and `create_skill`/`add_alias` add them safely (whole-namespace uniqueness enforced in the service, not the DB).
   - ~~Distinguish exact matches from related technologies.~~ ✅ done: exact-match-only resolution; related technologies never resolve to each other. (Explicit related-skill/parent-child relationships are not modeled.)
   - ~~Backend validates final skill mapping.~~ ✅ done at the service level: `resolve_skill` is the single deterministic mapping function and `requirement_service.extract_requirements` is now its caller — it is the only way `JobRequirement.skill_id` is populated from extraction, and the extractor (LLM) can never create skills or pick ids. (Exercised only with a fake extractor; no real LLM exists yet.)

8. **Add tests** for:
   - Health endpoint (already done).
   - Verification rules (done for `verification_service`: `tests/test_verification_service.py`).
   - Skill CRUD endpoints. — done for the four skills endpoints that exist (`tests/test_skills_api.py`); no update/delete endpoints exist to test.
   - Canonical skill matching. — done for `skill_service` (`tests/test_skill_service.py`).

### Later phases (do not start yet)

- **Phase 2 — Frontend:** Next.js + TypeScript + Tailwind CSS, connect to backend APIs.
- **Phase 3 — Job Analysis:** paste job description, extract requirements, normalize to canonical skills, deterministic comparison.
- **Phase 4 — AI Integration:** LLM provider, structured outputs, resource recommendations, interview question generation.
- **Phase 5 — RAG / pgvector:** embeddings, semantic search, grounded knowledge retrieval.

---

## 11. Important Conventions for the Next Developer

- **Do not skip the foundation documents.** Read `PROJECT_RULES.md`, `ARCHITECTURE.md`, and `FOLDER_STRUCTURE.md` before making changes.
- **Do not invent user skills, experience, or proficiency.** The AI must only use stored verified data.
- **Do not let the LLM decide verification status.** That belongs to backend business rules.
- **Keep the backend simple:** `API → Service → SQLAlchemy → PostgreSQL`.
- **Avoid generic repositories** unless a concrete need arises.
- **Avoid unnecessary dependencies.** Prefer the standard stack.
- **Write tests for important verification rules.**
- **Build incrementally** and explain each step.
- **Never commit `.env` or `.venv`.**

---

## 12. Commands to Run the Project

From inside `backend/`:

```bash
# Create virtual environment (use Python 3.12)
python3.12 -m venv .venv

# Activate (Windows)
.venv\Scripts\activate

# Install dependencies
pip install -r requirements-dev.txt

# Copy environment template and fill in real values
cp .env.example .env

# Start the server
uvicorn app.main:app --reload

# Run tests
pytest
```

---

## 13. Final Note

The project is intentionally small right now. The foundation is solid, the rules are clear, and the architecture is designed to grow. The next developer should continue **backend-first**, **incrementally**, and **without violating the anti-hallucination contract**.

---

## Appendix: Prompt for the Next AI

Paste this at the top of every new conversation when continuing this project:

```text
I am building the Career AI project as a learning exercise. I am new to Python backend development.

Please follow these instructions while working on the code:

1. Explain every concept, file, and code change in simple, beginner-friendly language.
2. Use analogies and step-by-step reasoning whenever possible.
3. Do not skip explanations or assume I already understand advanced topics.
4. Before implementing, briefly explain your plan and why you chose that approach.
5. After implementing, explain what changed, how it works, and how it connects to the previous code.
6. Keep the architecture simple: API → Service → SQLAlchemy → PostgreSQL.
7. Avoid premature abstractions, generic repositories, and unnecessary dependencies.
8. Build incrementally. Do not generate large amounts of code at once.
9. Wait for my explicit approval before moving to the next step or milestone.
10. Always respect the anti-hallucination rules: the database is the source of truth, the LLM is only an assistant, and verified evidence is required for VERIFIED status.

Refer to HANDOFF.md, PROJECT_RULES.md, ARCHITECTURE.md, and FOLDER_STRUCTURE.md for project context.
```
