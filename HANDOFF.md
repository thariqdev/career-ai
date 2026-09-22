# Career AI — Project Handoff Document

> **Date:** 2026-09-23  
> **Current phase:** Phase 1 — Backend Foundation (in progress)  
> **Status:** Foundation documents approved. Basic FastAPI backend skeleton created. Ten SQLAlchemy models now exist — `Skill`, `SkillAlias`, `User`, `Project`, `WorkExperience`, `Education`, `Evidence`, `UserSkill`, `UserSkillEvidence`, `JobDescription` — with migrations applied to a live local PostgreSQL database. No business logic, AI, auth, or frontend yet.
>
> **Note:** the psycopg2 / Application Control blocker described in §9 below no longer reproduces on this machine — `psycopg2-binary` imports fine and `database.py` connects to a live local PostgreSQL instance. Leaving §9 as historical context in case it recurs on a different machine.

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
    │       └── a2829026c599_create_evidence_table.py
    ├── app/
    │   ├── __init__.py
    │   ├── main.py             ← FastAPI app + /health router
    │   ├── dependencies.py     ← get_db() FastAPI dependency
    │   ├── api/
    │   │   ├── __init__.py
    │   │   └── health.py       ← GET /health endpoint
    │   ├── core/
    │   │   ├── __init__.py
    │   │   ├── models.py       ← Pydantic schemas (HealthResponse only)
    │   │   ├── services/       ← empty
    │   │   └── exceptions.py   ← empty
    │   ├── db/
    │   │   ├── __init__.py
    │   │   └── models/
    │   │       ├── __init__.py     ← registers all 7 models
    │   │       ├── skill.py
    │   │       ├── skill_alias.py
    │   │       ├── user.py
    │   │       ├── project.py
    │   │       ├── work_experience.py
    │   │       ├── education.py
    │   │       ├── evidence.py
    │   │       └── enums.py        ← EvidenceType
    │   └── ai/                 ← placeholders only
    │       ├── __init__.py
    │       ├── client.py
    │       ├── providers/
    │       │   └── __init__.py
    │       ├── prompts/
    │       └── schemas.py
    └── tests/
        ├── __init__.py
        ├── test_health.py
        └── test_profile_models.py   ← relationship tests (in-memory SQLite)
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

### `backend/app/db/models/__init__.py`

```python
from app.db.models.skill import Skill
from app.db.models.skill_alias import SkillAlias
from app.db.models.user import User
from app.db.models.project import Project
from app.db.models.work_experience import WorkExperience
from app.db.models.education import Education
from app.db.models.evidence import Evidence

__all__ = ["Skill", "SkillAlias", "User", "Project", "WorkExperience", "Education", "Evidence"]
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

Five migrations exist, applied in order, all consistent with the models (`alembic current` → `a2829026c599 (head)`):

- `c844c1e832a2_create_skills_table.py`
- `8ac9a8427368_create_skill_aliases_table.py`
- `fdf101337f27_create_users_table.py`
- `dc3241d510d0_create_projects_work_experiences_.py` — creates `projects`, `work_experiences`, `educations` together (one migration for the sibling group, per the "coherent group of models" convention).
- `a2829026c599_create_evidence_table.py` — creates `evidence` plus the `evidence_type` Postgres enum type. Its `downgrade()` was hand-edited to also drop the enum type (Alembic's autogenerate doesn't do this itself, which would otherwise break a downgrade→upgrade cycle).

They create (skills/skill_aliases shown previously; new tables):

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

- FastAPI server starts.
- `GET /health` returns `{"status": "ok"}`.
- Health test passes without a database.
- SQLAlchemy mappings for `Skill` and `SkillAlias` load correctly. Bidirectional relationship (`skill.aliases` / `alias.skill`) works.
- All 7 models (`Skill`, `SkillAlias`, `User`, `Project`, `WorkExperience`, `Education`, `Evidence`) are mapped, migrated, and confirmed against a **live local PostgreSQL database** (`career_ai`) — not just SQLite. `alembic current` → head, table/column shapes verified with `sqlalchemy.inspect`.
- `User → Project/WorkExperience/Education → Evidence` relationships verified in `tests/test_profile_models.py` (in-memory SQLite, 3 tests): ownership relationships, evidence linking back to its source record, and evidence standing alone (e.g. a certification) without a source record.
- Full test suite: `4 passed` (`test_health.py` + `test_profile_models.py`).

---

## 9. Environment-Specific Notes

- The local `.venv` was created with **Python 3.14.2**, but `pyproject.toml` requires `>=3.12,<3.13`. This mismatch hasn't caused problems in practice (tests and migrations run fine), but it's still worth recreating the venv with 3.12 at some point for strict reproducibility.
- The project uses `psycopg2-binary` as the PostgreSQL driver.
- **Update 2026-09-23:** on the machine currently used for development, `psycopg2` imports without issue and `database.py` connects to a real local PostgreSQL instance (`career_ai` database). The Application Control block described below was **not** reproduced here.
- Historical note (kept in case this recurs on a different machine): a previous session on a different Windows environment reported `psycopg2` import being blocked by an Application Control policy, meaning any code path creating the real engine would fail there. If that happens again:
  1. Run on a system where `psycopg2-binary` works, or
  2. Switch to `pg8000` (pure-Python driver).
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
   - `JobRequirement` — not started
   - `ComparisonResult` — not started
   - `SkillGap` — not started
   - `LearningResource` — not started
   - `LearningPlan` — not started
   - `LearningProgress` — not started
   - `CVSkillPresence` — not started

   Reference these concepts from `ARCHITECTURE.md` and `PROJECT_RULES.md`. Suggested next sub-batch: `UserSkill` alone (it's the piece that finally connects `Skill` to `User`/`Evidence` and lets verification-status rules become testable), since everything from `JobRequirement` onward depends on it existing.

2. **Generate Alembic migrations** for each new model or coherent group of models. (Convention established: one migration per model, or per tightly-coupled sibling group — see the `projects_work_experiences_educations` migration.)

3. **Create Pydantic schemas** in `backend/app/core/models.py` for request/response validation.

4. **Create domain services** in `backend/app/core/services/`:
   - `verification_service.py` — enforce evidence rules and status transitions.
   - `skill_service.py` — skill CRUD and canonical skill lookup.
   - `comparison_service.py` — compare job requirements against verified evidence.
   - `learning_service.py` — learning plans and progress.

5. **Create REST API endpoints** in `backend/app/api/`:
   - `/skills/*`
   - `/experience/*`
   - `/projects/*`
   - `/job-descriptions/*`
   - `/comparisons/*`
   - `/learning/*`

6. **Implement verification rules**:
   - Only `VERIFIED` evidence can be used for factual claims.
   - `PARTIAL` and `PROVISIONAL` cannot be auto-upgraded.
   - Evidence traceability: every `VERIFIED` skill links to evidence records.

7. **Implement canonical skill taxonomy**:
   - Store canonical names and aliases.
   - Distinguish exact matches from related technologies.
   - Backend validates final skill mapping.

8. **Add tests** for:
   - Health endpoint (already done).
   - Verification rules.
   - Skill CRUD endpoints.
   - Canonical skill matching.

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
