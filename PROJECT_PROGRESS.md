# Career AI — Project Progress

> **What this file is:** a short, plain-language log of what's been built, what's happening now, and what's next. It's the first thing to read at the start of any session on this project, and it gets updated right after every task finishes.
>
> **How this differs from `HANDOFF.md`:** `HANDOFF.md` is the deep technical reference — file-by-file descriptions, exact conventions, design rationale, schema details. This file is the shorter companion: a task-by-task changelog plus "where are we right now." Read this one first to get oriented; go to `HANDOFF.md` when you need the technical detail behind an entry here.
>
> **Workflow this file supports:**
> 1. Before starting a new task, read this file (not just re-derive everything from chat history).
> 2. After finishing a task, add/update its row below with what changed, its status, and a short plain-language summary.
> 3. Before starting the *next* task, quickly re-check the previous entry's "Verified" notes — don't move on if something was left unverified without saying so.

---

## Current Status (as of 2026-09-29)

🟢 **The core loop works end to end over HTTP now.** You can claim a skill, prove it with evidence, link the two, ask for a status change, paste a job posting, pull out its requirements, compare them against what you can prove, and see what's missing — all through real web requests, all automatically scoped to the one hardcoded user. Nothing about the underlying services changed to make this happen; this task only added the HTTP doors to code that already existed and was already tested.

**Environment blocker resolved — for good, not just for now.** `psycopg2` was being blocked by Windows Smart App Control (confirmed via the Windows Code Integrity event log). The project switched database drivers permanently to `pg8000`, a pure-Python driver with no compiled file for Windows to block. Full detail in `HANDOFF.md` §9.

**Housekeeping to keep in mind:** Only one commit exists so far (`ac637fc`, the initial backend foundation through the `JobDescription` model). Everything since — 5 more models, 4 migrations, 5 services, 5 API routers, all their schemas, the driver swap, and roughly 155 tests — is still **uncommitted** in the working tree. Worth committing in logical chunks before the pile grows further.

---

## Completed Tasks

| # | Date | Task | Status | What it means, in plain terms |
|---|------|------|--------|--------------------------------|
| 1 | 2026-09-23 | Read `HANDOFF.md` and resumed the project | ✅ Done | Confirmed the environment actually works (earlier notes said Postgres might be blocked here — it wasn't, at the time), and figured out what to build next. |
| 2 | 2026-09-23 | Built `User`, `Project`, `WorkExperience`, `Education`, `Evidence` (models + migrations + tests) | ✅ Done | These are the database "shapes" for a person's profile: who they are, what they've worked on, and the proof behind any skill claim. Applied to the real database and tested. |
| 3 | 2026-09-23 | Built `UserSkill` + `UserSkillEvidence` (models + migration + tests) | ✅ Done | This is the table that says "this user claims this skill, at this trust level (verified / partial / provisional / not verified)," plus the link table connecting a claim to its proof. |
| 4 | 2026-09-23 | Built `JobDescription` (model + migration + tests) | ✅ Done | A place to store a pasted job posting's raw text, before anything is extracted from it. |
| 5 | 2026-09-25 | First git commit (`ac637fc`) | ✅ Done | Saved everything up to this point into git. Nothing since has been committed. |
| 6 | 2026-09-25 | Built `JobRequirement` (model + migration + tests) | ✅ Done | One line item pulled from a job posting, like "needs Python," optionally matched to a known skill. |
| 7 | 2026-09-25 | Built `ComparisonResult` + `ComparisonResultEvidence` (models + migration + tests) | ✅ Done | Stores the outcome of checking one job requirement against what the user can prove, plus which evidence backed that decision. Old results are never erased — new checks just add new rows. |
| 8 | 2026-09-25 | Built `verification_service` (`link_evidence`, `set_status`) + new exceptions + tests | ✅ Done | The one piece of code allowed to change a skill's trust level or attach proof to it. Blocks marking something "verified" with zero proof behind it. |
| 9 | 2026-09-25 | Built `skill_service` (`resolve_skill`, `create_skill`, `add_alias`, `list_skills`, `get_skill`, `normalize_text`) + tests | ✅ Done | Matches free text (like "Postgres") to the one official skill it means ("PostgreSQL"), without ever guessing or inventing a new skill on a lookup. |
| 10 | 2026-09-25 | Built `comparison_service` (`compare_job_description`) + tests | ✅ Done | Runs the actual check: for each job requirement, look up what the user can prove and record the result. |
| 11 | 2026-09-25 | Built the `/skills` API (create, list, resolve, add alias) + error-mapping + schemas + tests, live-checked against real Postgres | ✅ Done | The first working web endpoints — you can now create and look up skills over HTTP, not just in test code. |
| 12 | 2026-09-26 | Added `latest_results` + `skill_gaps` to `comparison_service`; updated `ARCHITECTURE.md` | ✅ Done | Added a way to ask "what's the newest result for this requirement?" and "what am I still missing for this job?" — worked out fresh each time, never stored as its own table, so it can't go stale. |
| 13 | 2026-09-26 | Built `requirement_service` (`extract_requirements`) + `app/ai/schemas.py` + `app/ai/client.py` interface + tests | ✅ Done | The rulebook for turning an AI's guesses about a job posting into real database rows — every guess is checked (must actually appear in the text, no duplicates, skill must be a real match) before it's trusted. No real AI plugged in yet, only a placeholder. |
| 14 | 2026-09-27 | Built the single-hardcoded-user bootstrap (`user_service`, `get_current_user`, `GET /me`) + tests, live-checked | ✅ Done | Since there's no login system yet, the app now automatically uses one fixed "you" account for everything, instead of needing a user id passed around. |
| 15 | 2026-09-28 | Built the `/job-descriptions` API (create, read, extract, compare, gaps) + a safe placeholder AI extractor + schemas + tests, live-checked | ✅ Done | The first complete, working path: paste a job posting → pull out its requirements → compare them to what you can prove → see what you're missing — all through real web requests. |
| 16 | 2026-09-28 | Started evidence + user-skill API endpoints (claim a skill, add evidence, link it, change status) | ⏸️ Paused | Inspected the code needed for this; found the `psycopg2` environment problem before writing anything. Paused at the user's request to fix the environment first. |
| 17 | 2026-09-28 | Created this progress-tracking file | ✅ Done | Set up `PROJECT_PROGRESS.md` as the always-up-to-date "what's done, what's next" log for this project. |
| 18 | 2026-09-29 | Diagnosed the `psycopg2` block precisely (Windows Event Viewer), then switched the database driver from `psycopg2` to `pg8000` | ✅ Done | Found the exact Windows security feature causing the block (Smart App Control), explained the two possible fixes and their trade-offs, and — at the user's choice — swapped to a driver with no compiled file for Windows to block. Nothing about the actual app code changed (models, services, routes are all untouched); only the connection string and the installed package changed. Confirmed working: driver check, full test suite (133 tests), migration check, and a real server request against the live database. |
| 19 | 2026-09-29 | Built the `/user-skills` and `/evidence` APIs (claim a skill, list claims, link evidence, change status, record evidence, list evidence) + schemas + tests, live-checked | ✅ Done | The last two pieces needed to actually *use* the verification system from outside test code: you can now claim a skill, back it up with real proof, connect the two, and ask the system to mark it verified — and it will refuse if there's no proof attached. Combined with last task's job-description flow, the whole point of this app now works end to end over the web. |

---

## Pending / Next Up

1. **Commit the accumulated uncommitted work** (see Housekeeping above) — worth doing in logical chunks rather than one giant commit. This now also includes the driver swap (`requirements.txt`, `.env.example`, docs) and the `/user-skills` + `/evidence` APIs.
2. Remaining backlog, roughly in likely order:
   - Real LLM-backed requirement extractor (replacing the safe placeholder)
   - `CVSkillPresence` model + endpoints (CV status is a separate axis from verification status, intentionally not built yet)
   - `LearningResource`, `LearningPlan`, `LearningProgress` (the learning system)
   - `DELETE` / update endpoints across the API (none exist yet anywhere)
   - Phase 2: the Next.js frontend (not started)

---

## Working Conventions (full detail lives in `HANDOFF.md`)

- **Learning-first process for every task:** explain the concept, why it's needed, where it fits architecturally, the data flow, and the key design decision — *before* writing code. Then implement, then verify. One task at a time; stop and wait for approval before starting the next.
- **Service layer rule:** plain functions that take a database `Session`, never commit (only flush) — the caller (a route, or a test) owns the transaction and decides when to commit.
- **API layer rule:** routes stay thin, call a service, and commit after success. Domain errors are never caught in a route — one shared handler maps them to HTTP status codes.
- **No `user_id` ever appears in a request.** The single hardcoded user is resolved automatically via a dependency.
- **Verification habit:** after building something, deliberately break the one guarantee that matters most (e.g. remove a safety check), confirm the *right* test fails, then restore the file byte-for-byte and confirm the suite is green again.
- **Live-check habit:** after any task that touches the API, start the real server against the real local Postgres database, exercise the new endpoints for real, then delete exactly what was created so the database is left exactly as it was found.
