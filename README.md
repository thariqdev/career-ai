# Career AI

A personal career and technical-knowledge system.

## What it does

Career AI helps you manage your verified technical background and compare it against job descriptions.

1. Store verified skills, projects, work experience, and evidence.
2. Paste a job description.
3. Extract technical requirements automatically and normalize them to canonical skills.
4. Compare each requirement against your verified evidence.
5. Categorize every requirement as `VERIFIED`, `PARTIAL`, `PROVISIONAL`, or `NOT_VERIFIED`.
6. Identify skill gaps.
7. Recommend learning resources in two modes:
   - **THEORY / INTERVIEW**
   - **TECHNICAL / PRACTICAL**
8. Track learning progress explicitly.
9. Prepare for interviews based on the skills a job requires.

## Core Principle: No Hallucination

The system never invents your skills, experience, project involvement, years of experience, or proficiency.

- PostgreSQL is the source of truth for all personal career information.
- The LLM is an assistant, not an authority.
- Personal claims come only from structured, verified evidence.
- If the system lacks verified information, it says:
  > "Not enough verified information."
- `VERIFIED` requires concrete, reviewable evidence. Self-assessment alone is not enough.

## Verification Statuses

| Status | Meaning |
|--------|---------|
| `VERIFIED` | Sufficient evidence that you have worked with or demonstrated the skill. |
| `PARTIAL` | Some evidence exists, but not enough for strong/full proficiency. |
| `PROVISIONAL` | You reported or are learning the skill; sufficient evidence has not been recorded. |
| `NOT_VERIFIED` | No relevant evidence exists. |

## CV Skills vs Verified Knowledge

The system distinguishes between:

- **Skills you have verified evidence for.**
- **Skills currently on your CV.**
- **Skills a job description requires.**

Examples:

- You have verified Docker experience, but it is missing from your CV.
  - Knowledge status: `VERIFIED`
  - CV status: `MISSING_FROM_CV`
  - Recommendation: "Consider adding Docker to your CV."

- A job requires AWS, but you have no verified AWS evidence.
  - Knowledge status: `NOT_VERIFIED`
  - CV status: `NOT_PRESENT`
  - Recommendation: "Do not claim AWS experience on your CV. Learn and gain evidence first."

## Canonical Skill Taxonomy

The system uses a canonical skill taxonomy rather than simple keyword matching.

- `React.js` matches `React`, `ReactJS`, `React.js`.
- `PostgreSQL` matches `PostgreSQL`, `Postgres`.
- But `Next.js` ≠ `Node.js`, `React.js` ≠ `React Native`, `PostgreSQL` ≠ `MySQL`.

The LLM assists with extraction and normalization; the backend validates the final mapping.

## Technology Stack

| Layer | Technology |
|-------|------------|
| Frontend | Next.js, TypeScript, Tailwind CSS |
| Backend | Python, FastAPI, SQLAlchemy |
| Database | PostgreSQL |
| AI | LLM API with structured outputs |
| Future | RAG, pgvector |

## Project Status

**Phase 1 in progress: Backend foundation.**

The foundation documents are approved. The basic FastAPI backend skeleton has been created:

- `backend/app/main.py` — FastAPI entry point
- `backend/app/config.py` — environment configuration
- `backend/app/api/health.py` — `GET /health` endpoint
- `backend/app/api/skills.py` — `/skills` endpoints (create, list, resolve, add alias); `backend/app/api/errors.py` maps domain errors to HTTP statuses
- `backend/app/db/base.py` — SQLAlchemy engine/session/base
- `backend/alembic/` — initial Alembic configuration
- `backend/tests/test_health.py` — health endpoint test

A minimal, intentionally unstyled frontend skeleton now also exists (see "Phase 2 — Frontend Setup" below) — a real design pass is still a separate future task. (This section is otherwise stale — the backend has grown well past this skeleton; see `HANDOFF.md` for the current state.)

## Proposed Structure

See [FOLDER_STRUCTURE.md](FOLDER_STRUCTURE.md) for the full layout.

High-level:

```text
career-ai/
├── backend/        FastAPI + SQLAlchemy + domain logic
├── database/       Seeds and diagrams only
├── docs/           Architecture, rules, API contracts
├── frontend/       Next.js + TypeScript + Tailwind CSS
├── knowledge/      Verified data templates and canonical skill dictionaries
└── scripts/        Automation and utility scripts
```

## Development Phases

1. **Phase 1 — Backend foundation:** FastAPI, PostgreSQL, SQLAlchemy, Alembic, domain models, verification rules, basic REST APIs, health check, tests.
2. **Phase 2 — Frontend:** Next.js, TypeScript, Tailwind CSS, connect to backend APIs.
3. **Phase 3 — Job analysis:** Job description input, structured extraction, canonical skill normalization, deterministic comparison.
4. **Phase 4 — AI integration:** LLM provider, structured outputs, resource recommendations, interview generation.
5. **Phase 5 — RAG / pgvector:** Embeddings, semantic search, grounded knowledge retrieval.

## Phase 1 — Backend Setup

These instructions assume you are in the `backend/` directory.

### 1. Create and activate a virtual environment

**Windows:**

```powershell
python -m venv .venv
.venv\Scripts\activate
```

**macOS/Linux:**

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 2. Install dependencies

```bash
pip install -r requirements-dev.txt
```

### 3. Configure environment variables

Copy the example file and update the values:

```bash
cp .env.example .env
```

Edit `.env` to match your PostgreSQL instance:

```env
DEBUG=false
DATABASE_URL=postgresql+pg8000://user:password@localhost:5432/career_ai
```

### 4. Start FastAPI

```bash
uvicorn app.main:app --reload
```

The API will be available at `http://127.0.0.1:8000`.

You can test the health endpoint with:

```bash
curl http://127.0.0.1:8000/health
```

Expected response:

```json
{
  "status": "ok"
}
```

Skills endpoints (skills are a shared taxonomy; there is no authentication yet):

| Endpoint | Purpose |
|----------|---------|
| `POST /skills` | Create a canonical skill (`{"name": "...", "category": "..."}`) |
| `GET /skills` | List skills ordered by name |
| `GET /skills/resolve?text=...` | Look up the skill a text refers to (`404` if unknown; never creates anything) |
| `GET /skills/similar?name=...` | Existing skills that look the same once spaces, punctuation and case are ignored ("pytho n" → Python); a warning helper only |
| `DELETE /skills/{skill_id}` | Delete a skill nothing uses (its nicknames go with it); `409` with the reason if it's claimed, in a job requirement, on your CV, holding saved links, or in learning progress |
| `POST /skills/{skill_id}/aliases` | Add an alias to a skill (`{"alias": "..."}`) |
| `DELETE /skills/{skill_id}/aliases?alias=...` | Remove one of the skill's aliases (case and extra spaces ignored); returns the updated skill |
| `GET /skills/{skill_id}/learning-resources` | Per learning mode: a ready-made YouTube search link plus the links you've saved |
| `POST /skills/{skill_id}/learning-resources` | Save a link (`{"mode": "theory_interview" \| "technical_practical", "title": "...", "url": "https://..."}`) |
| `DELETE /learning-resources/{id}` | Remove a saved link |
| `PUT /skills/{skill_id}/learning-progress` | Set your progress on a skill (`{"status": "not_started" \| "studying" \| "finished"}`); never changes verification |
| `GET /learning-progress` | Every skill you've started or finished studying |
| `POST /cv/scan` | Preview only: upload a CV (`file`: PDF, .docx or .txt, up to 5 MB) or paste it (`text`), as form data; returns which saved skills it mentions. Saves nothing, and the CV is never stored |
| `PUT /cv/presence` | Save your confirmed choices after a scan (`{"present_skill_ids": [...], "absent_skill_ids": [...]}`) |
| `GET /cv/status` | Combined proof + CV status (and any advice) for every skill you've claimed or marked on your CV, in one request |

`GET /me` returns the single hardcoded user this system runs as (created automatically on first call).

Job-description endpoints (all scoped to that one user automatically — no `user_id` in any request):

| Endpoint | Purpose |
|----------|---------|
| `POST /job-descriptions` | Paste a job description (`{"raw_text": "..."}`) |
| `GET /job-descriptions` | List all of your job descriptions, most recently created first |
| `GET /job-descriptions/{id}` | Read one back, with its requirements |
| `POST /job-descriptions/{id}/extract` | Extract requirements from the text — by default, finds your saved skills (and their aliases) in it; Claude-backed instead if `ANTHROPIC_API_KEY` is set |
| `POST /job-descriptions/{id}/compare` | Compare its requirements against your verified skills |
| `GET /job-descriptions/{id}/gaps` | The requirements you're not yet `VERIFIED` for |

Interactive API docs are served at `http://127.0.0.1:8000/docs`.

**How requirements are extracted:** by default (no `ANTHROPIC_API_KEY` in `.env`), `/extract` uses a skill-list matcher. It looks for every skill name and alias you've saved, whole words only, and turns each one it finds into a requirement using the posting's exact words. It is free, instant, and can't invent anything, but it only finds skills you've already added. To use the Claude-backed extractor instead, add a real key to `.env` (`ANTHROPIC_API_KEY=sk-ant-...`) and restart the server. This costs money per call. Either way, the same validation rules apply (see `requirement_service`).

### 5. Run tests

```bash
pytest
```

This will run the health endpoint test in `tests/test_health.py`. The test suite does not require a running PostgreSQL server.

## Phase 2 — Frontend Setup

A minimal Next.js frontend now exists in `frontend/` (App Router, TypeScript, Tailwind CSS v4 — scaffolded with `create-next-app`). It now has a shared design token system (colors/fonts, see `HANDOFF.md`) and a shared header that appears on every page, but is otherwise still deliberately basic — the first real page is functional, not designed.

```bash
cd frontend
npm install
cp .env.local.example .env.local   # defaults to http://127.0.0.1:8000, adjust if needed
npm run dev
```

The dev server runs at `http://localhost:3000`. With the backend also running (`uvicorn app.main:app --reload`, see above):

- **`/` is the real Dashboard** now (the old `/health`+`/me` proof page is gone — `GET /me`'s result is still visible via the header's email chip). It shows three numbers (verified skills, open gaps across every job description, job descriptions analyzed), a "Skills to learn" list (every gap skill across all your job descriptions, the ones needed by the most jobs first), the most recent comparison's gaps inline, and a list of CV recommendations pulled from every skill's combined status. Every gap skill gets YouTube search buttons for both learning modes and a link to its skill page, plus a "studying" or "finished studying" tag if you've set one.
- **`/skills`** lists every skill from `GET /skills` (with its nicknames shown as "also: …"), shows each one's verification status and CV-presence status as colored badges, lets you click a CV badge to flip it (`PATCH /skills/{id}/cv-presence`), and has a small form to add a new skill (`POST /skills`) — duplicate or blank names show the backend's own error message. Before adding, it checks for look-alikes and asks "looks like Python. Add anyway?".
- **`/job-descriptions`** paste a job posting's text and it walks through the real backend pipeline in order: `POST /job-descriptions` → `POST .../extract` → `POST .../compare` → `GET .../gaps`, showing a step-by-step status. Requirements are the saved skills found in the posting (see "How requirements are extracted" above); if none are found, the page says so and points you to the Skills page. Each gap comes with its current CV status ("CV: present" / "missing from cv" / "not present"), any CV advice (e.g. "listed on your CV without verified evidence"), YouTube search buttons, and a link to that skill's page. It's single-shot: "analyze another" just resets the form.
- **`/skills/{id}`** click a skill's name on `/skills` to land here. It shows the skill's CV/knowledge status, lets you claim it (`POST /user-skills`), attach and link real evidence to it (`POST /evidence`, `POST /user-skills/{id}/evidence-links`), and change its verification status (`POST /user-skills/{id}/status`) with four real buttons — no client-side guessing about whether a status change is allowed. Try clicking "verified" with no evidence linked: the backend genuinely rejects it (409, "Not enough verified information"), and the page shows that exact message. Link a piece of evidence first and the same click succeeds. A "Nicknames" section lets you add or remove the skill's aliases; the requirement reader finds a skill by any of them. A "Learning progress" row (Not started / Studying / Finished studying) records how far you are. Finishing never marks a skill verified; the page reminds you to add evidence instead. A "Learning resources" section shows two columns (Theory / Interview, Technical / Practical), each with a YouTube search button that opens YouTube's own live search, plus links you've saved yourself, which you can add or remove. No API key needed. At the bottom, "Delete skill" removes a skill that nothing uses yet (e.g. a typo).
- **`/cv` (My CV)**: upload your CV (PDF, Word .docx or .txt) or paste it, and the app finds which of your saved skills it mentions, using the same whole-word, nickname-aware matching as job postings. You review the ticks and click Save; only then do the skills' "on my CV" badges update. Skills marked on your CV but not found in this one are listed unticked, so nothing is removed by accident. The CV is read locally and not stored. Being on your CV never verifies a skill.

**CORS:** the backend only allows browser requests from `http://localhost:3000` and `http://127.0.0.1:3000` (see `backend/app/main.py`) — a dev-only allow-list, not `"*"`, since there's no auth yet. It will need revisiting once real auth exists.

## Next Steps

1. Review the created backend files.
2. Approve this milestone.
3. Continue to the next milestone: creating the first SQLAlchemy domain models and initial Alembic migration.

## License

Personal project. All rights reserved.
