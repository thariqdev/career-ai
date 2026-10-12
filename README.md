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
| `PATCH /skills/{skill_id}` | Rename and/or re-categorize a skill (`{"name": "...", "category": "..."}`, only fields sent change); `409` if the name is already used by any skill or nickname. Claims, evidence and the rest follow the rename |
| `POST /skills/{source_id}/merge-into/{target_id}` | Merge a duplicate skill into another: its job requirements, nicknames, claim (with evidence), saved links, learning progress (the further-along one wins) and CV mark move over, its name becomes a nickname, and it is removed; `409` if both skills are claimed, `422` for merging a skill into itself |
| `DELETE /skills/{skill_id}` | Delete a skill nothing uses (its nicknames go with it); `409` with the reason if it's claimed, in a job requirement, on your CV, holding saved links, or in learning progress |
| `POST /skills/{skill_id}/aliases` | Add an alias to a skill (`{"alias": "..."}`) |
| `DELETE /skills/{skill_id}/aliases?alias=...` | Remove one of the skill's aliases (case and extra spaces ignored); returns the updated skill |
| `GET /skills/{skill_id}/learning-resources` | Per learning mode: a ready-made YouTube search link plus the links you've saved |
| `POST /skills/{skill_id}/learning-resources` | Save a link (`{"mode": "theory_interview" \| "technical_practical", "title": "...", "url": "https://..."}`) |
| `DELETE /learning-resources/{id}` | Remove a saved link |
| `PUT /skills/{skill_id}/learning-progress` | Set your progress on a skill (`{"status": "not_started" \| "studying" \| "finished"}`); never changes verification |
| `GET /learning-progress` | Every skill you've started or finished studying |
| `GET /skills/{skill_id}/learning-path` | The four-step path for a skill (start learning, finish, prove it, get verified), each step `done` / `current` / `todo`, worked out only from what you've recorded |
| `GET /learning-paths?skill_ids=1&skill_ids=2` | The same for several skills in one request (unknown ids are skipped) |
| `POST /profile/cv-drafts` | Read a CV (multipart `file` or `text`) into **draft** projects, work experience and education for you to review on My Profile ("Fill from my CV"). Saves nothing and never stores the CV; saving uses the normal add endpoints |
| `POST /cv/add-all` | "Add all my CV skills": saves every skill the CV mentions, marks it on your CV and claims it as **provisional** (never verified: a CV isn't proof). Running it again adds nothing |
| `GET /job-descriptions/{id}/match` | Your match for a job, always current: `percent`, and which of its skills are `proven`, `on_cv` (not proven yet) or `missing` (including common skills it names that you don't have) |
| `POST /assistant/ask` | The Career AI assistant (RAG, stage 1): `{"question": "..."}` returns the best-matching notes from your own data (BM25 keyword search) as numbered `sources`, each with a link. No AI model yet, so answers come only from your data; "not found" when nothing matches. See `docs/RAG_GUIDE.md`. Measure its search quality with `.venv/Scripts/python -m app.rag.evaluate` (from `backend/`). With `OLLAMA_EMBED_MODEL=nomic-embed-text` in `backend/.env` (and Ollama running) it adds meaning search (hybrid keyword + embeddings); the reply says which search was used |
| `POST /assistant/ask/stream` | The same answer as `/assistant/ask`, streamed as NDJSON: a `meta` line (sources, retrieval), many `delta` lines (pieces of text), an optional `replace` (the checked final text), then `done` (`written_by`: `ai` or `notes`). Send `history` (the last few `{role, text}` turns) for follow-ups. With `OLLAMA_CHAT_MODEL=llama3.2` a local model writes the answer from the notes and must cite them, or the notes are shown instead. Used by the chat (the 💬 button on every page, and `/assistant`) |
| `POST /assistant/feedback` | Rate one assistant answer 👍/👎: `{message_id, rating: "up"|"down", question, answer, sources, retrieval, written_by, comment}`. Rating the same `message_id` again replaces it. Review the 👎 with `.venv/Scripts/python -m app.rag.feedback_report` (from `backend/`) |
| `GET /assistant/feedback` | Your ratings, newest first; `?rating=down` for the ones to learn from |
| `GET /practice/rag-questions` | Interview flashcards parsed from `docs/RAG_GUIDE.md`'s "Interview questions you can now answer" sections: `[{id, stage, stage_title, question, answer}]`. Used by the **Practice** page (Leitner boxes; progress kept in the browser) |
| `GET /practice/job-questions` | Flashcards from each job's interview prep sheet: one per saved requirement linked to a skill (stage = job id, stage_title = its name). The answer is the prep sheet's own text: claim it with your proof, or don't bluff and what to study |
| `POST /skills/from-catalogue` | `{"name": "AWS"}`: save a common catalogue skill (by name or nickname) with its category and free nicknames. Returns `{skill, created}`; if you already have it under any name, returns that one (`created: false`). 404 for anything not in the catalogue. Adds the skill to the list you track only: no claim, no CV mark |
| `GET /export` | Download everything stored for you (skills, claims, evidence, profile, jobs and results, CV marks, learning progress and links) as one JSON file; read-only. Also on My Profile as "Download my data" |
| `POST /import/preview` | Upload a backup file (multipart `file`): returns what it holds, every problem found, and whether this app is empty. Writes nothing |
| `POST /import` | Restore a backup into an **empty** app, all or nothing: `422` for an invalid file (broken links, verified without evidence, bad links…), `409` if the app already has data. On My Profile as "Restore from backup" |
| `POST /cv/scan` | Preview only: upload a CV (`file`: PDF, .docx or .txt, up to 5 MB) or paste it (`text`), as form data; returns which saved skills it mentions. Saves nothing, and the CV is never stored |
| `PUT /cv/presence` | Save your confirmed choices after a scan (`{"present_skill_ids": [...], "absent_skill_ids": [...]}`) |
| `GET /cv/status` | Combined proof + CV status (and any advice) for every skill you've claimed or marked on your CV, in one request |
| `GET` / `POST /projects`, `DELETE /projects/{id}` | Your projects (name required; link must be http(s)) |
| `GET` / `POST /work-experiences`, `DELETE /work-experiences/{id}` | Your jobs (company, role and start date required) |
| `GET` / `POST /educations`, `DELETE /educations/{id}` | Your education (school required) |

Each of these, and evidence, can also be edited with `PATCH` (e.g. `PATCH /projects/{id}`, `PATCH /evidence/{id}`): only the fields you send change, `null` clears an optional field, and every rule is re-checked on the record as it will be after the edit. Editing evidence never changes a skill's verification status.

Profile records are listed most recent first; an end date can't be before a start date, and a record can't be removed while evidence comes from it (`409`). Evidence (`POST /evidence`) can name **at most one** source via `project_id`, `work_experience_id` or `education_id`; this is enforced by the API (`422`) and by a database check constraint.

Removing evidence keeps the "verified needs proof" rule true:

| Endpoint | Purpose |
|----------|---------|
| `DELETE /user-skills/{id}` | Remove a claim (its evidence links go; the evidence itself and the skill are kept). `409` naming the jobs if past comparison results use it: delete those jobs first |
| `DELETE /user-skills/{id}/evidence-links/{evidence_id}` | Unlink evidence from a skill (the evidence is kept). `409` if it's the last evidence of a `VERIFIED`/`PARTIAL` skill: change its status first |
| `DELETE /evidence/{id}` | Delete evidence; `409` while it's linked to a skill or cited by a past comparison result |

`GET /me` returns the single hardcoded user this system runs as (created automatically on first call). `PATCH /me` with `{"full_name": "..."}` saves your name (blank clears it). "Add all my CV skills" fills the name in from the top of the CV when none is saved yet (`name_saved` in its reply), and "Fill from my CV" on Profile shows it (`name`). The assistant answers "what is my name?" from it.

Job-description endpoints (all scoped to that one user automatically — no `user_id` in any request):

| Endpoint | Purpose |
|----------|---------|
| `POST /job-descriptions` | Paste a job description (`{"raw_text": "..."}`) |
| `GET /job-descriptions` | List all of your job descriptions, most recently created first, each with `match_percent` (null when there's nothing to compare yet: no requirements, or no CV) and `match_total` (skills the job asks for), from the same always-current match as `/job-descriptions/{id}/match` |
| `GET /job-descriptions/{id}` | Read one back, with its requirements |
| `DELETE /job-descriptions/{id}/requirements/{requirement_id}` | Remove one requirement with its own comparison results; the rest of the job is untouched. `404` if it isn't a requirement of that job. Its skill is remembered as "not for this job", so "Look for new skills" won't add it back |
| `GET /job-descriptions/{id}/dismissed` | Skills removed from this job (re-reading the posting skips them) |
| `DELETE /job-descriptions/{id}/dismissed/{skill_id}` | "Allow again": forget that removal, so the next "Look for new skills" may find it; adds nothing by itself |
| `PATCH /job-descriptions/{id}/application` | Your application for this job: `{"status": "applied", "applied_on": "2026-09-01", "notes": "…"}` (only fields sent change). Status is saved / applied / interviewing / offer / rejected / withdrawn; "applied" with no date records today; no future dates; a saved job has no date. Also `next_interview_at` (an ISO time with a time zone, or null): only while applied or interviewing, cleared otherwise; never changes the status by itself |
| `GET /job-descriptions/{id}/suggestions` | Common skills (from a built-in catalogue of about 230) the posting mentions that you haven't saved yet. Read-only; the CV scan returns the same `suggestions` for your CV |
| `DELETE /job-descriptions/{id}` | Delete a job together with its requirements and comparison history; skills, claims, evidence and CV marks are untouched |
| `POST /job-descriptions/{id}/extract` | Extract requirements from the text — by default, finds your saved skills (and their aliases) in it; Claude-backed instead if `ANTHROPIC_API_KEY` is set |
| `POST /job-descriptions/{id}/compare` | Compare its requirements against your verified skills |
| `POST /job-descriptions/{id}/extract-new` | Look again: add only requirements this job doesn't already have (e.g. skills saved since); existing requirements and results are never changed |
| `GET /job-descriptions/extractor` | Which requirement reader is active (`skill_list`, free; `ollama`, free and local, with its `model`; or `claude`, paid), so the UI can warn before a paid call |
| `GET /job-descriptions/{id}/interview-prep` | An interview prep sheet: per requirement, what you can honestly say (fixed templates filled only with your current claims, linked evidence and CV status; nothing generated) |
| `GET /job-descriptions/{id}/results` | The latest status of every requirement, verified ones included (comparing again adds new results; old ones are kept) |
| `GET /job-descriptions/{id}/gaps` | The requirements you're not yet `VERIFIED` for |

Interactive API docs are served at `http://127.0.0.1:8000/docs`.

**How requirements are extracted:** by default (no `ANTHROPIC_API_KEY` in `.env`), `/extract` uses a skill-list matcher. It looks for every skill name and alias you've saved, whole words only, and turns each one it finds into a requirement using the posting's exact words. It is free, instant, and can't invent anything, but it only finds skills you've already added. To use the Claude-backed extractor instead, add a real key to `.env` (`ANTHROPIC_API_KEY=sk-ant-...`) and restart the server. This costs money per call. Either way, the same validation rules apply (see `requirement_service`).

**Optional free AI reader (Ollama).** To also spot skills you haven't saved yet, install [Ollama](https://ollama.com) (free, runs on your own computer), run `ollama pull llama3.2` (about 2 GB), and add `OLLAMA_MODEL=llama3.2` to `backend/.env`, then restart the backend. The app then uses your skill list **plus** the local model. Skills the model finds that you haven't saved appear on the job page under "Mentioned in this posting, not in your skills yet", each with an **Add skill** button. The model can't invent requirements: everything must appear word-for-word in the posting, and it never creates skills or claims. If Ollama isn't running, the app quietly uses your skill list alone and says so. A Claude key, if set, takes priority.

### 5. Run tests

```bash
pytest
```

This will run the health endpoint test in `tests/test_health.py`. The test suite does not require a running PostgreSQL server.


**Start from scratch.** To empty the database (a backup is saved first to `backend/backups/`, which "Restore from backup" accepts), stop the backend and run, from `backend/`:

```bash
.venv/Scripts/python scripts/reset_data.py --yes
```

## Phase 2 — Frontend Setup

A minimal Next.js frontend now exists in `frontend/` (App Router, TypeScript, Tailwind CSS v4 — scaffolded with `create-next-app`). It now has a shared design token system (colors/fonts, see `HANDOFF.md`) and a shared header that appears on every page, but is otherwise still deliberately basic — the first real page is functional, not designed.

```bash
cd frontend
npm install
cp .env.local.example .env.local   # defaults to http://127.0.0.1:8000, adjust if needed
npm run dev
npm test     # quick checks for the "Skills to learn" ranking (Node's built-in runner)
```

The dev server runs at `http://localhost:3000`. With the backend also running (`uvicorn app.main:app --reload`, see above):

- **`/` is the real Dashboard** now (the old `/health`+`/me` proof page is gone — `GET /me`'s result is still visible via the header's email chip). It shows three numbers (verified skills, open gaps across every job description, job descriptions analyzed), a "Skills to learn" list (gap skills from your open jobs: the ones your applied/interviewing jobs need come first, then the ones most jobs need; jobs with an offer, rejection or withdrawal aren't counted), the most recent comparison's gaps inline, and a list of CV recommendations pulled from every skill's combined status. Every gap skill gets YouTube search buttons for both learning modes, its next learning step (linking to its skill page), plus a "studying" or "finished studying" tag if you've set one.
- **`/skills`** lists every skill from `GET /skills` (with its nicknames shown as "also: …"), shows each one's verification status and CV-presence status as colored badges, lets you click a CV badge to flip it (`PATCH /skills/{id}/cv-presence`), and has a small form to add a new skill (`POST /skills`) — duplicate or blank names show the backend's own error message. Before adding, it checks for look-alikes and asks "looks like Python. Add anyway?".
- **`/job-descriptions`** paste a job posting's text and it walks through the real backend pipeline in order: `POST /job-descriptions` → `POST .../extract` → `POST .../compare` → `GET .../gaps`, showing a step-by-step status. Requirements are the saved skills found in the posting (see "How requirements are extracted" above); if none are found, the page says so and points you to the Skills page. Each gap comes with its current CV status ("CV: present" / "missing from cv" / "not present"), any CV advice (e.g. "listed on your CV without verified evidence"), YouTube search buttons, and a link to that skill's page. "Analyze another" resets the form, and every job you've analyzed is listed under it as "Pasted job descriptions".
- **`/job-descriptions/{id}`**: one job's page, with its requirements and their latest status, its gaps (with CV badges and learning buttons), and the original posting text. **Compare again** re-checks it against what you can prove *now*, e.g. after verifying a skill. Older results are kept, not overwritten. Each requirement has a **Remove** button for a wrong line (its results go with it); removed skills stay removed, listed under "Removed from this job" with an **Allow again** button. **Delete job** (at the bottom) removes it with its own requirements and comparison history. **Look for new skills** re-reads the posting for skills you've saved since, adds only those, and compares them; if a paid Claude key is ever configured, it asks before spending money.
- **`/job-descriptions/{id}/prep`**: the **Interview prep** sheet, linked from each job's page and printable. For each requirement it says what you can honestly claim, which of your evidence to talk about (with its project/job source), warns when an unproven skill is on your CV, and gives study links for what you haven't proven. Every line comes from your own saved data; nothing is made up.
- **`/skills/{id}`** click a skill's name on `/skills` to land here. It shows the skill's CV/knowledge status, lets you claim it (`POST /user-skills`), attach and link real evidence to it (`POST /evidence`, `POST /user-skills/{id}/evidence-links`), and change its verification status (`POST /user-skills/{id}/status`) with four real buttons — no client-side guessing about whether a status change is allowed. "Remove claim" takes the claim back (your evidence is kept), unless past job comparisons use it. Try clicking "verified" with no evidence linked: the backend genuinely rejects it (409, "Not enough verified information"), and the page shows that exact message. Link a piece of evidence first and the same click succeeds. Any evidence can be **edited** (title, description, link, type, source). Linked evidence can be **unlinked**, and unlinked evidence **deleted**; the app refuses either one if it would leave a verified skill without proof or erase comparison history. A "Nicknames" section lets you add or remove the skill's aliases; the requirement reader finds a skill by any of them. A "Learning progress" row (Not started / Studying / Finished studying) records how far you are. Finishing never marks a skill verified; the page reminds you to add evidence instead. A "Learning resources" section shows two columns (Theory / Interview, Technical / Practical), each with a YouTube search button that opens YouTube's own live search, plus links you've saved yourself, which you can add or remove. No API key needed. A **"Your path"** checklist near the top shows the four steps (start learning, finish, prove it, get verified) and which one to do next; studying never ticks "prove it" or "verified". "Edit name / category" fixes a typo or category; everything attached follows the rename. "Merge into another skill" folds a duplicate (like "pytho n") into the real one, suggesting a look-alike. At the bottom, "Delete skill" removes a skill that nothing uses yet.
- **`/cv` (My CV)**: upload your CV (PDF, Word .docx or .txt) or paste it, and the app finds which of your saved skills it mentions, using the same whole-word, nickname-aware matching as job postings. You review the ticks and click Save; only then do the skills' "on my CV" badges update. Skills marked on your CV but not found in this one are listed unticked, so nothing is removed by accident. The CV is read locally and not stored. Being on your CV never verifies a skill.
- **`/profile` (My Profile)**: add, edit and remove your projects, work experience and education. When you add evidence on a skill's page, a "Comes from" dropdown lets you say which of these it comes from, and the evidence list shows it ("from project FundsApp").

**CORS:** the backend only allows browser requests from `http://localhost:3000` and `http://127.0.0.1:3000` (see `backend/app/main.py`) — a dev-only allow-list, not `"*"`, since there's no auth yet. It will need revisiting once real auth exists.

## Next Steps

1. Review the created backend files.
2. Approve this milestone.
3. Continue to the next milestone: creating the first SQLAlchemy domain models and initial Alembic migration.

## License

Personal project. All rights reserved.
