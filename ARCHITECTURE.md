# Career AI — Architecture

> **Version:** Foundation  
> **Goal:** Define a modular, extensible, and understandable architecture for a personal career and technical-knowledge system.

## 1. Design Goals

1. **Clean separation** between frontend, backend, database, AI logic, and documentation.
2. **Anti-hallucination by design** — personal claims are always traceable to stored, verified evidence.
3. **Simplicity first** — understandable code that can be explained in an interview.
4. **Extensibility** — RAG, pgvector, and new AI providers can be added later without rewriting core logic.
5. **Type safety** — explicit contracts between frontend and backend.

## 2. High-Level Architecture

```text
┌─────────────────────────────────────────────────────────────┐
│                        Frontend                             │
│              Next.js + TypeScript + Tailwind CSS            │
│  - Paste job descriptions                                   │
│  - View verified profile, comparisons, gaps, and plans      │
│  - Manage learning progress                                 │
└───────────────────────┬─────────────────────────────────────┘
                        │ HTTP / REST + OpenAPI
┌───────────────────────▼─────────────────────────────────────┐
│                        Backend                              │
│                     Python + FastAPI                          │
│  - API routes                                               │
│  - Service / business logic                                 │
│  - SQLAlchemy ORM                                           │
│  - Verification layer                                       │
│  - Canonical skill matching                                 │
└──────────────┬────────────────────────────┬───────────────┘
               │                            │
┌──────────────▼──────────────┐  ┌──────────▼──────────────┐
│         Database            │  │      AI / LLM Layer     │
│    PostgreSQL + SQLAlchemy  │  │   LLM API client        │
│  - Source of truth          │  │   Structured outputs    │
│  - Evidence & verification  │  │   Prompt templates      │
│  - Requirements & results   │  │   Parsing & suggestions │
│  - Learning plans           │  │   No authority          │
└─────────────────────────────┘  └─────────────────────────┘
```

## 3. Layer Responsibilities

### 3.1 Frontend (`frontend/`)

- User interface for the Next.js application.
- Communicates with the backend only through typed REST endpoints.
- Displays data with clear labels for verification status and CV status.
- No business logic or direct database access.

### 3.2 Backend (`backend/`)

- FastAPI application exposing REST endpoints.
- **Simple architecture:** API → Service → SQLAlchemy → PostgreSQL.
- Domain services implement business rules and verification logic.
- No generic repository abstraction in Version 1.
- AI orchestration layer calls the LLM client and validates structured outputs.

### 3.3 Database (`backend/alembic/` + PostgreSQL)

- PostgreSQL is the single source of truth.
- SQLAlchemy models and Alembic migrations live in `backend/alembic/`.
- Stores:
  - User profile, skills, projects, work experience, education
  - Evidence records and verification status
  - Job descriptions and extracted requirements
  - Comparison results (skill gaps are derived from them, not stored)
  - Learning plans and progress
  - CV skill presence

### 3.4 AI / LLM Layer (`backend/app/ai/`)

- LLM client with provider abstraction.
- Structured-output parsing for job descriptions, requirements, and suggestions.
- Prompt templates versioned alongside code.
- **LLM = assistant, not authority.** It does not decide verification status or invent facts.

### 3.5 Knowledge / Data (`knowledge/`)

- Structured verified data files, import schemas, and templates.
- Canonical skill dictionaries and taxonomies.

### 3.6 Documentation (`docs/`)

- Architecture, rules, API contracts, data models, and decisions.
- Single source of truth for project conventions.

## 4. Core Domain Concepts

| Concept | Description |
|---------|-------------|
| `User` / `Profile` | The user and their career profile. |
| `Skill` | A canonical technology, methodology, or capability with aliases and category. |
| `UserSkill` | Relationship linking a user to a skill with status and evidence. |
| `Evidence` | A concrete record proving a claim: project, work experience, certification, artifact. |
| `Project` | A documented project with role, technologies, and responsibilities. |
| `WorkExperience` | A job or role with documented responsibilities and technologies. |
| `Education` | Degrees, certifications, and formal training. |
| `JobDescription` | Raw text plus extracted structured requirements. |
| `JobRequirement` | A single skill/capability demanded by a job description, normalized to a canonical skill. |
| `ComparisonResult` | Mapping of a requirement to the user's verification status, CV status, and reasoning. |
| `SkillGap` | **A derived view, not a stored table.** The latest `ComparisonResult` per requirement whose status is not `VERIFIED` (i.e. `PARTIAL`, `PROVISIONAL`, or `NOT_VERIFIED`), computed by `comparison_service.skill_gaps`. Not stored because it would duplicate `ComparisonResult` and go stale as soon as evidence is added. |
| `LearningResource` | A link (doc, video, playlist, course) the **user** saved for a skill under one learning mode (`theory_interview` or `technical_practical`). Only the user adds or removes these; nothing is created automatically. Belongs to the skill, not a user. YouTube search links are **not** stored here — they're derived per request (section 6.3). |
| `LearningPlan` | **Not a stored table (for now).** The Dashboard's "Skills to learn" list (gap skills ranked by how many job descriptions need them, each with its learning resources) already serves as the plan and is derived, like `SkillGap`. A table would only be added for plan-specific state the user enters (e.g. target dates). |
| `LearningProgress` | The user's own statement of how far they are in studying one skill: `studying` or `finished` (no row means "not started"). One row per (user, skill). **Independent of `UserSkill` and `Evidence`**: finishing studying never changes verification status (PROJECT_RULES.md §14: mastery is never inferred from studying). |
| `CVSkillPresence` | Whether a skill is currently listed on the user's CV — **not restricted to verified skills**. This is a fact the user states directly and is kept fully independent of `UserSkill.status` (section 12): a skill can be `VERIFIED` and absent from the CV, or `NOT_VERIFIED` and present on it. No service infers or sets this automatically. |

> **Why `SkillGap` is derived:** `ComparisonResult` rows are append-only snapshots, so the full history is already stored. A "gap" is just the current answer to "which requirements of this job am I not yet verified for?" — the latest result per requirement, minus `VERIFIED`. A dedicated gap table could only copy that information and would go stale. If gap-specific state is ever needed (priority, dismissed, notes), a table can be added later for that state alone.

## 5. Verification Statuses

| Status | Definition |
|--------|------------|
| `VERIFIED` | Sufficient supporting evidence exists. |
| `PARTIAL` | Some evidence exists, but not enough for strong/full proficiency. |
| `PROVISIONAL` | User-reported or learning, no sufficient evidence yet. |
| `NOT_VERIFIED` | No relevant evidence exists. |

Only `VERIFIED` records may be used for factual claims about professional background.

## 6. Data Flow

### 6.1 Storing verified knowledge

```text
User input → Backend API → Validation → SQLAlchemy → PostgreSQL
                                  ↓
                           Verification layer
```

### 6.2 Comparing a job description

```text
Paste JD → Backend → AI parser (structured output)
              ↓
        Extract requirements
              ↓
        Normalize to canonical skills
              ↓
        Backend validates mapping
              ↓
        Compare against verified evidence
              ↓
        Return categorized results + reasoning + evidence IDs
```

### 6.3 Recommending learning resources

```text
Skill (e.g. a gap) → for each learning mode:
        ├─ derived YouTube search link (fixed query template; built, never fetched or stored)
        └─ user-curated LearningResource rows (added/removed only by the user)
                 ↓
        Return both, per mode
                 ↓
        User reviews and saves learning plan (not built yet)
```

**Current implementation (2026-10-01):** resources come from two sources, neither involving AI or any third-party API call:

1. **Derived YouTube search links.** For each mode, a fixed query ("{skill} interview questions" / "{skill} full course tutorial") is turned into a `youtube.com/results?search_query=…` URL. The app never requests it; clicking it runs YouTube's own live search, so results are always current, with no API key, scraping, or quota. Nothing is stored, so nothing can go stale (same reasoning as `SkillGap`).
2. **User-curated links** (`LearningResource`), satisfying PROJECT_RULES.md §15's "curated, reviewable and editable". Only `http`/`https` links with a host are accepted.

**Deliberately not used:** an AI resource suggester (an LLM can invent course names and URLs, which this project's anti-hallucination rule forbids, unless every link it returns is checked against a real source), unofficial YouTube scraping tools (against YouTube's terms, fragile), and pre-filled curated links (links written from memory are themselves unverified). The official YouTube Data API remains a compatible later addition (it needs a free Google API key) if stored titles and view counts are wanted.

## 7. API Boundaries

- REST endpoints grouped by domain:
  - `/profile/*`
  - `/skills/*`
  - `/experience/*`
  - `/projects/*`
  - `/job-descriptions/*`
  - `/comparisons/*`
  - `/learning/*`
- Request/response schemas defined with Pydantic.
- OpenAPI generated automatically by FastAPI.

## 8. Backend Architecture (Version 1)

```text
API
 ↓
SERVICE / BUSINESS LOGIC
 ↓
SQLAlchemy
 ↓
PostgreSQL
```

- No generic repository abstraction unless a concrete need arises.
- Services contain explicit business rules and verification logic.
- SQLAlchemy models and queries live close to the service layer.

## 9. Database Overview

- PostgreSQL relational schema.
- Tables for users, skills, user skills, evidence, projects, experience, education, job descriptions, requirements, comparisons, learning resources, plans, progress, and CV presence.
- Verification status is stored explicitly.
- `pgvector` will be added later for semantic search and RAG.
- Alembic migrations live in `backend/alembic/` only.

## 10. Skill Matching Engine

1. Job description text is parsed into structured requirements.
2. Each requirement is normalized to a canonical skill using the skill taxonomy.
3. The backend validates the mapping; the LLM does not decide the final match.
4. The comparison engine looks up the user's `UserSkill` records and linked evidence.
5. Status is determined by the verification layer, not by keyword presence.
6. Results include evidence references so the UI can explain the decision.
7. Skill gaps are derived on demand from the latest result per requirement (status not `VERIFIED`); they are never stored and reading them never triggers a new comparison.

## 11. AI / LLM Integration

- LLM provider abstracted behind an interface.
- All calls use structured outputs (Pydantic models / JSON schemas).
- Prompts include only relevant verified data; no free-form biographical generation.
- Comparison results cite record IDs so the UI can link back to evidence.
- The LLM never marks a skill `VERIFIED` or adds it to the CV.

## 12. CV Skills vs Verified Knowledge

The system maintains two independent views of skills:

- **Knowledge status:** based on stored evidence (`VERIFIED`, `PARTIAL`, `PROVISIONAL`, `NOT_VERIFIED`).
- **CV status:** whether the skill is present on the user's CV (`PRESENT`, `MISSING_FROM_CV`, `NOT_PRESENT`).

This enables recommendations such as:

- "You have verified Docker experience. Consider adding it to your CV."
- "You do not have verified AWS experience. Do not claim it on your CV yet."

## 13. Extensibility

- New AI providers: implement the LLM client interface.
- New comparison strategies: add a new service behind a common interface.
- New resource sources: add a plugin to the resource suggester or a curated catalog.
- New frontend features: consume existing backend endpoints without backend changes.
- Future RAG: add embedding generation and vector columns without changing core domain logic.

## 14. Future RAG

RAG and `pgvector` are future capabilities, not part of Version 1.

When introduced:

```text
Verified knowledge
+ Interview knowledge
+ Technical learning material
+ Relevant documents
        ↓
Embeddings / vector search
        ↓
Relevant context
        ↓
LLM
        ↓
Grounded answer
```

RAG must not replace PostgreSQL as the source of truth for the user's professional background.

## 15. Development Phases

### Phase 1 — Backend Foundation

- FastAPI
- PostgreSQL
- SQLAlchemy
- Alembic
- Domain models
- Verification rules
- Basic REST APIs
- Health check
- Tests

### Phase 2 — Frontend

- Next.js
- TypeScript
- Tailwind CSS
- Connect to backend APIs

### Phase 3 — Job Analysis

- Job description input
- Structured requirement extraction
- Canonical skill normalization
- Deterministic comparison

### Phase 4 — AI Integration

- LLM provider
- Structured outputs
- Resource recommendations
- Interview generation

### Phase 5 — RAG / pgvector

- Embeddings
- Semantic search
- Grounded knowledge retrieval

## 16. Security & Privacy

- Personal data stays in the user's database.
- LLM calls send only the data needed for the current task.
- No AI provider caches or trains on personal data unless contractually guaranteed.
- API authentication will be added before any deployment.

## 17. Anti-Hallucination Design

The architecture enforces the anti-hallucination principle through:

1. **Centralized verification layer** — all status changes require evidence.
2. **Traceable comparisons** — every requirement result links to stored records.
3. **Structured LLM outputs** — prevents the model from inventing free-form claims.
4. **Explicit data boundaries** — frontend and AI cannot mutate verified data directly.
5. **Canonical skill taxonomy** — prevents false keyword matches.
6. **Default response** — missing data always returns `"Not enough verified information."`.
