# The Career AI backend as a container (stage 94). Render builds this from render.yaml.
# Python is pinned so the server runs the same version the tests run locally.
# Build context: the REPO ROOT (so docs/RAG_GUIDE.md, used by the Practice page, can be
# included). The root .dockerignore lets in only backend/ and that one guide, never .env.
FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000

WORKDIR /app

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ .
# app/rag/practice.py looks for the guide three folders up from itself: /app/app/rag -> /docs
COPY docs/RAG_GUIDE.md /docs/RAG_GUIDE.md

EXPOSE 8000

# Bring the database schema up to date, then start the API. ${PORT} is set by the host.
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
