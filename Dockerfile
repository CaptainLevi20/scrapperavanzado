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
# LibreOffice (headless, via soffice) converts RTF/DOC/DOCX to PDF for document
# previews and does the RTF fallback conversion for SAMAI downloads — both run
# only inside worker tasks (core/downloader.py), never in api or beat. Writer
# alone covers every format this project converts (no spreadsheets involved).
RUN apt-get update && apt-get install -y --no-install-recommends \
        libreoffice-writer \
    && rm -rf /var/lib/apt/lists/*
CMD ["celery", "-A", "worker.celery_app", "worker", "--loglevel=info"]

# ---- beat: Celery scheduler (single instance only) ----
FROM base AS beat
CMD ["celery", "-A", "worker.celery_app", "beat", "--loglevel=info"]
