import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import (
    assistant,
    auth,
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
from app.dependencies import get_current_user
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
    allow_credentials=True,  # the session cookie (stage 97), for the listed origins only
    allow_methods=["*"],
    allow_headers=["*"],
)

# Public: health check, the account routes themselves, and the demo (token-protected reset).
app.include_router(health.router)
app.include_router(auth.router)
app.include_router(demo.router)

# Everything else needs a logged-in user (stage 97). Routes that read `user` get the same
# one (FastAPI caches the dependency per request); routes that don't are protected too.
for private in (
    assistant, skills, me, job_descriptions, user_skills, evidence, learning_resources,
    learning_progress, learning_path, cv, profile, export, import_backup, practice,
):
    app.include_router(private.router, dependencies=[Depends(get_current_user)])
