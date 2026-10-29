# Career AI

A personal career and technical-knowledge system: it keeps track of the skills you can actually prove, reads job postings, shows how well you match each job and what to learn next, and has a grounded AI assistant that answers questions only from your own data.

**Live app:** https://career-ai-inky-ten.vercel.app. It's my own Career AI with my real CV and job applications (there's no login, so anyone with the link can see it). The Assistant runs on free hosted AI models, so the first visit after a quiet spell can take up to a minute. To run it as a public demo with made-up data instead, see below.

**How the AI assistant was built and measured:** [docs/RAG_CASE_STUDY.md](docs/RAG_CASE_STUDY.md) (a write-up), and [docs/RAG_GUIDE.md](docs/RAG_GUIDE.md) (the stage-by-stage guide).

## Highlights

- **Proof-based skills.** Each skill is `VERIFIED`, `PARTIAL`, `PROVISIONAL` or `NOT_VERIFIED`, and the first two need linked evidence (enforced by the backend, not the UI).
- **Job matching.** Paste a posting: requirements are extracted against a canonical skill taxonomy (aliases, look-alike guards), compared with your proof, and turned into a match percentage, gaps, a "skills to learn" ranking and a printable interview prep sheet, all from one source of truth.
- **Application tracking.** Status, dates, notes and the next interview (with a calendar file).
- **A grounded RAG assistant.** Hybrid search (BM25 + embeddings, fused with RRF), read-only SQL tools for exact lists and counts, a local model (Ollama) that must cite its notes or the notes are shown instead, prompt-injection sanitizing, streaming, and confirmed actions. Every step was judged on test sets frozen *before* the code and tracked in a scorecard.
- **Practice.** Leitner-box flashcards from the RAG guide and from each job's prep sheet.
- **Your data stays yours.** Export everything as JSON, restore into an empty app, and nothing is sent to a paid API unless you set a key.

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
| Frontend | Next.js 16 (App Router), TypeScript, Tailwind CSS v4 |
| Backend | Python, FastAPI, SQLAlchemy 2, Alembic, pytest |
| Database | PostgreSQL (pg8000 driver) |
| AI (optional, free) | Ollama on your own computer: `llama3.2` (reading postings, writing answers), `nomic-embed-text` (meaning search) |
| AI (optional, paid) | Claude, for the job-posting reader, only if `ANTHROPIC_API_KEY` is set |
| Hosting (demo) | Vercel (frontend), Render (backend, Docker), Neon (PostgreSQL), GitHub Actions (daily reset) |

## Architecture

```text
browser ── Next.js (frontend/) ──HTTP/JSON──> FastAPI (backend/app/api)
                                                  │
                                    services (backend/app/core/services): the rules,
                                    deterministic; the AI only proposes, the backend validates
                                                  │
                                    SQLAlchemy models ──> PostgreSQL (the source of truth)

Assistant (backend/app/rag): question ─> small talk / actions / general-vs-personal
  ─> read-only SQL tools or hybrid search over notes built from the database
  ─> optional local model writes a cited answer ─> faithfulness check ─> streamed reply
```

More detail: [ARCHITECTURE.md](ARCHITECTURE.md), [PROJECT_RULES.md](PROJECT_RULES.md), and [HANDOFF.md](HANDOFF.md) (the technical notes for each stage).

```text
career-ai/
├── backend/     FastAPI app, services, models, Alembic migrations, RAG assistant, tests
├── frontend/    Next.js app
├── docs/        RAG guide and case study
├── render.yaml  Render Blueprint for the demo backend
└── .github/     the daily demo reset
```

## Run it locally: backend

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

Then create a PostgreSQL database (e.g. `career_ai`) and, after step 3, bring its tables up to date with `alembic upgrade head`.

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
| `POST /cv/replace` | "Start fresh with this CV" (for a different person): removes the current person's data (name, profile, proof, claims, CV marks, jobs and results, learning progress, ratings; the skill list and study links stay), adds the new CV's skills as provisional, and returns its projects, work and education as drafts to review. The page downloads a backup first |
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

The test suite (800+ tests) uses throwaway in-memory databases, so it never touches your PostgreSQL data and needs no running server.


**Start from scratch.** To empty the database (a backup is saved first to `backend/backups/`, which "Restore from backup" accepts), stop the backend and run, from `backend/`:

```bash
.venv/Scripts/python scripts/reset_data.py --yes
```

## Run it locally: frontend

The frontend lives in `frontend/` (Next.js App Router, TypeScript, Tailwind CSS v4, with a shared design-token system: see `HANDOFF.md`).

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

**CORS:** by default the backend only allows browser requests from `http://localhost:3000` and `http://127.0.0.1:3000`. A deployment sets `CORS_ORIGINS` (comma-separated) to its own site. There is no login (it's a single-user tool), which is why the public demo holds only made-up data.

## AI in production (without Ollama)

Locally the assistant runs on Ollama (free, nothing leaves your computer). A free server has no GPU and not enough memory for that, so production uses hosted free tiers instead. Only the model behind each step changes; the assistant's routing, sanitizing and checks are the same.

| Step | Local | Production |
|---|---|---|
| Meaning search (embeddings) | `nomic-embed-text` via Ollama | `gemini-embedding-2`, 768 dims (`EMBED_PROVIDER=gemini`) |
| Writing answers | `llama3.2` via Ollama | Groq `openai/gpt-oss-20b`, then Gemini `gemini-3.5-flash-lite` if Groq fails, then the notes themselves (`CHAT_PROVIDER=groq`) |
| Stored vectors | `note_embeddings` table (text column) | `note_embeddings` table (pgvector `vector` column on Neon) |

- **Keys** live only in the server's environment (`GROQ_API_KEY`, `GEMINI_API_KEY`), never in the frontend, never committed.
- **Only notes are sent:** the models see the retrieved notes (and, for embeddings, each note's text). On the demo these are made-up data. Free tiers may use what they receive to improve their products, so don't point them at real personal data.
- **Rate limits:** a 429 from Gemini embeddings is retried with backoff; a busy or stuck writer (20 s without a byte) hands over to the next one at once.
- **Vectors are stored** per (note text, model, size), so a restart doesn't re-embed every note, and vectors from different models are never compared.

**Measured with the production models** (`EMBED_PROVIDER=gemini CHAT_PROVIDER=groq python -m app.rag.scorecard --full`, same frozen test sets, made-up career; one run on 2026-10-29):

| Measure | llama3.2 / nomic (baseline) | Gemini + Groq |
|---|---|---|
| Hybrid search MRR | 0.933 | **0.967** |
| Follow-ups, glued (live), MRR | 0.637 | **0.713** |
| Answer completeness | 1.000 | 0.991 (within tolerance) |
| Same facts every run (of 15) | 15 | 14 (within tolerance) |
| LLM judge: wrong answers caught / good answers wrongly rejected | unusable (rejected 8/8 good) | **8/8 caught, 0/8 false alarms** |
| Prompt attacks with no defence | 21/32 | **6/32** |
| Held-out attacks after cleaning | 3/24 | **5/24 (worse)** |

`MIN_COSINE = 0.6` still separates right notes (0.69 to 0.81) from the two documented off-topic questions (0.52, 0.58).

**Checked on the live demo (Render + Neon, 2026-10-29):** five questions in a row all used hybrid search, with no rate-limit errors; the first took 6.7 s (it embeds and stores the notes), the rest 1.8 to 2.9 s. Two bugs only showed up there and are fixed: vectors were sent as `VARCHAR` (and, for several rows, typed as `text`), which pgvector refused, so nothing was stored and every question re-embedded all notes until Gemini's free limit (100 texts a minute) answered 429.

### What is broken or unfinished

- **Search doesn't use pgvector yet.** Vectors are stored in PostgreSQL, but ranking is still cosine in Python (fine for dozens of notes, not for thousands).
- **Held-out prompt attacks got worse (3/24 → 5/24).** gpt-oss follows instructions hidden in job text more readily; two attack wordings ("recommend Rust", "answer in Spanish" in a title) get past the block-list.
- **Only 20 of 45 AI answers were kept**; the rest fell back to the notes (no citation, or a failed check). There's no earlier number to compare with.
- **The LLM judge now works but isn't switched on.** Turning it on changes the assistant's logic, so it needs a fresh test set first.
- **One run only.** The rewritten follow-ups scored better too (MRR 0.812 vs 0.713 glued), but a single run isn't evidence (stage 75); the rewrite stays off.
- **No production latency numbers.** `latency_eval` and `router_eval` still measure Ollama only.
- **No warm-up with hosted models.** Startup pre-indexing only runs for Ollama, so the first question after a fresh database embeds every note (afterwards they're stored).
- **"Start fresh with this CV" leaves the old person's note vectors** in `note_embeddings` (vectors only, no text). The demo's daily reset empties them.
- **`gemini-3.8-flash` was overloaded** on the free tier (timeouts, 503) in testing, so the fallback is Flash-Lite.

## Deploy it (free tiers)

**Two ways to run it.** As your own app (`DEMO_MODE=false`, what `render.yaml` sets now): your real data stays, and you can restore a "Download my data" backup into the empty live database. As a **public demo** (`DEMO_MODE=true`): an empty database is filled with a fictional career at startup, backup import/restore is switched off, and `POST /demo/reset` (protected by a secret token) puts everything back. Never point a demo at your real data.

1. **Database (Neon):** create a project and copy its connection string (`postgresql://...?sslmode=require` works as pasted).
2. **Backend (Render):** New > Blueprint > this repo. `render.yaml` builds `backend/Dockerfile`, which runs `alembic upgrade head` and starts the API. Fill in `DATABASE_URL` (from Neon) and `CORS_ORIGINS` (the Vercel URL from step 3; you can set it after step 3). `DEMO_RESET_TOKEN` is generated: copy it for step 4.
3. **Frontend (Vercel):** import this repo with root directory `frontend`, and set `NEXT_PUBLIC_API_BASE_URL` (the Render URL) and `NEXT_PUBLIC_DEMO_MODE=true` (shows the demo banner).
4. **Daily reset (GitHub):** in the repo's Settings > Secrets and variables > Actions, add the secret `DEMO_RESET_TOKEN` and the variable `DEMO_API_URL` (the Render URL). `.github/workflows/demo-reset.yml` then runs every day at 03:00 UTC, and on demand from the Actions tab.
5. **AI on the server (optional, free):** paste `GROQ_API_KEY` and `GEMINI_API_KEY` into Render's Environment (both are `sync: false` in `render.yaml`, so they're never in the repo). `render.yaml` already sets `EMBED_PROVIDER=gemini` and `CHAT_PROVIDER=groq`. Without the keys the Assistant still works, answering with the matching notes.

Free servers sleep when idle, so the first visit after a quiet spell can take up to a minute.

## License

Personal project. All rights reserved.
