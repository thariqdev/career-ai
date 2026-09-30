# Career AI — How to work in this repo

This is a **learning project**. One chat does everything: plan, implement, verify, explain. There is no separate "working chat".

## Starting a session (save tokens)

1. Read `PROJECT_PROGRESS.md` first. It is the source of truth for what's done and what's next.
2. Open `HANDOFF.md` only for the specific technical detail a task needs. Don't read it end to end.
3. Don't re-derive context from old chat history. If the progress file doesn't answer something, check the code directly.

## The task loop

1. **User says "next"**: propose the next task. Include:
   - the new concept in plain words (what it is, and why Career AI needs it)
   - a short plan: scope, files touched, how it will be verified, and what is deliberately out of scope
2. **Wait for approval.** Don't write code until the user approves.
3. **Implement** only the approved scope. Preserve the existing architecture and conventions. No unrelated refactors.
4. **Verify**: run the backend tests (`pytest` in `backend/`) and, if the frontend was touched, `npm run build` in `frontend/`. Use `alembic check` after schema work. Leave the live database as you found it.
5. **Commit** the task as its own commit. **Do not push** unless the user asks.
6. **Update `PROJECT_PROGRESS.md`** with a new row in plain language. Update `HANDOFF.md` only where technical detail changed.
7. **Explain what was done, as if to an 8-year-old** who knows nothing about coding or AI:
   - short sentences, an everyday analogy, no jargon
   - what we built, and why it matters
   - this is required after **every** task, even small ones

Then stop and wait for the next "next".

## Project rules (details in PROJECT_RULES.md and ARCHITECTURE.md)

- PostgreSQL is the source of truth. The LLM is an assistant, not an authority.
- Never invent skills, experience, or proficiency. `VERIFIED`/`PARTIAL` require linked evidence.
- Backend logic stays deterministic: API → Service → SQLAlchemy → PostgreSQL.
- Every schema change goes through Alembic.
- Don't spend money on the Claude API without asking. The extractor falls back to a placeholder when `ANTHROPIC_API_KEY` is unset.
