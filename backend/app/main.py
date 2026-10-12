import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import (
    assistant,
    cv,
    demo,
    evidence,
    export,
    health,
    import_backup,
    job_descriptions,
    learning_path,
    learning_progress,
    learning_resources,
    me,
    practice,
    profile,
    skills,
    user_skills,
)
from app.api.errors import domain_error_handler
from app import demo as demo_mode
from app.core.exceptions import DomainError
from app.rag.warmup import start_warm_up


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Load the assistant's local models in the background (app/rag/warmup.py), so the
    # first question doesn't wait for them. Does nothing when the AI is switched off.
    start_warm_up()
    # The public demo (stage 94): a fresh database gets the made-up career.
    if demo_mode.demo_mode():
        from database import SessionLocal

        demo_mode.seed_if_empty(SessionLocal)
    yield


app = FastAPI(title="Career AI API", version="0.1.0", lifespan=lifespan)

app.add_exception_handler(DomainError, domain_error_handler)

# Dev-only CORS allow-list: there is no auth yet, so this is intentionally narrow —
# specific local frontend origins, never "*" — and will need revisiting once real
# auth exists (e.g. to also allow credentials, or a deployed frontend origin).
app.add_middleware(
    CORSMiddleware,
    # Comma-separated; the deployed frontend's address is added via CORS_ORIGINS (stage 94).
    allow_origins=[o.strip() for o in (os.getenv("CORS_ORIGINS") or "http://localhost:3000,http://127.0.0.1:3000").split(",") if o.strip()],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(assistant.router)
app.include_router(skills.router)
app.include_router(me.router)
app.include_router(job_descriptions.router)
app.include_router(user_skills.router)
app.include_router(evidence.router)
app.include_router(learning_resources.router)
app.include_router(learning_progress.router)
app.include_router(learning_path.router)
app.include_router(cv.router)
app.include_router(profile.router)
app.include_router(export.router)
app.include_router(import_backup.router)
app.include_router(practice.router)
app.include_router(demo.router)
