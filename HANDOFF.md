# Career AI — Project Handoff Document

> **Date:** 2026-09-23  
> **Current phase:** Phase 1 — Backend Foundation (in progress); Phase 2 — Frontend now has a bare skeleton (see §7)  
> **Status (updated 2026-09-29):** The verification data-entry side is now reachable over HTTP too: claim a skill (`/user-skills`), record evidence (`/evidence`), link the two, and request a status change — all thin routes over the unchanged `verification_service`. Combined with the earlier `/job-descriptions` flow (create → extract → compare → gaps), the whole loop this project exists for — claim a skill, prove it, then check it against a real job posting — is now exercisable end to end over HTTP, all scoped to the single hardcoded user via `Depends(get_current_user)`; no `user_id` ever appears in a request. `CVSkillPresence` also now exists as a model (deliberately independent of verification status — see §7), `cv_service` combines it with `UserSkill.status` into one read-only view with a recommendation, and both are now reachable over HTTP too — `PATCH /skills/{id}/cv-presence` (upsert) and `GET /skills/{id}/cv-status`. Requirement extraction's real LLM provider still does not exist (see §7). Foundation documents approved. Basic FastAPI backend skeleton created. Fourteen SQLAlchemy models now exist — `Skill`, `SkillAlias`, `User`, `Project`, `WorkExperience`, `Education`, `Evidence`, `UserSkill`, `UserSkillEvidence`, `JobDescription`, `JobRequirement`, `ComparisonResult`, `ComparisonResultEvidence`, `CVSkillPresence` — with migrations applied to a live local PostgreSQL database. Four domain services exist (`verification_service`, `skill_service`, `comparison_service`, `cv_service`), and the first HTTP endpoints (`/skills`) sit on top of `skill_service`. No AI or auth yet. **A bare, intentionally unstyled frontend skeleton now exists** (Next.js + TypeScript + Tailwind, one proof page calling `/health` and `/me`) — see the new §7 section below.
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
    │       ├── 8b7d8f0de9ae_create_cv_skill_presences_table.py
    │       ├── 9bd5ef6ad2a1_create_learning_resources_table.py
    │       └── e034a498adb5_create_learning_progress_table.py
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
    │   │   ├── cv.py                 ← POST /cv/scan (preview), PUT /cv/presence (confirmed save), GET /cv/status
    │   │   ├── learning_progress.py  ← PUT /skills/{id}/learning-progress + GET /learning-progress
    │   │   ├── learning_resources.py ← /skills/{id}/learning-resources (list, add) + DELETE /learning-resources/{id}
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
    │   │   │   ├── cv_presence_service.py   ← set_cv_presence() (the only writer of CVSkillPresence)
    │   │   │   ├── cv_import_service.py     ← extract_text() (PDF/.docx/.txt), scan_cv() (read-only)
    │   │   │   ├── cv_service.py            ← combined_status(), combined_status_for_all(), CVStatus, CombinedSkillStatus
    │   │   │   ├── learning_progress_service.py ← get/list/set_progress() (never touches UserSkill/Evidence)
    │   │   │   └── learning_service.py      ← youtube_search_url() (derived), add/list/remove_resource()
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
    │   │       ├── learning_resource.py    ← LearningResource
    │   │       ├── learning_progress.py    ← LearningProgress
    │   │       └── enums.py        ← EvidenceType, VerificationStatus, LearningMode, LearningStatus
    │   └── ai/                 ← extractor interface, schemas, and two implementations
    │       ├── __init__.py
    │       ├── client.py       ← RequirementExtractor (typing.Protocol)
    │       ├── providers/
    │       │   ├── __init__.py
    │       │   ├── skill_list_extractor.py  ← SkillListExtractor (deterministic, no AI; the default)
    │       │   └── claude_extractor.py      ← ClaudeRequirementExtractor (used only when ANTHROPIC_API_KEY is set)
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
        ├── test_cv_service.py
        ├── test_skills_cv_api.py
        ├── test_learning_resources_api.py
        ├── test_learning_progress_api.py
        └── test_cv_api.py
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

**Endpoints** (`app/api/skills.py`, router prefix `/skills`; each route uses `db: Session = Depends(get_db)`, except the two CV routes below which are per-user):

| Method + path | Calls | Success | Notes |
|---|---|---|---|
| `POST /skills` | `create_skill` | `201` `SkillResponse` | body `{name, category?}` |
| `GET /skills` | `list_skills` | `200` `list[SkillResponse]` | ordered by name |
| `GET /skills/resolve?text=...` | `resolve_skill` | `200` `SkillResponse` | `404 {"detail": ...}` if no match; **read-only, never creates anything**; declared before any future `/{skill_id}` GET so it cannot be shadowed |
| `POST /skills/{skill_id}/aliases` | `get_skill` + `add_alias` | `201` `SkillResponse` (updated skill) | body `{alias}`; `404` if the skill id doesn't exist |
| `PATCH /skills/{skill_id}/cv-presence` | *(upsert, no service call — see below)* | `200` `CVPresenceResponse` | body `{present}`; `404` if the skill id doesn't exist; **user-scoped** (`Depends(get_current_user)`) |
| `GET /skills/{skill_id}/cv-status` | `cv_service.combined_status` (unmodified) | `200` `CVStatusResponse` | `404` if the skill id doesn't exist; **user-scoped**, read-only, no commit |

**The two CV routes, added 2026-09-29:** finally give `CVSkillPresence` and `cv_service` a way to be reached over HTTP (both existed before this with no endpoint at all). `PATCH .../cv-presence` is an **upsert**, deliberately unlike `claim_skill`'s check-then-`409` in `user_skills.py`: restating a fact about your own CV isn't a conflict the way a duplicate skill claim is, and `CVSkillPresence`'s `(user_id, skill_id)` unique constraint already guarantees at most one row — the route looks the row up, updates `present` in place if found, creates it if not, then commits. There is no service call here because there's no business rule beyond "the skill must exist" — same reasoning as `JobDescription`'s and `Evidence`'s own creation having no service. `GET .../cv-status` calls `cv_service.combined_status` exactly as it already existed (not modified) and does not commit, same reasoning as `GET .../gaps` in `job_descriptions.py`: nothing to commit, and the one write a request could ever need (bootstrapping the user) already happened inside `get_current_user`.

**Conventions**
- **Routes are thin:** they call `skill_service` (or, for the two CV routes, `cv_service`/`CVSkillPresence` directly, since there's no business rule to delegate to a service) and nothing else — no business rules in the route, **no `try/except` for `DomainError`**.
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

**The stub extractor (`app/ai/providers/stub_extractor.py`) — REMOVED 2026-10-01, replaced as the default by `SkillListExtractor`; see "The skill-list matcher" section below.** Historical description: `NoOpRequirementExtractor` — **a TEMPORARY placeholder**, always returns zero proposed requirements. It never guesses, matching the same anti-hallucination stance as everything else in this project. It's wired as the *default* via `get_requirement_extractor` in `app/dependencies.py`, a module-level singleton (it holds no state) — so `/extract` is a real, provable endpoint today. **Swapping in a real LLM-backed provider later means changing only that one dependency; no endpoint or service changes.** Tests override the dependency with a fake extractor to exercise real accept/reject behavior over HTTP.

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

### Frontend skeleton: `frontend/`, plus CORS in `backend/app/main.py`

Added 2026-09-29 — Phase 2 begins with the bare minimum needed to prove the frontend can talk to the backend at all. **This is intentionally unstyled** — no component library, no design system, one plain page. A real design pass is a separate, later task.

- **`frontend/`** — a standard `create-next-app` scaffold: App Router, TypeScript, Tailwind CSS, ESLint, matching `FOLDER_STRUCTURE.md`'s documented `app/`, `public/`, `package.json`, `tsconfig.json` layout. Two things `FOLDER_STRUCTURE.md` also lists — `components/` and `styles/` — were **not** created: nothing in this task needed them, and creating empty directories ahead of an actual feature would be the same kind of premature structure the backend has avoided throughout (no generic repository, no unused abstractions). `tailwind.config.ts` also doesn't exist: this Next.js version ships Tailwind v4, which configures via CSS (`app/globals.css` + `postcss.config.mjs`) rather than a JS/TS config file — `FOLDER_STRUCTURE.md` predates that change.
- **`frontend/lib/api.ts`** — one small typed helper, `apiGet<T>(path)`, plus an `ApiError` class carrying the HTTP status. Base URL from `NEXT_PUBLIC_API_BASE_URL` (the `NEXT_PUBLIC_` prefix is required by Next.js for any env var that needs to be readable in the browser, not just during the server build), defaulting to `http://127.0.0.1:8000`. `frontend/.env.local.example` documents it, same pattern as `backend/.env.example`; a real `frontend/.env.local` is gitignored (the root `.gitignore` already covers `.env.local`/`.env.*.local` at any depth, so nothing needed adding there).
- **`frontend/app/page.tsx`** — replaces the default scaffold page entirely. A client component (`"use client"`) that calls `GET /health` and `GET /me` on load via `useEffect`, and renders one of three states: loading, loaded (prints the raw JSON), or error. No routing, no other pages. (Its inline `style={{...}}` was later replaced with Tailwind utility classes once the design tokens below existed — see the next section.)
- **CORS (`backend/app/main.py`)** — `CORSMiddleware` added, allowing only `http://localhost:3000` and `http://127.0.0.1:3000`. Deliberately **not** `"*"`: there's no auth yet, so this stays a narrow, explicit allow-list, commented in the code as dev-only and due for revisiting once real auth exists. No other backend behavior changed — confirmed by the full test suite still passing (185 tests) and `alembic check` still reporting no drift.
- **Verified end to end**, from the command line (no real browser/screenshot tooling available in this environment): `npm run build` compiles and type-checks with no errors; with both dev servers running, `curl http://127.0.0.1:8000/health` and `.../me` returned real data from the live database; an `OPTIONS` preflight from `Origin: http://localhost:3000` came back with `access-control-allow-origin: http://localhost:3000`, confirming the CORS allow-list actually works; `curl http://localhost:3000/` returned the correct server-rendered HTML shell (title, the page's own markup, the initial "Loading…" text) — the post-fetch rendered data itself only appears after client-side JavaScript runs in a real browser, which `curl` cannot execute, so that specific detail is asserted by code review and the direct backend `curl` checks above, not observed directly.
- **A harmless side effect worth knowing about:** running `next dev` auto-generates `frontend/AGENTS.md` and `frontend/CLAUDE.md` — Next.js's own notice to AI coding tools about this Next.js version's API changes, regenerated by `next dev` every time it runs (the file says as much). Left in place rather than fought, since deleting it would just have it reappear on the next `npm run dev`.
- **Still pending (as of this task):** any real page beyond the proof page, `components/`/`styles/` (only when an actual feature needs them), a real design pass, and connecting any of the existing backend endpoints beyond `/health`/`/me`. **All addressed by the next section, added the same day.**

### Design tokens, shared header, and the first real page: `/skills`

Added 2026-09-29 — the first page that's actually functional, not just a proof of connection: it lists real skills, shows real verification/CV status, and lets you create a skill and toggle CV presence, all against the unmodified backend. No backend change in this task; CORS already allowed it.

- **Design tokens (`frontend/app/globals.css`)** — colors and fonts defined **once**, as Tailwind v4 theme variables (`@theme`), not a `tailwind.config.ts` (see the note in the previous section on why this Next.js version doesn't use one). Every `--color-x` variable automatically becomes Tailwind utilities `bg-x`/`text-x`/`border-x`; every `--font-x` becomes `font-x`. Colors: `ground`/`surface`/`ink`/`ink-soft`/`line` (neutrals), `accent`/`accent-soft` (teal), `warm`/`warm-soft` (amber), and four status pairs — `verified`, `partial`, `provisional`, `not-verified` (each with a matching `-bg`). Fonts, via `next/font/google` (not a manual `<link>`, so Next.js self-hosts them): **Fraunces** → `font-display` (headings), **IBM Plex Sans** → `font-sans` (body, the default), **IBM Plex Mono** → `font-mono` (badges/data labels). The scaffold's original Geist fonts and light/dark `--background`/`--foreground` scheme were removed — no dark palette was specified in this task, so introducing a half-finished dark mode would have meant guessing colors nobody gave.
- **`frontend/components/AppHeader.tsx`** — the wordmark, three nav links (`Dashboard` → `/`, `Skills` → `/skills`, `Job Descriptions` → `/job-descriptions`, the last one a deliberate 404 for now — no page exists yet), and a user-email chip. Wired into `app/layout.tsx` once, so it appears above every page automatically — **`app/page.tsx` itself needed no edit for the header to appear above it**, only for its own inline styles to be replaced with the new tokens.
- **`frontend/lib/useMe.ts`** — the `GET /me` fetch-and-three-state logic already proven on the home page, pulled out into one small reusable hook rather than copy-pasted a second time for the header's chip. The home page's own `/health` + `/me` proof code was **left as its own inline logic, unchanged** — it's a different use case (showing the raw JSON of both calls together, not just an email), so sharing the hook there too would have meant restructuring proven code for a debatable gain; not done.
- **`frontend/lib/types.ts`** — `Skill`, `CVStatus` (the three-value string union), `CVStatusResponse`, and `User`, copied field-for-field from `backend/app/core/models.py`. `User` wasn't named in the task's own list but was needed by both `useMe` and the pre-existing home page, so it was added as a small, clearly-justified extra rather than left undefined.
- **`frontend/lib/api.ts`** — gained `apiPost`/`apiPatch` alongside the existing `apiGet`, all three now sharing one internal `request` helper. Error handling was tightened here too: if the backend's error body has a plain string `detail` (which is exactly what `EmptySkillTextError`/`SkillNameCollisionError` produce — see `app/api/errors.py`), that exact message becomes the thrown `ApiError`'s message, instead of a generic "responded with 409".
- **`frontend/app/skills/page.tsx`** — the page itself:
  - Fetches `GET /skills`, then — for every skill — a separate `GET /skills/{id}/cv-status`. **This is a deliberate N+1 request pattern**, called out rather than hidden: at this scale (a handful of skills) it's harmless, and there's no "cv-status for all skills at once" endpoint to use instead; building one would be adding a new backend endpoint this task explicitly wasn't scoped for.
  - Renders a table: name, category, a knowledge-status badge, and a **clickable** CV-status badge (a real `<button>`, not just styled text) that calls `PATCH .../cv-presence` to flip `present` and refetches just that one row — the rest of the table doesn't reload.
  - A small form (name + optional category) calling `POST /skills`; on a `409` (duplicate) or `422` (blank name) it shows the backend's own `detail` message inline, not a generic one.
  - **Two small color choices that weren't specified by the task, made and noted here:** a skill with `knowledge_status: null` (no claim at all) gets a neutral `line`/`ink-soft` badge labeled "no claim" — deliberately not reusing any of the four real status colors, since none of them mean "no claim exists." The three `cv_status` values also had no assigned colors in the task's token list, so `present` → `accent` (teal, positive), `missing_from_cv` → `warm` (amber, the actionable one), `not_present` → neutral, matching the same reasoning as the "no claim" choice.
- **Verified**, from the command line (same limitation as before — no browser/screenshot tooling here): `npm run build` compiled and type-checked with no errors (routes `/`, `/skills` both listed). Rather than relying on `curl`ing `/skills`' raw HTML (which — like the home page — only shows the pre-fetch "Loading…" shell, since this is a client component), the exact sequence of backend calls the page makes was reproduced by hand: created a real skill via `curl`, fetched its `cv-status` (`knowledge_status: null`, `cv_status: "not_present"`, matching the "no claim" / neutral badge), `PATCH`ed `present: true` and refetched (`cv_status` flipped to `"present"`), and triggered both the `409` duplicate-name and `422` blank-name cases directly — all four responses matched exactly what the page's code would render. The compiled JS bundle for `/skills` was also checked directly and confirmed to contain the `cv-status`/`cv-presence`/`skills` path fragments. The backend test suite was re-run (185 passed, unchanged) to confirm nothing there was touched.
- **A live-database note:** verification was run against dev servers the user already had running from a previous session (both ports were already in use, and a `users` row already existed) — those servers and that pre-existing row were left completely alone; only the one skill (and its resulting CV-presence row) created *for this verification* were deleted afterward, confirmed back to 0 rows.
- **Still pending (as of this task):** the Dashboard and Job-Descriptions pages (both link 404 for now), a skill-detail view, alias UI, a real design/visual pass beyond having the tokens defined, and a "no claim"/CV-status color decision that's mine, not the task's, so worth a second look later. **The Job-Descriptions page is addressed by the next section, added the same day.**

### The second real page: `/job-descriptions`, and a shared `StatusBadge`

Added 2026-09-29 — the second functional page, wired to the same unmodified backend. No backend change in this task either.

- **`frontend/components/StatusBadge.tsx`** — the knowledge-status badge (verified/partial/provisional/not-verified/"no claim") was, until now, written once inline inside `app/skills/page.tsx`. Since this new page needs the exact same badge, that logic was pulled out into its own small component (`status: string | null` in, colored `<span>` out) rather than being copy-pasted a second time. `app/skills/page.tsx` was updated to import and use it — its own copy of `knowledgeBadgeClasses`/`knowledgeBadgeLabel` was deleted, nothing else there changed.
- **`frontend/lib/types.ts`** — gained `JobDescription`, `JobRequirement`, `ExtractionResponse`, `ComparisonResult`, and `Gap`, copied field-for-field from `backend/app/core/models.py`'s `JobDescriptionResponse`/`JobRequirementResponse`/`ExtractionResponse`/`ComparisonResultResponse`/`GapResponse`.
- **`frontend/app/job-descriptions/page.tsx`** — the page itself:
  - A form: a required textarea for the raw job text, plus optional title/company/source-url fields.
  - On submit, it calls four backend endpoints **in sequence, waiting for each to finish before starting the next**: `POST /job-descriptions` (create) → `POST .../extract` → `POST .../compare` → `GET .../gaps`. A small "Creating…" / "Extracting…" / "Comparing…" / "Loading gaps…" label tracks which step is currently running, so a slow step doesn't look like the page has frozen.
  - **Extraction currently always returns zero accepted requirements, by design** — there's no real AI reader wired in yet, only a safe placeholder (`NoOpRequirementExtractor`, see §13) that refuses to invent requirements rather than guess badly. The page treats this as the expected, honest case: it shows a plain explanatory note ("No requirements were found. The real AI reader isn't connected yet…") instead of an error banner. If requirements ever are accepted (once a real extractor exists), the page renders each one with `StatusBadge` (matched to its comparison result by `job_requirement_id`) and a gaps list below it, each gap showing the requirement text, its status badge, and the mapped skill name (or "not mapped to a skill" when `skill_name` is `null`).
  - **No list/history page** — the backend has no `GET /job-descriptions` (list-all) endpoint, only `GET /job-descriptions/{id}`, so this page is deliberately single-shot: analyze one, see its results, then "Analyze another job description" just clears the form and results state. A real list page is a **noted gap for later**, not something added here.
  - Real errors (e.g. a `409` if requirements somehow already exist for that job description) show the backend's own `detail` message, same pattern as the Skills page's form errors.
- **Verified**, from the command line: `npm run build` compiled and type-checked cleanly (routes `/`, `/skills`, `/job-descriptions` all listed). The exact four-call sequence was reproduced by hand against the live backend: `POST /job-descriptions` with real text (`201`, got back id `1`), `POST .../extract` → `{"accepted":[],"rejected":[]}` (confirms the "no requirements found" honest-message branch is what a real run hits today), `POST .../compare` → `[]`, `GET .../gaps` → `[]` — all matching exactly what the page's code renders for this case. The backend test suite was re-run (185 passed, unchanged) to confirm nothing there was touched.
- **A live-database note:** run against the same already-running dev servers as the previous task; the one job description created for this verification (id `1`) was deleted afterward and its id sequence reset to `1`, with row counts confirmed back to the pre-verification baseline (1 pre-existing user, 0 job descriptions/requirements/comparison results).
- **Still pending (as of this task):** the Dashboard page, a skill-detail view, alias UI, a real design/visual pass, and — as noted above — a job-descriptions list/history endpoint and page. **The skill-detail view is addressed by the next section, added the same day.**

### The third real page: `/skills/{id}`, plus one small precedented backend field

Added 2026-09-29 — the page where the anti-hallucination rule (`PROJECT_RULES.md` §4: `VERIFIED` requires real, reviewable evidence) becomes something you can click and watch enforced live, not just read about.

- **The one backend change:** `UserSkillResponse` (in `app/core/models.py`) gained `evidence_ids: list[int]`, populated by the same `model_validator(mode="before")` pattern already used by `ComparisonResultResponse.evidence_ids` — read the raw ORM object's `.evidence_links` relationship and pull each link's `evidence_id`, since `UserSkill` has no `.evidence_ids` attribute of its own for a per-field `from_attributes` lookup to find. No migration, no new route — every `/user-skills` route already returns the ORM object as-is, so the new field appears automatically. The full backend test suite was re-run after this change (still **185 passed** — nothing asserted `UserSkillResponse`'s exact JSON body, so nothing needed updating, only confirming).
- **`frontend/lib/types.ts`** — gained `UserSkill` (mirroring the new backend shape, including `evidence_ids`) and `Evidence`, copied field-for-field from `EvidenceResponse`.
- **`frontend/app/skills/[id]/page.tsx`** — a Next.js dynamic route (folder name `[id]`), built as a client component using the `useParams()` hook from `next/navigation` rather than an async `params` prop — the recommended way to read a route parameter from a Client Component on this Next.js version, and simpler than unwrapping a `Promise` for a page that's client-rendered anyway.
  - **No `GET /skills/{id}` endpoint exists**, so the one skill is found by fetching the full `GET /skills` list and searching it for the matching id — the same *kind* of trade-off as the Skills page's N+1 pattern, just applied to a lookup instead of a batch of them; not worth adding a new backend endpoint for.
  - If `GET /user-skills` has no claim for this skill yet, the page shows "You haven't claimed this skill yet" and a button that calls `POST /user-skills`.
  - Once a claim exists: its `evidence_ids` are cross-referenced against the full `GET /evidence` list to split it into "linked" (shown with type/title/description) and "your other evidence" (each with its own `Link` button calling `POST /user-skills/{id}/evidence-links`).
  - **Creating evidence and linking it are two separate, visible actions** — the "add new evidence" form only calls `POST /evidence`; it never auto-links what it just created. This mirrors how the backend itself keeps `POST /evidence` and `POST /user-skills/{id}/evidence-links` as two distinct endpoints rather than one that does both — the frontend doesn't paper over a real architectural separation just for convenience.
  - **The status control never disables a button based on a client-side guess.** All four buttons (Verified / Partial / Provisional / Not verified) are always clickable; clicking one just calls `POST /user-skills/{id}/status` and shows whatever the backend actually decides. This was a deliberate choice, not an oversight: if the page pre-blocked "Verified" whenever it *guessed* there wasn't enough evidence, the demo would only be proving the frontend's guess matched the backend's rule, not that the backend's rule is what's actually running. Letting a real click hit a real `409` is the whole point.
  - The `EvidenceType` dropdown hardcodes the same five values as the backend's `EvidenceType` enum — the same small, already-accepted kind of duplication `StatusBadge`/`VerificationStatus` already has, not a new one.
- **`frontend/app/skills/page.tsx`** — the only change here: each row's skill name is now a `<Link href={"/skills/" + id}>` to its detail page. Nothing else in that file was touched.
- **Verified**, from the command line: `npm run build` compiled and type-checked cleanly, with `/skills/[id]` listed as a dynamic (`ƒ`) route (expected — it has no `generateStaticParams`, so Next.js renders it on demand rather than pre-building one page per skill id, which is correct for data that changes at runtime). The full claim-to-verify flow was reproduced by hand against the live backend: created a skill (`Kubernetes`, id `1`) → confirmed `GET /skills/1/cv-status` showed `knowledge_status: null` (the "not claimed yet" branch) → claimed it (`POST /user-skills`, `evidence_ids: []`) → attempted `POST /user-skills/1/status {"status":"verified"}` and got the real `409` ("UserSkill 1 cannot be VERIFIED: no linked evidence. Not enough verified information.") → created a piece of evidence and linked it (`evidence_ids: [1]`) → retried the same status call and got `200` with `status: "verified"`. Every response matched exactly what the page's code renders for that state. The backend test suite was re-run once more after this live sequence (185 passed, unchanged).
- **A live-database note:** run against the same already-running dev servers as the prior two tasks. Cleanup required deleting in dependency order (the `user_skill_evidence` link row before the `user_skills` row it points to, a straightforward foreign-key ordering issue, not a design problem) — all test rows (1 skill, 1 user-skill claim, 1 evidence record, 1 link) were deleted and their id sequences reset, with row counts confirmed back to the pre-verification baseline (1 pre-existing user, 0 everywhere else).
- **Still pending (as of this task):** the Dashboard page, alias UI, a real design/visual pass, a job-descriptions list/history endpoint and page, and any UI for citing a `work_experience_id`/`project_id`/`education_id` when creating evidence (left `null`/unset in this task, as specified). **The Dashboard and the job-descriptions list endpoint are addressed by the next section, added the same day — this closes out the frontend's currently planned scope (Dashboard, Skills, Job Descriptions, Skill Detail are all real pages now).**

### The Dashboard, and the one missing list endpoint: `GET /job-descriptions`

Added 2026-09-29 — replaces the original `/health`+`/me` proof-of-connection home page with a real summary screen, and fills the one gap flagged in the last two tasks: there was no way to ask the backend for "all of my job descriptions," only one at a time by id.

- **The one backend addition:** `GET ""` on `job_descriptions.py`, copying the exact shape of the existing `GET ""` list routes on `skills.py`/`user_skills.py`/`evidence.py` — `user: User = Depends(get_current_user)`, returns `list[JobDescriptionResponse]` scoped to `JobDescription.user_id == user.id`, ordered by `created_at.desc()`. **A real correctness fix found along the way, not just a test workaround:** ordering by `created_at` alone ties when two rows share the same timestamp (SQLite's `CURRENT_TIMESTAMP` only has second resolution, so three job descriptions created in the same test all got an identical value — but two near-simultaneous inserts could tie in Postgres too), which left "most recent first" undefined for ties. Added `JobDescription.id.desc()` as a secondary sort key, same idea as `skill_service.list_skills`'s existing `order_by(Skill.name, Skill.id)` tiebreaker, so the order is deterministic regardless of clock resolution. No migration — no schema change, just a new way of reading existing rows.
- **Tests added to `test_job_descriptions_api.py`:** empty list on a fresh database; three created job descriptions come back most-recent-first (this is the test that caught the tie-breaking bug above); a job description belonging to a different user (inserted directly, bypassing the API) never appears in the current user's list. Full suite: **188 passed** (185 + these 3 new ones).
- **`frontend/app/page.tsx`** — completely replaced. The old `/health`+`/me` JSON-dump proof code is gone (its only remaining trace is that `GET /me`'s result still shows up via `AppHeader`'s email chip, which was already independent of this page). The new Dashboard:
  - Fetches `GET /user-skills` and counts claims with `status === "verified"`.
  - Fetches the new `GET /job-descriptions` (already most-recent-first, so no client-side sorting needed).
  - For **every** job description, fetches `GET /job-descriptions/{id}/gaps` and sums the counts — the same N+1-per-item trade-off already accepted twice before (Skills page's per-skill `cv-status`, Skill Detail's full-list-then-find), now used a third time. This is read-only and triggers no new comparisons.
  - For **every** skill, fetches `GET /skills/{id}/cv-status` and collects every non-null `recommendation`, capped at 5 (`MAX_RECOMMENDATIONS`) so a large skill list doesn't turn this section into a second full page.
  - Renders three stat cards (verified skills / open gaps / job descriptions analyzed) with honest zeros when there's nothing yet — never a placeholder number.
  - **Recent comparison section:** shows the most recent job description's title/company and its gaps, rendered exactly like the Job Descriptions page already renders a gap list (requirement text + `StatusBadge` + skill name, reusing the same component). If there are no job descriptions at all, an empty-state message links to `/job-descriptions` instead. There is still no job-description detail/list route to link a *specific* comparison to (the known, already-documented gap from the previous task) — only the single most recent one is shown inline here, nothing is a clickable link into a page that doesn't exist yet.
  - **CV recommendations section:** lists the collected recommendation strings, or an honest "No CV recommendations right now." message if there are none.
- **Verified**, from the command line: `npm run build` compiled and type-checked cleanly. The real flow was reproduced by hand against the live backend: created two job descriptions ("Backend Role"/Acme, then "DevOps Role"/Globex) → `GET /job-descriptions` returned `[DevOps Role, Backend Role]` (most recent first, confirmed by id order `[2, 1]`) → replayed every remaining Dashboard call (`GET /user-skills` → `[]`, `GET /job-descriptions/2/gaps` and `/1/gaps` → both `[]`, `GET /skills` → `[]`) confirming the Dashboard would show `0` verified / `0` open gaps / `2` analyzed, "DevOps Role — Globex" with "No gaps — every requirement is verified," and "No CV recommendations right now." for this exact real state. The backend test suite was re-run after cleanup (188 passed, unchanged).
- **A live-database note:** run against the same already-running dev server as the prior tasks. Both test job descriptions were deleted afterward and the id sequence reset, with row counts confirmed back to the pre-verification baseline (1 pre-existing user, 0 everywhere else).
- **Still pending (as of this task):** alias UI, a real design/visual pass, a job-descriptions detail/list *page* (the backend list endpoint now exists, but nothing yet links to it or paginates it — the Dashboard only ever shows the single most recent one inline), and any UI for citing a `work_experience_id`/`project_id`/`education_id` when creating evidence. **The real requirement extractor is addressed by the next section, added the same day.**

### The real requirement extractor (Claude-backed), with automatic, zero-cost fallback

Added 2026-09-29. **NOT YET LIVE-TESTED — there is no `ANTHROPIC_API_KEY` configured anywhere in this project, on purpose, and this task made zero real calls to the Anthropic API at any point.** Everything below was verified without a network call; the section ends with the exact steps to actually try it once a real key exists.

- **`backend/app/ai/providers/claude_extractor.py`** (new) — `ClaudeRequirementExtractor`, implementing the same `RequirementExtractor` protocol `NoOpRequirementExtractor` already implements. Its `extract_requirements` builds a prompt that explicitly instructs Claude to copy each requirement phrase **verbatim** from the job text — never paraphrase or reword — and calls `client.messages.parse(model=MODEL, max_tokens=4096, messages=[...], output_format=ExtractionResult)`, the Anthropic SDK's structured-output helper. `ExtractionResult` (the existing Pydantic class from `app/ai/schemas.py`) is passed directly as `output_format` — no hand-written JSON schema — and `response.parsed_output` is returned as-is.
  - **Why verbatim copying matters, specifically:** `requirement_service`'s grounding check (see §7 and its own docstring) rejects any proposal whose text doesn't literally appear as a substring of the job description's raw text. A model that paraphrases ("experience with backend frameworks" instead of quoting "3+ years with Django") would have every one of its proposals rejected, not because the check is broken, but because paraphrasing is indistinguishable from fabrication to a substring check — and that check is strict *on purpose* (a real requirement getting rejected costs some recall; a fabricated one getting silently accepted would violate the whole project's anti-hallucination rule). The prompt is written the way it is specifically so the real model's output has a chance of passing a check that was never loosened to accommodate it.
  - **Model:** a module constant, `MODEL = "claude-haiku-4-5"` — the cheapest current model, chosen deliberately for this task; changing models later means editing this one line, nothing else.
  - **No `thinking` or `output_config.effort` params are passed** — Haiku 4.5 doesn't support either, and the API rejects the request if they're present; only `model`, `max_tokens`, `messages`, `output_format` are sent.
  - **The `anthropic.Anthropic()` client is constructed lazily**, only inside `extract_requirements`, never at import time, never in `__init__`, never as a module or class-level value. This is the single most important design choice in this task: every test file that uses `TestClient(app)` imports this module transitively (via `app/dependencies.py`), so if the client were built eagerly, the *entire test suite* would require a real API key just to load — even though tests never call the real extractor. Confirmed by grepping the whole backend for `anthropic.Anthropic(` — the only match is inside the method body (see Verified, below).
- **`app/dependencies.py`'s `get_requirement_extractor`** — the one wiring point, updated to check `os.getenv("ANTHROPIC_API_KEY")`: truthy (a real, non-empty key) returns a new `ClaudeRequirementExtractor()`; falsy (unset, today's state) returns the exact same pre-existing `_requirement_extractor` singleton as before this task — **byte-for-byte the same behavior as yesterday** when no key exists. `database.py`'s `load_dotenv()` (already run at import time, unrelated to this task) is what makes a real `.env` key visible to `os.getenv` here.
- **`backend/requirements.txt`** gained `anthropic`; **`backend/.env.example`** gained a commented-out, empty `ANTHROPIC_API_KEY=` line explaining the safe fallback.
- **`backend/tests/test_claude_extractor.py`** (new, 3 tests, all using `monkeypatch` to control the environment regardless of what's actually set locally — **none make a network call**):
  1. With the key deleted from the environment, `get_requirement_extractor()` still returns a `NoOpRequirementExtractor` — proving no behavior change today.
  2. `ClaudeRequirementExtractor()` can be constructed with no key present, without raising — proving the client really is lazy (if `anthropic.Anthropic()` were built in `__init__`, this test would fail immediately without a key). `extract_requirements` is deliberately never called in this test.
  3. With the key monkeypatched to a fake value (`"test-key-not-real"`), `get_requirement_extractor()` now returns a `ClaudeRequirementExtractor` instance — proving the wiring switches correctly. `extract_requirements` is still never called.
- **Verified**, from the command line, with **no `ANTHROPIC_API_KEY` set anywhere in the real environment** (checked directly: absent from both `.env` and the shell before running anything) — this is the specific, critical claim this task exists to prove, not an incidental detail:
  - Full backend suite: **191 passed** (188 + these 3 new tests), with the key genuinely absent the whole time.
  - `python -c "from app.main import app"` succeeded with no key set, confirming app *startup* itself — not just the test suite — is completely unaffected by this change.
  - `grep -rn "anthropic\.Anthropic(" backend` found exactly one match, inside `ClaudeRequirementExtractor.extract_requirements`'s method body — no other construction site anywhere, confirming the laziness claim by reading the code rather than just asserting it.
- **What was deliberately never done, per explicit instruction:** no real call to the Anthropic API, at any point, for any reason, including a "quick sanity check" — there is no key configured, and none was added. The prompt's actual quality (does Claude really quote verbatim, does it correctly leave `skill_mention` null when appropriate) is **completely unverified** and will only be known once a real key exists and a real job description is run through it.
- **To actually try it later, once a real key exists** (not done as part of this task):
  1. Add a real key to `backend/.env`: `ANTHROPIC_API_KEY=sk-ant-...`.
  2. Restart the backend (`uvicorn app.main:app --reload`).
  3. Use the app exactly as before — paste a job description on `/job-descriptions`, click Analyze. No frontend change, no other backend change; `get_requirement_extractor` picks up the real extractor automatically.
  4. Check the response: `extraction.accepted` should now contain real, verbatim-quoted requirements instead of always being empty — and any proposal Claude invents or paraphrases should still show up in `rejected` with a `"not found in job description text"` reason, proving the grounding check still guards a real model exactly as it guarded the placeholder.

### The skill-list matcher: `SkillListExtractor`, the new default extractor

Added 2026-10-01. Replaces `NoOpRequirementExtractor` as the no-key default, so extraction, comparison, gaps and the Dashboard now produce real data for free. No AI is involved. (The sections above that say "extraction always returns zero" or "no key returns `NoOpRequirementExtractor`" describe the state before this change.)

- **`app/ai/providers/skill_list_extractor.py`** — `SkillListExtractor(terms_by_skill)`. It is given `{canonical name: [name, *aliases]}` as plain strings and proposes one `ExtractedRequirement` per skill found in the text. Its `text` and `skill_mention` are both the exact matched substring, and `is_required` is always `True`.
  - **Always grounded:** because it only copies text, every proposal passes `requirement_service`'s grounding check. Because `skill_mention` is a registered name or alias, the existing `resolve_skill` maps it without any new mapping code. `requirement_service` itself is unchanged.
  - **Term boundaries:** a term can't sit next to a letter, digit, `_`, `+` or `#` (`_TERM_CHAR = r"[\w+#]"`). So "Java" doesn't match inside "JavaScript", and "C" doesn't match inside "C++" or "C#". `.` is deliberately not a boundary character, so "Node.js." still matches at the end of a sentence. The trade-off is that a skill named "Node" would match inside "Node.js".
  - **Case:** matching ignores case, except terms of `SHORT_TERM_MAX_LENGTH = 2` characters or fewer ("Go", "R", "C#"), which must match exactly. Known limitation: a capitalized "Go" at the start of a sentence still matches.
  - **Whitespace:** words in a multi-word term match across any whitespace run.
  - **Deduplication:** one proposal per skill, from its earliest-matching term, returned in text order.
- **`skill_service.skill_terms(db)`** — new read-only helper that builds that mapping from `list_skills`.
- **`get_requirement_extractor(db: Session = Depends(get_db))`** — now takes the request's `Session`. FastAPI caches `get_db` per request, so this is the same session the route uses. If `ANTHROPIC_API_KEY` is set it returns `ClaudeRequirementExtractor()` (unchanged); otherwise `SkillListExtractor(skill_service.skill_terms(db))`. The matcher gets a string snapshot and never holds the session. That preserves `client.py`'s rule that an extractor "knows nothing about the database": the dependency reads the taxonomy, not the extractor. With no skills saved it proposes nothing, which is exactly as safe as the removed placeholder.
- **Removed:** `app/ai/providers/stub_extractor.py` (`NoOpRequirementExtractor`), which nothing referenced any more.
- **Frontend:** `/job-descriptions`'s zero-requirements message no longer says "the real AI reader isn't connected yet". It now says none of your saved skills appear in the posting, and links to `/skills`.
- **Tests:**
  - new `tests/test_skill_list_extractor.py` (10 tests):
    - case-insensitive match using the text's own words
    - empty taxonomy
    - whole terms (Java/JavaScript)
    - C vs C++/C#
    - `Node.js.` at the end of a sentence
    - short terms needing an exact match
    - multi-word terms across whitespace
    - aliases collapsing to the earliest match
    - text order
    - default wiring with no key, using a real taxonomy including an alias

    Every case also asserts that each proposal's text is a literal substring of the input.
  - `test_claude_extractor.py`: its "no key → placeholder" test was removed (that case moved to the new file), and the key-switch test now passes a SQLite `Session`.
  - `test_job_descriptions_api.py`: the "default stub accepts nothing" test was renamed for the no-skills case. A new HTTP test uses the real default wiring: skills Python, Java, and PostgreSQL with alias Postgres; the posting "Need Postgres and Python; JavaScript is a plus." gives accepted `[("Postgres","PostgreSQL"), ("Python","Python")]`.
  - Suite total: **201 passed**, run with no `ANTHROPIC_API_KEY` present.
- **Mutation check:** setting `_TERM_CHAR` to `r"[#]"` (weakening the boundaries) made exactly `test_matches_whole_terms_only` and `test_c_is_not_found_inside_c_plus_plus_or_c_sharp` fail. The file was restored byte-identical.
- **Live check** (no dev server was running, so a temporary `uvicorn` was started on :8000 and stopped afterwards):
  - Created Python, PostgreSQL (alias Postgres) and Docker.
  - Posted "We need strong Python and Postgres experience. JavaScript is a plus. Docker knowledge preferred."
  - `/extract` accepted Python, Postgres→PostgreSQL and Docker, with nothing rejected.
  - `/compare` returned 3 × `not_verified` (no claims), and `/gaps` returned all 3.
  - All created rows were deleted in foreign-key order and sequences reset, back to baseline (1 user, 0 elsewhere).
- **Known limitations, deliberately not addressed:**
  - It can't tell required from preferred ("Docker knowledge preferred" is stored as required).
  - It can't find non-skill requirements ("3+ years").
  - It only finds skills already saved.
  - The matcher and Claude aren't combined.

### Learning resources: derived YouTube search links + user-curated links

Added 2026-10-01. Design and the sources deliberately not used are in `ARCHITECTURE.md` §6.3. No AI, no API key, no third-party call made by the app.

- **`LearningMode` enum** (`enums.py`): `THEORY_INTERVIEW` / `TECHNICAL_PRACTICAL` (PROJECT_RULES.md §14). Stored as the Postgres enum `learning_mode`; like the existing enums, the member *names* are stored.
- **`LearningResource` model** (`learning_resource.py`, migration `9bd5ef6ad2a1`):
  - Columns: `skill_id` FK, `mode`, `title`, `url`, `created_at`.
  - `UniqueConstraint("skill_id", "mode", "url", name="uq_learning_resource")`, so the same URL is allowed under the other mode.
  - Not user-scoped, like the skill taxonomy.
  - The autogenerated downgrade only dropped the table, so `sa.Enum(name='learning_mode').drop(..., checkfirst=True)` was added by hand, the same fix as `evidence_type`. A downgrade → upgrade cycle was confirmed against live Postgres: after the downgrade, neither the table nor the enum type existed. `alembic check` reports no drift.
- **`learning_service`:**
  - `SEARCH_QUERY_TEMPLATES`: `"{skill} interview questions"` and `"{skill} full course tutorial"`.
  - `search_query` and `youtube_search_url` use `urllib.parse.quote_plus`, so "C++" becomes `C%2B%2B` and "C#" becomes `C%23`. Links are derived per request and never stored.
  - `add_resource` strips the title and URL, then:
    - rejects a blank title (`EmptyResourceTitleError`, 422)
    - rejects anything that isn't `http`/`https` with a host (`InvalidResourceUrlError`, 422)
    - rejects the same URL already saved for this skill and mode (`DuplicateLearningResourceError`, 409)

    The URL rule is also the XSS guard, since the frontend renders saved URLs as `<a href>`: a `javascript:` URL can never be stored.
  - `list_resources` returns oldest first. `remove_resource` deletes. Like the other services, it flushes and never commits.
- **API** (`app/api/learning_resources.py`):
  - `GET /skills/{id}/learning-resources` returns `{skill_id, skill_name, modes: [{mode, search_query, search_url, resources: [...]}]}`, with both modes always present in enum order.
  - `POST /skills/{id}/learning-resources` returns 201.
  - `DELETE /learning-resources/{id}` returns 204, or 404 if missing. This is the first `DELETE` in the API.
  - An unknown skill returns 404.
- **Frontend:**
  - `lib/api.ts`: `request` now returns `undefined` for a 204 instead of trying to parse an empty body, and gains `apiDelete`.
  - `lib/types.ts`: gains `LearningMode`, `LearningResource`, `LearningModeResources`, `SkillLearningResources`.
  - `app/skills/[id]/page.tsx`: a "Learning resources" section with one `LearningColumn` per mode. Each column shows the YouTube search link, the saved links (each with Remove), and an add form with its own state. Backend 422/409 messages are shown inline. Adding or removing a link refetches only the learning data, not the whole page. All links open with `target="_blank" rel="noopener noreferrer"`.
- **Verified:**
  - **Tests:** 16 new in `test_learning_resources_api.py`:
    - URL encoding for Docker, C++, C# and Machine Learning
    - the empty state still has both search links
    - an unknown skill returns 404
    - add, then list, puts the link under its own mode only
    - 5 bad URLs return 422 and nothing is saved: `javascript:`, `ftp:`, no scheme, no host, blank
    - a blank title returns 422, and a bad mode returns 422
    - a duplicate returns 409 in the same mode but is allowed in the other mode
    - delete returns 204, then 404 on a second delete

    Suite: **217 passed**. `npm run build` is clean.
  - **Mutation check:** replacing the URL check with `if False:` made all 5 bad-URL cases fail. The file was restored byte-identical.
  - **Live check:**
    - Port 8000 briefly refused a bind (most likely a lingering socket from an earlier temporary server), so the check ran on a temporary `uvicorn` on :8011, stopped afterwards.
    - Against live Postgres: a `C++` skill got correctly encoded search links; saving returned 201; `javascript:` returned 422; a duplicate returned 409; delete returned 204, then 404.
    - The generated `C%2B%2B+full+course+tutorial` link fetched from youtube.com returned 200, with YouTube's page showing the query as `"C++ full course tutorial"`.
    - All rows were deleted and sequences reset, back to baseline.
- **Not done:**
  - showing resources for gap skills on the Dashboard / Job Descriptions pages
  - editing a saved link (remove and re-add for now)
  - "sort by view count" on search links (YouTube's URL parameter for it wasn't verified)
  - stored video titles and view counts (that would need the YouTube Data API key)
  - learning plans and progress

### Learning links next to gaps (Dashboard + Job Descriptions)

Added 2026-10-01. Frontend only; no backend change (suite still 217 passed).

- **`lib/learning.ts`:**
  - `MODE_LABEL`, moved here from the Skill Detail page so there's one copy.
  - `useLearningResources(skillIds)`, which fetches `GET /skills/{id}/learning-resources` once per distinct id. A failed request just leaves that skill out, so its buttons are hidden instead of the page failing. The effect is keyed on the sorted, de-duplicated id list, so re-renders don't refetch. Search-query wording stays in the backend only; the frontend never builds a YouTube URL itself.
- **`components/LearnLinks.tsx`:** one skill's two YouTube search buttons (`title` shows the full query), plus a link to `/skills/{id}` that shows "(N saved)" when the user has saved links.
- **`components/GapList.tsx`:** the gap list the Dashboard and Job Descriptions page each used to draw themselves (requirement, `StatusBadge`, skill name, and the shared "No gaps" message), now shared, with `LearnLinks` under each mapped gap. Unmapped gaps (`skill_id` null) get no links.
- **Dashboard (`app/page.tsx`):** a new "Skills to learn" section. `rankSkillsToLearn` takes the per-job gaps the page already fetches:
  - it counts each skill once per job description, so "needed by N jobs" means N postings, not N requirement lines
  - it skips unmapped gaps
  - it sorts by N descending, then name, and caps at `MAX_SKILLS_TO_LEARN = 8`
- **Request cost:** "Skills to learn" and the recent-comparison `GapList` each call the hook, so a skill appearing in both is fetched twice. That's accepted at this scale, the same per-item trade-off as elsewhere.
- **Verified:**
  - `npm run build` is clean; ESLint is clean for every new or changed file.
  - **Live replay**, on a temporary `uvicorn` on :8011:
    - Setup: skills Python, Docker, PostgreSQL (alias Postgres); one saved Docker link; postings "Need Python and Docker." and "Need Docker and Postgres."; extract and compare on both.
    - Replaying the Dashboard's calls with the same ranking logic gave: 4 open gaps; Skills to learn = Docker (2 jobs, 1 saved), then PostgreSQL (1), then Python (1); correct search URLs for every skill and mode; every recent-comparison gap row mapped to a skill.
    - Cleaned up back to baseline.
  - Not checked in a real browser (no browser tooling here).
- **Pre-existing lint finding, not fixed (out of scope):** `react-hooks/set-state-in-effect` flags `loadAll()` called inside `useEffect` in `app/skills/page.tsx` and `app/skills/[id]/page.tsx`. It was confirmed present in the last committed version too. It's a newer React lint rule about extra re-renders, not a bug; noted in the backlog.

### Alias ("nickname") management: remove endpoint + UI

Added 2026-10-01. Aliases are how the skill-list matcher finds more requirements, so they now have a UI.

- **`skill_service.remove_alias(db, skill, alias)`:**
  - It matches only among **this** skill's own aliases, using `normalize_text`, so case and extra whitespace are ignored. It never touches the skill's name or another skill's alias.
  - No match raises `AliasNotFoundError`, mapped to **404** in `errors.py`. This is the first domain error mapped to 404; the existing 404s are raised as `HTTPException` in routes for missing ids.
  - After the delete it flushes and expires `skill.aliases`, so the returned skill no longer lists the removed alias.
- **`DELETE /skills/{id}/aliases?alias=...`** (`skills.py`) returns the updated `SkillResponse` (200), 404 for an unknown skill or alias, and 422 without `alias`.
  - The alias goes in the **query string on purpose**: in the path, an alias like `CI/CD` would be split on its `/` by routing even when URL-encoded.
- **Frontend:**
  - `components/AliasEditor.tsx`: a list with a remove button per alias and an add form. Add and remove both call endpoints that return the updated `Skill`, which is passed to `onChange`, so there's no refetch. Backend messages (409 collision, 422 blank, 404) are shown verbatim. The alias is sent with `encodeURIComponent`.
  - It's placed on the Skill Detail page under the badges.
  - `/skills` shows "also: …" under names that have aliases.
  - `lib/api.ts`'s `apiDelete` is now generic (`apiDelete<T = void>`), since this DELETE returns a body.
- **Verified:**
  - **Tests:** 7 new in `test_skills_api.py`:
    - remove, after which `resolve` stops finding it
    - case and whitespace are ignored
    - `CI/CD` can be removed
    - another skill's alias returns 404 with nothing changed
    - the skill's own name as an alias returns 404
    - an unknown skill returns 404
    - a missing param returns 422

    Suite: **224 passed**.
  - **Mutation check:** matching across all aliases instead of `skill.aliases` made exactly `test_removing_another_skills_alias_is_404_and_changes_nothing` fail. The file was restored byte-identical.
  - `npm run build` is clean, and ESLint is clean on `AliasEditor.tsx` and `api.ts`.
  - **Live check** (temporary :8011):
    1. With skill PostgreSQL and the posting "Experience with Postgres required.", the reader found nothing.
    2. After adding alias `Postgres`, it found `("Postgres", "PostgreSQL")`.
    3. Removing `" POSTGRES "` returned the skill with `aliases: []`, and the reader found nothing again.
    4. `CI/CD` was added and then removed via `?alias=CI%2FCD`.
    5. Removing a missing alias returned 404 with the message.
    6. Cleaned up back to baseline.
- **Not done:** renaming or deleting skills, merging skills.

### Learning progress: the user's own "studying / finished" per skill

Added 2026-10-01. PROJECT_RULES.md §14 ("The AI must not infer mastery from viewing a tutorial") and §16 ("Progress is stored explicitly").

- **`LearningStatus` enum** (`STUDYING`, `FINISHED`). "Not started" is deliberately not a member: it's represented by **no row**, so there's one way to say it, like `CVSkillPresence`'s "never stated".
- **`LearningProgress` model** (`learning_progress.py`, migration `e034a498adb5`):
  - Columns: `user_id`, `skill_id`, `status`, `updated_at` (`onupdate`).
  - `UniqueConstraint("user_id", "skill_id", name="uq_learning_progress")`.
  - **No FK to `UserSkill`/`Evidence`**, by design.
  - Downgrade hand-fixed to also drop the `learning_status` enum type, the same as `learning_mode`. A downgrade → upgrade cycle was confirmed on live Postgres (no table and no enum left after the downgrade), and `alembic check` is clean.
- **`learning_progress_service`:**
  - `get_progress`
  - `list_progress`, ordered by skill name
  - `set_progress(db, user, skill, status | None)`: `None` deletes the row if present; otherwise it upserts.

  It reads and writes `LearningProgress` **only**. It never touches `UserSkill`, `Evidence` or verification.
- **API** (`app/api/learning_progress.py`, user-scoped via `get_current_user`):
  - `PUT /skills/{id}/learning-progress` takes `{"status": "not_started" | "studying" | "finished"}`. It's a Pydantic `Literal`, so anything else, including `"verified"`, is a 422.
  - `GET /learning-progress` lists only the current user's rows.
  - `LearningProgressResponse.for_skill(skill, progress)` builds the response without an ORM row in the "not started" case: `status "not_started"`, `updated_at null`.
  - `PUT` is used because the request states the whole value (an idempotent set). It's the first `PUT` in the API, which is why `lib/api.ts` gains `apiPut`.
- **Frontend:**
  - `components/LearningProgressControl.tsx`: three buttons with `aria-pressed`. When the status is `finished` and `knowledge_status !== "verified"`, it shows "Finished studying isn't proof yet… add evidence … and link it to your claim".
  - It's placed on the Skill Detail page under Nicknames. The page loads `GET /learning-progress` and picks its skill.
  - Dashboard "Skills to learn" items show a "studying" / "finished studying" tag.
  - `PROGRESS_LABEL` lives in `lib/learning.ts`.
- **Verified:**
  - **Tests:** 13 new in `test_learning_progress_api.py`:
    - empty list
    - studying, then finished, updates one row
    - `not_started` deletes the row, and is fine when there's nothing to delete
    - unknown skill returns 404
    - `verified` / `mastered` / `""` / `STUDYING` return 422
    - the list is ordered by name and scoped to the user
    - **guard:** "finished" leaves an existing claim `provisional` with no evidence
    - **guard:** "finished" on an unclaimed skill creates no `UserSkill`

    Suite: **237 passed**.
  - **Mutation check:** injecting an auto-verify into `set_progress` (on `FINISHED`, create or upgrade the claim to `VERIFIED`) made exactly the two guard tests fail. The file was restored byte-identical.
  - `npm run build` is clean, and ESLint is clean on the new and changed files apart from the known pre-existing `set-state-in-effect` finding.
  - **Live check** (temporary :8011):
    - Claimed Docker (`provisional`), then set studying and finished; `updated_at` advanced.
    - The list showed `finished`, while the claim was still `provisional` with `[]` evidence and `cv-status` `knowledge_status` was `provisional`.
    - `"verified"` returned 422.
    - Reset to `not_started` returned `updated_at null` and an empty list.
    - Cleaned up back to baseline.
- **Not done:** a `LearningPlan` table (see `ARCHITECTURE.md` §4), percentages, per-resource "watched" tracking, reminders.

### CV upload: scan a CV for saved skills, then confirm CV presence

Added 2026-10-01. It's two steps on purpose: `CVSkillPresence` is a fact the *user* supplies, so a scan only suggests and nothing is written until the user confirms. A CV is a claim, not proof, so neither step touches `UserSkill`, `Evidence` or verification.

- **New dependencies:** `pypdf` and `python-multipart` (FastAPI needs it for uploads), both added to `requirements.txt`. **Both were confirmed pure Python, with no `.pyd` files**, because Windows Smart App Control already blocked a compiled extension on this machine (`psycopg2`, §9). `.docx` is read with the stdlib (`zipfile` + `xml.etree`), so no extra package.
- **`cv_presence_service.set_cv_presence(db, user, skill, present)`:** the upsert previously inlined in `PATCH /skills/{id}/cv-presence`, moved out so the badge toggle and the CV save share it. It's a separate module because `cv_service` is documented read-only. The behavior is unchanged: all 237 existing tests passed straight after the move.
- **`cv_import_service`** (read-only):
  - **`extract_text(filename, content)`:**
    - Picks the reader by extension: `pdf` (`pypdf`, empty password tried for encrypted files), `docx`, or `txt` (UTF-8 with BOM, falling back to latin-1). Any other extension raises `UnsupportedCVFileError` (**415**).
    - Over `MAX_CV_BYTES` (5 MB) raises `CVFileTooLargeError` (**413**). The route reads at most limit+1 bytes, so a huge upload is never fully read into memory.
    - No text, such as a scanned image or blank file, raises `NoCVTextError` (**422**, "paste the text instead").
    - **Defensive parsing of untrusted files:**
      - any `pypdf` failure becomes a 415, not a 500
      - a `.docx` whose `word/document.xml` decompresses beyond `MAX_DOCX_XML_BYTES` (20 MB) is refused, which guards against zip bombs
      - XML containing `<!DOCTYPE` or `<!ENTITY` is refused, which guards against entity-expansion attacks; a real `.docx` never contains either
  - **`scan_cv(db, user, text)`:**
    - Runs the same `SkillListExtractor` over the CV and maps each match through `resolve_skill`. An ambiguous match is skipped, as in `requirement_service`.
    - Returns `CVScan(characters, found=[FoundSkill(skill, matched_text, on_cv)], on_cv_not_found=[Skill])`.
- **API** (`app/api/cv.py`, user-scoped):
  - **`POST /cv/scan`:** multipart with exactly one of `file` or `text` (otherwise 422). It returns `CVScanResponse` and saves nothing.
  - **`PUT /cv/presence`** takes `{present_skill_ids, absent_skill_ids}`:
    - duplicates are ignored, and an id in both lists is a 422
    - **every id is checked before anything is written**, so one unknown id returns 404 and saves nothing
    - one commit at the end
- **Frontend:**
  - **`app/cv/page.tsx` ("My CV", added to `AppHeader`):** a file input or textarea, then Scan, then a review screen:
    - found skills, **ticked by default**, showing "found as …" when matched via a nickname and "already marked"
    - "marked on your CV but not found in this one", **unticked by default**, so a skill the reader missed (e.g. an unsaved nickname) is never removed by accident
    - Save, then a summary
  - `lib/api.ts` gains `apiPostForm`, which deliberately sets no `Content-Type` so the browser can set the multipart boundary.
  - `AppHeader`'s stale "job-descriptions doesn't exist yet" comment was removed.
- **Verified:**
  - **Tests:** 18 new in `test_cv_api.py`. Sample files are built inside the tests: a hand-assembled minimal PDF, and a `.docx` zipped with the stdlib.
    - `.txt`, `.pdf` (uppercase extension too) and `.docx` all find skills by name and alias, whole words only
    - pasted text works
    - scanning saves nothing and reports `on_cv` and `on_cv_not_found`
    - 7 unusable inputs give clear errors: `.png`, no extension, fake PDF, non-zip `.docx`, `.docx` with a DOCTYPE/ENTITY, a blank `.txt`, a text-less PDF
    - over the limit returns 413, and neither or both of file/text returns 422
    - save marks present and absent and leaves unmentioned skills untouched
    - an unknown id returns 404 with nothing saved, and an id in both lists returns 422
    - **guard:** scanning and saving never changes a claim's status or creates claims

    Suite: **255 passed**.
  - **Mutation check:** making `set_cv_presence` auto-create a `UserSkill` for present skills made exactly the guard test fail. The file was restored byte-identical.
  - `npm run build` is clean with the new `/cv` route, and ESLint is clean on the new and changed files.
  - **Live check:**
    - Run on a temporary :8011, with the user's own server running on :8000 and their test data (4 skills, 1 alias, 1 claim, 1 evidence, 1 job description) left in place.
    - Two uniquely named test skills, "Zebralang" and "QuokkaDB" (alias "Quokka"). A real multipart upload of a generated PDF ("…Zebralang and Quokka…") found both, with QuokkaDB "found as Quokka".
    - Save marked both present, and `cv-status` showed `present`. A `.png` returned 415.
    - **Cleanup deleted only those two skills by id** (ids asserted, names asserted) and their rows; sequences were set to max(id)+1. The user's data was verified identical to the snapshot.
    - The user's `--reload` server picked up `/cv/scan` and `/cv/presence` automatically.
- **Not done:**
  - showing CV status next to each gap (the next step)
  - extracting job history or education
  - OCR for scanned CVs
  - storing the CV
  - finding skills not yet in the taxonomy

### CV status next to every gap, and `GET /cv/status`

Added 2026-10-01. This is step 2 of the CV work, and it also closes the long-standing "list-all-my-cv-statuses endpoint" backlog item.

- **`GET /cv/status`** (`app/api/cv.py`, user-scoped, read-only) returns `[CVStatusResponse.from_combined_status(c) for c in cv_service.combined_status_for_all(db, user)]`: every skill with a `UserSkill` or `CVSkillPresence` row for this user, ordered by name, in one request. `combined_status_for_all` already existed and was tested since task 22; it had just never had a route. Skills with neither row aren't listed, and the frontend treats them as `not_present`.
- **`lib/cv.ts`:**
  - `cvBadgeClasses` / `cvBadgeLabel`, moved from the two copies in `app/skills/page.tsx` and `app/skills/[id]/page.tsx` (this would have been the third). Both pages now import them, with no visual change.
  - `useCvStatuses()`, which fetches `/cv/status` once. A failure yields `{}`, so a page shows no CV info rather than failing.
- **`components/GapList.tsx`:** each mapped gap gets a `CV: <status>` badge, plus `cv.recommendation` (warm text) when there is one.
  - **Two time frames are deliberately shown side by side:** the knowledge badge is the snapshot from the job's last comparison, while the CV badge and advice are *current*. This is noted in the component's docstring.
  - Unmapped gaps get no CV badge.
- **Verified:**
  - **Tests:** 3 new in `test_cv_api.py`:
    - empty before any claim or CV mark
    - only claimed and CV-marked skills appear, by name, and **each entry equals the per-skill `GET /skills/{id}/cv-status` response**; a CV-only skill gives `(None, "present")` plus the "without verified evidence" advice
    - another user's CV row isn't listed

    Suite: **258 passed**.
  - `npm run build` is clean. ESLint is clean on `GapList.tsx` and `lib/cv.ts`; the two pages still show only the known pre-existing `set-state-in-effect` finding.
  - **Live check** (temporary :8011; the user's server and data untouched):
    - Setup: test skills Zebralang (claimed, marked on the CV) and QuokkaDB (untouched); posting "Need Zebralang and QuokkaDB experience."; extract and compare.
    - Replaying the gap list's requests gave the rows `Zebralang | provisional | CV: present` plus the advice, and `QuokkaDB | not_verified | CV: not present` with no advice.
    - `/cv/status` also correctly included the user's own claimed skill.
    - Cleanup deleted only the recorded ids (names and titles asserted first) in foreign-key order. Row counts were compared against a pre-check snapshot and matched exactly.
- **Not done:**
  - switching the Skills page's per-skill `cv-status` requests to `/cv/status`
  - CV tags on the Dashboard's "Skills to learn"

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
- `tests/test_skills_cv_api.py` (9 tests, its own file — same reasoning as `test_user_skills_api.py`/`test_evidence_api.py` being split out already: a cohesive feature area, keeps `test_skills_api.py` from growing indefinitely) covers: `PATCH` creating a row when none exists; `PATCH` again **updating** the same row rather than creating a second (row count stays 1); `PATCH` on a nonexistent skill → 404, nothing created; `GET` with no claim and no presence → `not_present`/`None`; `GET` after `PATCH`ing present with no claim → the "listed without verified evidence" warning; `GET` for a real `VERIFIED` claim (built via `verification_service`, bootstrapped through `GET /me` so the test's `User` row matches the one `get_current_user` will resolve) missing from the CV → the "Consider adding" suggestion; the same claim present on the CV → no recommendation; `GET` on a nonexistent skill → 404; and `/openapi.json`/`/docs` listing both new paths. The upsert behavior and the read-only guarantee on `GET .../cv-status` were both mutation-checked — breaking the upsert into create-only failed the update test, and making the `GET` route write anything immediately hit the real `(user_id, skill_id)` unique constraint as an `IntegrityError`.
- **Live check (2026-09-29):** the same server pattern was walked through the exact flow requested: claim a skill, attempt `VERIFIED` with no evidence → `409`, add evidence, link it, set `VERIFIED` → `200` with `status: "verified"`. A duplicate claim also returned `409` mid-flow. `/docs`/`/openapi.json` both returned 200 and listed the new paths. The one user, skill, user-skill, evidence, and evidence-link row created were all deleted afterward (in FK-safe order) and every id sequence reset, leaving `career_ai` exactly as found (every table checked back at 0 rows).
- Full test suite: `185 passed` (`test_health.py` 1, `test_profile_models.py` 3, `test_user_skill.py` 3, `test_job_description.py` 1, `test_job_requirement.py` 2, `test_comparison_result.py` 3, `test_verification_service.py` 11, `test_skill_service.py` 28, `test_comparison_service.py` 26, `test_skills_api.py` 19, `test_requirement_service.py` 16, `test_user_service.py` 4, `test_me_api.py` 2, `test_job_descriptions_api.py` 14, `test_user_skills_api.py` 15, `test_evidence_api.py` 8, `test_cv_skill_presence.py` 5, `test_cv_service.py` 15, `test_skills_cv_api.py` 9).
- **Live check (2026-09-29, cv-presence/cv-status):** the real server was walked through the exact flow requested: `PATCH .../cv-presence {"present": true}` on a fresh skill → the "listed without verified evidence" warning via `GET .../cv-status`; `PATCH .../cv-presence {"present": false}` → `GET` confirming it flipped to `not_present`/`None`; `PATCH` on a nonexistent skill → 404. `/docs`/`/openapi.json` both returned 200 and listed both new paths. The one user, skill, and CV-presence row created were deleted afterward and every affected id sequence reset, leaving `career_ai` exactly as found (every table checked back at 0 rows).
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
   - ~~`LearningResource`~~ ✅ done 2026-10-01 — user-curated links per skill and mode, plus derived YouTube search links (see "Learning resources" in §7). Still pending: showing them for gap skills on the Dashboard / Job Descriptions pages.
   - `LearningPlan` — **deliberately not a table** (2026-10-01): the Dashboard's derived "Skills to learn" ranking serves as the plan; see `ARCHITECTURE.md` §4.
   - ~~`LearningProgress`~~ ✅ done 2026-10-01 — see "Learning progress" in §7.
   - ~~`CVSkillPresence`~~ ✅ done 2026-09-29 (`app/db/models/cv_skill_presence.py`; `(user_id, skill_id)` unique constraint, one evolving row like `UserSkill` rather than an append-only history like `ComparisonResult`; `present: Boolean` has no default — the caller must always state it explicitly; **deliberately independent** of `UserSkill`/`Evidence`/`ComparisonResult` — no FK to any of them, so a skill can be `VERIFIED` and not on the CV, or `NOT_VERIFIED` and on the CV, with no conflict — verified with real coexisting rows in `tests/test_cv_skill_presence.py`). The combined "knowledge + CV" view is now ✅ done too, at the service level — see `cv_service.py` in §7. CV presence can now be **set and read over HTTP** too (`PATCH`/`GET /skills/{id}/cv-presence`/`cv-status`, see §7). Still pending: a list-all-my-cv-statuses endpoint (only a single-skill read exists so far), and `DELETE` if ever needed.

   Reference these concepts from `ARCHITECTURE.md` and `PROJECT_RULES.md`. Suggested next sub-batch: `UserSkill` alone (it's the piece that finally connects `Skill` to `User`/`Evidence` and lets verification-status rules become testable), since everything from `JobRequirement` onward depends on it existing.

2. **Generate Alembic migrations** for each new model or coherent group of models. (Convention established: one migration per model, or per tightly-coupled sibling group — see the `projects_work_experiences_educations` migration.)

3. **Create Pydantic schemas** in `backend/app/core/models.py` for request/response validation. (Partially done 2026-09-25: `SkillCreate`, `AliasCreate`, `SkillResponse`. Schemas for every other domain are still pending.)

4. **Create domain services** in `backend/app/core/services/`:
   - ~~`verification_service.py`~~ ✅ done 2026-09-25 — `link_evidence` + `set_status` (see §7). Still pending: HTTP endpoints that call it, and any `unlink_evidence`.
   - ~~`skill_service.py`~~ ✅ partially done 2026-09-25 — canonical skill lookup (`resolve_skill`) + safe creation (`create_skill`, `add_alias`) + read helpers (`list_skills`, `get_skill`), see §7. HTTP endpoints for these now exist (see item 5). Still pending: skill/alias rename/deletion.
   - ~~`comparison_service.py`~~ ✅ done 2026-09-25 — `compare_job_description`; read side added 2026-09-26 — `latest_results` + `skill_gaps` (see §7). Still pending: HTTP endpoints. `comparison_service` itself does **not** read `CVSkillPresence` — that combined view is `cv_service.py` instead, kept as its own module (see item below), not folded into `comparison_service`.
   - ~~`requirement_service.py`~~ ✅ done 2026-09-26 **at the service level**, endpoint added 2026-09-28 (see §7) — `extract_requirements` validates an untrusted extractor's proposals (grounding check, dedup, skill mapping only via `resolve_skill`) and stores `JobRequirement` rows, unchanged by which extractor is plugged in. The **real LLM provider implementation + prompt** is now ✅ done too, 2026-09-29 — `app/ai/providers/claude_extractor.py`, wired in automatically only when `ANTHROPIC_API_KEY` is set (see the dedicated section below). **Not yet live-tested against the real API — no key exists in this environment on purpose; see that section for exactly what was and wasn't verified.** Still pending: any **re-extraction workflow** (a re-run is currently refused, regardless of extractor).
   - ~~`cv_service.py`~~ ✅ done 2026-09-29 — `combined_status` + `combined_status_for_all` (see §7). Read-only; both an HTTP endpoint (`GET .../cv-status`) and a way to write a `CVSkillPresence` (`PATCH .../cv-presence`) now exist — see the "Skills API" section in §7. `combined_status_for_all` still has no endpoint of its own (only the single-skill read is wired up).
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
