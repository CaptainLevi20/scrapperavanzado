# IURISYNC Backend

Backend SaaS de scraping de fuentes jurídicas/administrativas colombianas. Reutiliza los scrapers de `WebScrapping_Fuentes`, organizados por "familia técnica", con almacenamiento estructurado en PostgreSQL y archivos en un object storage S3-compatible.

## Setup local

1. `python -m venv .venv && .venv\Scripts\pip install -r requirements.txt`
2. `copy .env.example .env`
3. `docker compose up -d` (Postgres, Redis, MinIO)
4. `docker compose exec postgres psql -U iurisync -d iurisync -c "CREATE DATABASE iurisync_test;"`
5. `.venv\Scripts\alembic upgrade head`
6. `.venv\Scripts\python -m core.seed` (puebla `source_families`/`sources`)
7. `.venv\Scripts\python -m core.manage create-api-key --name "mi-equipo"` (guarda la key impresa)

## Correr los servicios

- API: `.venv\Scripts\uvicorn api.main:app --reload --port 8000`
- Worker: `.venv\Scripts\celery -A worker.celery_app worker --pool=solo --loglevel=info`
- Beat (scheduler diario): `.venv\Scripts\celery -A worker.celery_app beat --loglevel=info`

## Tests

`.venv\Scripts\pytest -v` (requiere `docker compose up -d` para las pruebas de integración con Postgres/MinIO).

## Alcance

Este repo porta dos familias de scraping como prueba del modelo (`constitucional`, `samai`). Las demás familias de `WebScrapping_Fuentes` (Corte Suprema, JEP, CNDJ, Rama Judicial, ADR, ADRES, ANE, ANH) se portan siguiendo el mismo patrón de `core/scrapers/families/` + `@register_family(...)` como trabajo de seguimiento.
