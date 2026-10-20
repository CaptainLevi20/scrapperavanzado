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
- Frontend: `cd frontend && npm install && npm run dev` (apunta a la API en `http://localhost:8000` por defecto; se cambia con `VITE_API_BASE_URL`, ver `frontend/.env.example`)

El worker no recarga el código solo: tras cambiar un scraper hay que reiniciarlo.

## Tests

`.venv\Scripts\pytest -v` (requiere `docker compose up -d` para las pruebas de integración con Postgres/MinIO).

Frontend: `cd frontend && npm test`.

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
MinIO y un proxy Caddy que reenvía `/` al contenedor del frontend y `/api/*` al
backend. Caddy también publica MinIO en el puerto 9443 del mismo dominio, que
es a donde apuntan los enlaces firmados de descarga de documentos
(`S3_PUBLIC_ENDPOINT_URL`); sin eso el navegador recibiría URLs
`http://minio:9000`, resolubles solo dentro de Docker.

El frontend se compila y publica automáticamente como una cuarta imagen
(`ghcr.io/captainlevi20/scrapperavanzado-frontend`) por el mismo CI, desde
`frontend/Dockerfile` — no requiere ningún paso manual de compilación ni
copia de archivos.

Ver `docs/guia-despliegue-sistemas.md` para la guía de instalación
completa.

`docker-compose.yml` (sin `.prod`) sigue siendo solo para infraestructura
local de desarrollo (Postgres/Redis/MinIO).

## Alcance

El repo empezó portando las 10 familias de scraping de `WebScrapping_Fuentes` (`constitucional`, `samai`, `corte_suprema`, `jep`, `cndj`, `adr`, `adres`, `ane`, `anh`, `rama_judicial`). Las demás se desarrollaron directamente aquí, todas con el patrón `core/scrapers/families/` + `@register_family(...)`:

- **Ministerios:** `mincit`, `madr`, `minambiente`, `minvivienda`, `mineducacion`, `mininterior`, `mindeporte`, `minjusticia`, `minenergia`, `mintrabajo`, `minsalud`.
- **Superintendencias:** `superfinanciera`, `supersalud`, `ssf`, `snr`, `supersociedades`, `supersolidaria`, `sic`, `supertransporte`, `supervigilancia`.
- **Otras entidades:** `procuraduria`.

La lista vigente de familias es el import de `core/scrapers/families/__init__.py`; la de fuentes (con su nombre visible) es `core/seed.py`. Qué trae cada fuente está en la sección de fuentes de `docs/guia-despliegue-sistemas.md`.

## Agregar una fuente nueva

Ver `docs/guia-integracion-fuentes.md`: flujo completo (investigación del
sitio, diseño, scraper, pruebas, corrida real, documentación, PR y despliegue).
