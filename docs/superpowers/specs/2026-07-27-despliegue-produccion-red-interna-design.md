# Despliegue en producción, dentro de la red de la oficina — Diseño

Fecha: 2026-07-27

## Contexto y objetivo

IURISYNC hoy solo corre en máquinas de desarrollo. La empresa necesita tenerlo funcionando en producción **esta misma semana**, para que el equipo lo use desde la red interna de la oficina.

Restricciones confirmadas con el usuario:
- **Debe quedar accesible solo dentro de la red de la oficina**, no expuesto a internet — decisión de seguridad explícita, no negociable en este diseño.
- La empresa ya tiene dominios propios; se usará un **subdominio interno** (ej. `documentos.avancejuridico.com.co`) resuelto por el DNS interno de la oficina, no por un DNS público.
- El almacenamiento de documentos (`S3_ENDPOINT_URL` y variables relacionadas en `core/config.py` / `core/storage.py`) **no se conecta todavía** al servidor donde la empresa ya aloja ~200.000 documentos — ese servidor es de infraestructura desconocida (podría no ser S3-compatible) y su integración queda fuera de alcance de este diseño, como trabajo futuro. Por ahora se usa el contenedor MinIO que el proyecto ya trae.
- Quien ejecuta los pasos técnicos en el servidor es **la persona de sistemas de la empresa**, no un perfil de desarrollo. El entregable de instalación debe ser una guía paso a paso que esa persona pueda seguir sin conocer el código.
- Plazo: una semana.

Explícitamente en alcance:
- Un `docker-compose` de producción que levante, en **una sola máquina** dentro de la red de la oficina: la API, el worker de Celery, el beat (programador de tareas), Postgres, Redis, MinIO, y el frontend ya compilado.
- Un proxy inverso (Caddy) que sirva el frontend y reenvíe las llamadas a la API bajo el mismo subdominio, evitando problemas de CORS.
- HTTPS interno: certificado propio de la empresa si sistemas confirma que lo tienen, o un certificado autofirmado como alternativa (con la advertencia de navegador que eso implica la primera vez).
- Una guía de instalación en lenguaje simple para la persona de sistemas, con la lista de información/accesos que necesita preparar de su lado.
- Variables de entorno de producción documentadas (`.env` de ejemplo), incluyendo credenciales que sistemas deberá generar (no usar las de desarrollo/`minioadmin` en producción).

Explícitamente fuera de alcance:
- Conectar el almacenamiento al servidor real de documentos de la empresa — se hace en una iteración futura, cambiando únicamente variables de entorno de `S3_*` una vez se sepa qué protocolo expone ese servidor.
- Exponer la herramienta a internet, VPN, o acceso remoto fuera de la oficina.
- Alta disponibilidad, balanceo de carga, o separar servicios en más de una máquina — no se necesita para el tamaño de uso actual (equipo interno).
- Empaquetar el frontend en su propia imagen Docker publicada por CI — para esta primera versión se sirve como archivos estáticos servidos directamente por Caddy en la misma máquina, construidos manualmente o vía CI como artefacto (a definir en el plan de implementación).
- Backups automatizados de la base de datos — se deja anotado como mejora futura, no bloquea el despliegue de esta semana.

## Arquitectura

```
Red interna de la oficina
        │
        │  DNS interno: documentos.avancejuridico.com.co → IP de la máquina
        ▼
┌─────────────────────────────────────────────┐
│  Una sola máquina (física o VM), Docker      │
│                                               │
│   Caddy (puerto 443, HTTPS)                  │
│    ├── /            → archivos del frontend  │
│    └── /api/*        → contenedor API        │
│                                               │
│   Contenedores (docker-compose):             │
│    - api      (imagen ya publicada en GHCR)  │
│    - worker   (imagen ya publicada en GHCR)  │
│    - beat     (imagen ya publicada en GHCR)  │
│    - postgres                                │
│    - redis                                   │
│    - minio    (almacenamiento temporal)      │
└─────────────────────────────────────────────┘
```

Las imágenes `api`, `worker` y `beat` **ya existen** — el CI (`.github/workflows/ci.yml`) las publica automáticamente en GHCR en cada push a `master`. El despliegue de producción las descarga (`docker pull`), no las reconstruye en el servidor.

## Componentes nuevos a crear

1. **`docker-compose.prod.yml`** — variante de producción del `docker-compose.yml` actual. Diferencias clave frente al de desarrollo:
   - Usa las imágenes de GHCR (`ghcr.io/captainlevi20/scrapperavanzado-{api,worker,beat}:latest`) en vez de construir localmente.
   - Agrega el servicio Caddy.
   - No expone los puertos de Postgres/Redis/MinIO fuera de la red interna de Docker (solo Caddy expone 443 hacia la red de la oficina).
   - Usa variables de entorno desde un archivo `.env` real (no las de ejemplo con `minioadmin`).

2. **`Caddyfile`** — configuración del proxy inverso:
   - Sirve el build estático del frontend (`frontend/dist`) en `/`.
   - Reenvía `/api/*` al contenedor `api` (puerto 8000 interno).
   - Certificado: si sistemas confirma que tienen una CA interna, Caddy se configura para usarla; si no, Caddy genera un certificado autofirmado local.

3. **`.env.prod.example`** — plantilla de variables de entorno de producción, basada en `.env.example` pero con:
   - `CORS_ORIGINS` apuntando al subdominio interno real.
   - Recordatorio explícito de generar credenciales nuevas para `S3_ACCESS_KEY`/`S3_SECRET_KEY`/`REGISTRATION_CODE` (no usar los valores de ejemplo `minioadmin`/`changeme`).
   - `S3_ENDPOINT_URL` apuntando al contenedor MinIO interno (sin necesidad de `S3_PUBLIC_ENDPOINT_URL` porque todo, incluido el navegador del usuario, está dentro de la misma red interna).

4. **Guía de instalación para sistemas** (documento aparte, en lenguaje no técnico donde sea posible) con:
   - Requisitos de la máquina (mínimo 4 núcleos, 8 GB RAM, 100 GB disco).
   - Cómo instalar Docker si no lo tienen.
   - Los archivos que deben copiar al servidor (`docker-compose.prod.yml`, `Caddyfile`, `.env` ya completado).
   - Los comandos exactos a ejecutar (`docker compose up -d`, verificación de que los contenedores están corriendo).
   - Qué configurar de su lado: DNS interno del subdominio, certificado interno (si aplica), regla de firewall para el puerto 443 dentro de la red de oficina.

## Preguntas pendientes para sistemas (no bloquean el inicio del trabajo)

- ¿Tienen una autoridad certificadora (CA) interna para emitir certificados HTTPS internos, o se usa un certificado autofirmado?
- Confirmar las características exactas de la máquina que van a asignar (¿física o virtual? ¿ya tiene Docker?).
- Confirmar el nombre exacto del subdominio interno a usar.

## Verificación

- Tras el despliegue, la guía de instalación incluye una lista de comprobación simple: abrir el subdominio desde un navegador dentro de la oficina, iniciar sesión, y confirmar que se puede disparar una ejecución de scraping de prueba y ver un documento descargado.
- El CI existente (`ci.yml`) ya corre pruebas automáticas de backend y frontend antes de publicar cada imagen — no se duplica ese trabajo aquí, solo se documenta que las imágenes desplegadas ya pasaron esas pruebas.
