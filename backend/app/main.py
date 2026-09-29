from fastapi import FastAPI

from app.api import evidence, health, job_descriptions, me, skills, user_skills
from app.api.errors import domain_error_handler
from app.core.exceptions import DomainError

app = FastAPI(title="Career AI API", version="0.1.0")

app.add_exception_handler(DomainError, domain_error_handler)

app.include_router(health.router)
app.include_router(skills.router)
app.include_router(me.router)
app.include_router(job_descriptions.router)
app.include_router(user_skills.router)
app.include_router(evidence.router)
