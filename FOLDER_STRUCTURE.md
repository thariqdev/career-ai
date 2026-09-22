# Career AI — Proposed Folder Structure

> **Status:** Foundation proposal. No code directories exist yet.

```text
career-ai/
│
├── .git/                          # Git repository
├── .gitignore                     # Global ignore rules
├── README.md                      # Project overview and entry point
├── PROJECT_RULES.md               # Rules, anti-hallucination, and conventions
├── ARCHITECTURE.md                # System architecture and design decisions
├── FOLDER_STRUCTURE.md            # This file
│
├── backend/                       # FastAPI backend
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py                # FastAPI application entry point
│   │   ├── config.py              # Settings and environment variables
│   │   ├── dependencies.py        # FastAPI dependency injection
│   │   │
│   │   ├── api/                   # REST route modules
│   │   │   ├── __init__.py
│   │   │   ├── profile.py
│   │   │   ├── skills.py
│   │   │   ├── experience.py
│   │   │   ├── projects.py
│   │   │   ├── job_descriptions.py
│   │   │   ├── comparisons.py
│   │   │   └── learning.py
│   │   │
│   │   ├── core/                  # Domain services and business logic
│   │   │   ├── __init__.py
│   │   │   ├── models.py          # Pydantic request/response schemas
│   │   │   ├── services/          # Domain services
│   │   │   │   ├── __init__.py
│   │   │   │   ├── profile_service.py
│   │   │   │   ├── skill_service.py
│   │   │   │   ├── comparison_service.py
│   │   │   │   ├── learning_service.py
│   │   │   │   └── verification_service.py
│   │   │   └── exceptions.py      # Domain exceptions
│   │   │
│   │   ├── db/                    # Database access
│   │   │   ├── __init__.py
│   │   │   ├── base.py            # SQLAlchemy base and session
│   │   │   └── models/            # SQLAlchemy ORM models
│   │   │       ├── __init__.py
│   │   │       ├── user.py
│   │   │       ├── skill.py
│   │   │       ├── user_skill.py
│   │   │       ├── evidence.py
│   │   │       ├── project.py
│   │   │       ├── experience.py
│   │   │       ├── education.py
│   │   │       ├── job_description.py
│   │   │       ├── job_requirement.py
│   │   │       ├── comparison.py
│   │   │       ├── learning_resource.py
│   │   │       ├── learning_plan.py
│   │   │       ├── learning_progress.py
│   │   │       └── cv_skill.py
│   │   │
│   │   └── ai/                    # LLM integration
│   │       ├── __init__.py
│   │       ├── client.py          # Provider-agnostic LLM client interface
│   │       ├── providers/         # Provider-specific implementations
│   │       │   ├── __init__.py
│   │       │   └── openai_client.py
│   │       ├── prompts/           # Versioned prompt templates
│   │       │   ├── __init__.py
│   │       │   ├── parse_job_description.txt
│   │       │   ├── normalize_requirements.txt
│   │       │   ├── compare_requirements.txt
│   │       │   └── suggest_resources.txt
│   │       └── schemas.py         # Structured output Pydantic models
│   │
│   ├── alembic/                   # Alembic migrations (single source)
│   ├── tests/                     # Backend tests
│   │   ├── __init__.py
│   │   ├── unit/
│   │   └── integration/
│   ├── pyproject.toml             # Python project metadata
│   ├── requirements.txt             # Production dependencies
│   ├── requirements-dev.txt         # Development dependencies
│   └── Dockerfile                   # Backend container (future)
│
├── database/                      # Database-level artifacts (no migrations)
│   ├── seeds/                     # Seed data templates
│   └── diagrams/                  # Entity-relationship diagrams
│
├── docs/                          # Project documentation
│   ├── decisions/                 # Architecture Decision Records (ADRs)
│   ├── api/                       # API contract drafts
│   └── user-guides/               # How-to guides
│
├── frontend/                      # Next.js frontend
│   ├── app/                       # Next.js App Router
│   │   ├── layout.tsx
│   │   ├── page.tsx
│   │   └── globals.css
│   ├── components/                # React components
│   │   ├── ui/
│   │   ├── profile/
│   │   ├── comparisons/
│   │   └── learning/
│   ├── lib/                       # API clients and utilities
│   │   ├── api.ts
│   │   └── types.ts
│   ├── public/                    # Static assets
│   ├── styles/                    # Tailwind / custom styles
│   ├── package.json
│   ├── tsconfig.json
│   ├── tailwind.config.ts
│   └── next.config.js
│
├── knowledge/                     # Verified knowledge data and templates
│   ├── schemas/                   # JSON/YAML schemas for import
│   ├── templates/                 # Empty templates for user data
│   └── dictionaries/              # Canonical skill taxonomy and categories
│
└── scripts/                       # Automation and utility scripts
    ├── setup/                     # Environment setup helpers
    └── dev/                       # Development helpers
```

## Folder Descriptions

| Folder | Purpose |
|--------|---------|
| `backend/app/api` | REST endpoints grouped by domain. |
| `backend/app/core` | Business logic, domain services, Pydantic schemas, and exceptions. |
| `backend/app/db` | SQLAlchemy ORM models and session management. |
| `backend/app/ai` | LLM client, prompt templates, and structured-output schemas. |
| `backend/alembic` | Single location for Alembic migrations. |
| `database` | Seed data and schema diagrams only. No migrations here. |
| `docs` | Architecture, rules, API contracts, ADRs, and user guides. |
| `frontend` | Next.js application, components, API client, and styles. |
| `knowledge` | Templates, import schemas, and canonical skill dictionaries. |
| `scripts` | Setup and development automation. |

## Notes

- Empty `__init__.py` files and package directories will be created when code is generated.
- `pgvector` support will be added to the database layer later without changing the folder layout.
- RAG components will live under `backend/app/ai/` as additional modules when introduced.
- The backend intentionally avoids a generic repository abstraction in Version 1.
