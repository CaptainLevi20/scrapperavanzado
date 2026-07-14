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

## Despliegue

`Dockerfile` en la raíz define tres targets sobre la misma imagen base (Python 3.14 + `requirements.txt`):

- `api`: `uvicorn api.main:app` en el puerto 8000.
- `worker`: `celery -A worker.celery_app worker`.
- `beat`: `celery -A worker.celery_app beat` (correr una sola instancia).

```
docker build --target api -t iurisync-api .
docker build --target worker -t iurisync-worker .
docker build --target beat -t iurisync-beat .
```

Cada contenedor necesita las mismas variables de entorno que `core/config.py` (`DATABASE_URL`, `REDIS_URL`, `S3_ENDPOINT_URL`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`, `S3_BUCKET`, `S3_REGION`, `CORS_ORIGINS`) apuntando a Postgres/Redis/MinIO reales, no a `localhost`. Antes de levantar los contenedores hay que aplicar las migraciones una vez, por ejemplo:

```
docker run --rm --env-file .env.production iurisync-api alembic upgrade head
```

`docker-compose.yml` sigue siendo solo para infraestructura local (Postgres/Redis/MinIO); no define los servicios `api`/`worker`/`beat`.

## Alcance

Este repo porta las 10 familias de scraping de `WebScrapping_Fuentes` (`constitucional`, `samai`, `corte_suprema`, `jep`, `cndj`, `adr`, `adres`, `ane`, `anh`, `rama_judicial`), cada una siguiendo el patrón `core/scrapers/families/` + `@register_family(...)`.
