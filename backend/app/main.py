from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import (
    cv,
    evidence,
    health,
    job_descriptions,
    learning_progress,
    learning_resources,
    me,
    skills,
    user_skills,
)
from app.api.errors import domain_error_handler
from app.core.exceptions import DomainError

app = FastAPI(title="Career AI API", version="0.1.0")

app.add_exception_handler(DomainError, domain_error_handler)

# Dev-only CORS allow-list: there is no auth yet, so this is intentionally narrow —
# specific local frontend origins, never "*" — and will need revisiting once real
# auth exists (e.g. to also allow credentials, or a deployed frontend origin).
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(skills.router)
app.include_router(me.router)
app.include_router(job_descriptions.router)
app.include_router(user_skills.router)
app.include_router(evidence.router)
app.include_router(learning_resources.router)
app.include_router(learning_progress.router)
app.include_router(cv.router)
