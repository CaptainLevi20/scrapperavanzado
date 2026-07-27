# IURISYNC Backend

Backend SaaS de scraping de fuentes jurídicas/administrativas colombianas. Reutiliza los scrapers de `WebScrapping_Fuentes`, organizados por "familia técnica", con almacenamiento estructurado en PostgreSQL y archivos en un object storage S3-compatible.

## Setup local

1. `python -m venv .venv && .venv\Scripts\pip install -r requirements.txt`
2. `copy .env.example .env`
3. `docker compose up -d` (Postgres, Redis, MinIO)
4. `docker compose exec postgres psql -U iurisync -d iurisync -c "CREATE DATABASE iurisync_test;"`
5. `.venv\Scripts\alembic upgrade head`
6. `.venv\Scripts\python -m core.seed` (puebla `source_families`/`sources`)
7. Registra tu primer usuario desde el frontend (`/register`) con el código de invitación configurado en `REGISTRATION_CODE`, o directamente vía `POST /auth/register`.

## Correr los servicios

- API: `.venv\Scripts\uvicorn api.main:app --reload --port 8000`
- Worker: `.venv\Scripts\celery -A worker.celery_app worker --pool=solo --loglevel=info`
- Beat (scheduler diario): `.venv\Scripts\celery -A worker.celery_app beat --loglevel=info`

## Tests

`.venv\Scripts\pytest -v` (requiere `docker compose up -d` para las pruebas de integración con Postgres/MinIO).

## Despliegue

`Dockerfile` en la raíz define tres targets sobre la misma imagen base (Python 3.14 + `requirements.txt`):

- `api`: `uvicorn api.main:app` en el puerto 8000.
- `worker`: `celery -A worker.celery_app worker`.
- `beat`: `celery -A worker.celery_app beat` (correr una sola instancia).

El CI (`.github/workflows/ci.yml`) publica automáticamente las tres imágenes a
`ghcr.io/captainlevi20/scrapperavanzado-{api,worker,beat}` en cada push a
`master`.

Para producción, `docker-compose.prod.yml` levanta los tres servicios (usando
las imágenes de GHCR, sin reconstruir localmente) junto con Postgres, Redis,
MinIO y un proxy Caddy que sirve el frontend compilado y reenvía `/api/*` al
backend. Ver `docs/guia-despliegue-sistemas.md` para la guía de instalación
completa, y `docs/superpowers/specs/2026-07-27-despliegue-produccion-red-interna-design.md`
para el diseño detrás de esas decisiones.

`docker-compose.yml` (sin `.prod`) sigue siendo solo para infraestructura
local de desarrollo (Postgres/Redis/MinIO).

## Alcance

Este repo porta las 10 familias de scraping de `WebScrapping_Fuentes` (`constitucional`, `samai`, `corte_suprema`, `jep`, `cndj`, `adr`, `adres`, `ane`, `anh`, `rama_judicial`), cada una siguiendo el patrón `core/scrapers/families/` + `@register_family(...)`.
