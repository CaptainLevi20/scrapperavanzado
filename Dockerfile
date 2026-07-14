# syntax=docker/dockerfile:1

FROM python:3.14-slim AS base

WORKDIR /srv

RUN --mount=type=cache,target=/root/.cache/pip \
    --mount=type=bind,source=requirements.txt,target=requirements.txt \
    pip install -r requirements.txt

COPY . .

# ---- api: FastAPI served by uvicorn ----
FROM base AS api
EXPOSE 8000
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]

# ---- worker: Celery task processor ----
FROM base AS worker
CMD ["celery", "-A", "worker.celery_app", "worker", "--loglevel=info"]

# ---- beat: Celery scheduler (single instance only) ----
FROM base AS beat
CMD ["celery", "-A", "worker.celery_app", "beat", "--loglevel=info"]
