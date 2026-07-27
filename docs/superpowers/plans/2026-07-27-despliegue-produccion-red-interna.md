# Despliegue en producción, red interna — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Producir todos los artefactos necesarios para desplegar IURISYNC en un solo servidor dentro de la red interna de la oficina, más una guía en lenguaje simple para que la persona de sistemas lo instale sin conocer el código.

**Architecture:** Un `docker-compose.prod.yml` que levanta, en una sola máquina, los contenedores `api`/`worker`/`beat` ya publicados en GHCR, más `postgres`/`redis`/`minio` de infraestructura, detrás de un proxy inverso Caddy que sirve el frontend estático y reenvía `/api/*` al backend bajo el mismo origen (sin CORS cross-origin). El certificado HTTPS usa el modo `tls internal` de Caddy (CA local, sin necesidad de internet) como opción por defecto.

**Tech Stack:** Docker / Docker Compose, Caddy 2, PostgreSQL 16, Redis 7, MinIO, imágenes ya publicadas en `ghcr.io/captainlevi20/scrapperavanzado-{api,worker,beat}`.

## Global Constraints

- La herramienta debe quedar accesible **solo dentro de la red de la oficina** — ningún puerto ni servicio se expone a internet.
- **Un solo servidor** (física o VM) aloja todos los componentes — no separar servicios en varias máquinas en esta iteración.
- Quien ejecuta los pasos en el servidor real es **la persona de sistemas**, sin conocimientos de programación — todo comando que le pidamos ejecutar debe estar documentado literal, sin dar por hecho que entiende Docker/YAML.
- Plazo: una semana. No añadir alcance no pedido (backups automatizados, alta disponibilidad, integración con el servidor de documentos de la empresa quedan fuera, según el spec).
- El almacenamiento de documentos usa el MinIO propio del proyecto por ahora — no se conecta al servidor externo de ~200.000 documentos en este plan.
- No se generan ni commitean secretos reales — solo plantillas (`*.example`) con valores de ejemplo, nunca `.env.production` real.

---

### Task 1: Blindar `.gitignore` contra archivos de secretos de producción

Hoy `.gitignore` solo ignora el archivo exacto `.env`, no `.env.production` ni ninguna otra variante — si alguien crea `.env.production` con secretos reales dentro del repo, un `git add` accidental lo subiría. Esto hay que arreglarlo antes de que este plan cree ninguna plantilla `.env.production.example`, para que quede protegido desde el primer commit.

**Files:**
- Modify: `.gitignore`

**Interfaces:**
- Produces: patrón de ignorado que cubre cualquier `.env.production`, `.env.local`, etc., preservando `.env.example` y `.env.production.example` como sí versionables.

- [ ] **Step 1: Editar `.gitignore`**

Reemplazar la línea `.env` (línea 5 actual) por este bloque:

```
.env
.env.*
!.env.example
!.env.production.example
```

- [ ] **Step 2: Verificar que un `.env.production` real quedaría ignorado**

```bash
echo "DATABASE_URL=test" > .env.production
git status --short
```

Expected: la salida de `git status --short` **no** debe listar `.env.production` (si aparece con `??`, el patrón está mal).

- [ ] **Step 3: Limpiar el archivo de prueba**

```bash
rm .env.production
```

- [ ] **Step 4: Commit**

```bash
git add .gitignore
git commit -m "Ignore .env.production and other local env files, keep .example templates tracked"
```

---

### Task 2: Crear la plantilla `.env.production.example`

**Files:**
- Create: `.env.production.example`

**Interfaces:**
- Consumes: nombres de variables definidos en `core/config.py::Settings` (`database_url`, `redis_url`, `s3_endpoint_url`, `s3_access_key`, `s3_secret_key`, `s3_bucket`, `s3_region`, `cors_origins`, `registration_code`), y `POSTGRES_USER`/`POSTGRES_PASSWORD`/`POSTGRES_DB` que consume el contenedor oficial de Postgres.
- Produces: nombre de archivo `.env.production.example` y el nombre de variable adicional `CADDY_DOMAIN`, que las Tasks 3 y 4 (`docker-compose.prod.yml` y `Caddyfile`) referencian.

- [ ] **Step 1: Crear el archivo**

Contenido completo de `.env.production.example`:

```
# Copia este archivo a .env.production y reemplaza cada valor marcado con
# CAMBIAR_ESTO antes de levantar los contenedores. NUNCA subas .env.production
# a git (ya está protegido en .gitignore, pero revisa antes de hacer commit).

# --- Dirección del sitio dentro de la red de la oficina ---
# El subdominio interno real que configure sistemas (DNS interno).
CADDY_DOMAIN=documentos.avancejuridico.com.co
CORS_ORIGINS=https://documentos.avancejuridico.com.co

# --- Base de datos ---
POSTGRES_USER=iurisync
POSTGRES_PASSWORD=CAMBIAR_ESTO_password_seguro
POSTGRES_DB=iurisync
# El usuario y password aquí deben coincidir exactamente con POSTGRES_USER/POSTGRES_PASSWORD de arriba.
DATABASE_URL=postgresql+psycopg://iurisync:CAMBIAR_ESTO_password_seguro@postgres:5432/iurisync

# --- Cola de tareas en segundo plano ---
REDIS_URL=redis://redis:6379/0

# --- Almacenamiento de documentos (MinIO propio del proyecto, temporal) ---
S3_ENDPOINT_URL=http://minio:9000
S3_ACCESS_KEY=CAMBIAR_ESTO_usuario_minio
S3_SECRET_KEY=CAMBIAR_ESTO_password_minio_largo_y_unico
S3_BUCKET=iurisync-documents
S3_REGION=us-east-1

# --- Registro de usuarios ---
# Código que cada persona debe ingresar para crear su cuenta la primera vez.
REGISTRATION_CODE=CAMBIAR_ESTO_codigo_de_invitacion
```

- [ ] **Step 2: Verificar que cubre todas las variables que la app necesita**

```bash
python -c "
import re
from pathlib import Path
required = ['DATABASE_URL','REDIS_URL','S3_ENDPOINT_URL','S3_ACCESS_KEY','S3_SECRET_KEY','S3_BUCKET','S3_REGION','CORS_ORIGINS','REGISTRATION_CODE','CADDY_DOMAIN','POSTGRES_USER','POSTGRES_PASSWORD','POSTGRES_DB']
content = Path('.env.production.example').read_text(encoding='utf-8')
missing = [k for k in required if not re.search(rf'^{k}=', content, re.MULTILINE)]
assert not missing, f'Missing required vars: {missing}'
print('OK: all required variables present')
"
```

Expected: `OK: all required variables present`

- [ ] **Step 3: Commit**

```bash
git add .env.production.example
git commit -m "Add production .env template"
```

---

### Task 3: Crear `docker-compose.prod.yml`

**Files:**
- Create: `docker-compose.prod.yml`

**Interfaces:**
- Consumes: nombres de variable de `.env.production.example` (Task 2); imágenes `ghcr.io/captainlevi20/scrapperavanzado-{api,worker,beat}:latest` ya publicadas por `.github/workflows/ci.yml`.
- Produces: nombres de servicio Docker Compose `postgres`, `redis`, `minio`, `api`, `worker`, `beat`, `caddy` — Task 4 (Caddyfile) referencia `api` y `caddy` monta `./frontend/dist` (producido por Task 5).

- [ ] **Step 1: Crear el archivo**

Contenido completo de `docker-compose.prod.yml`:

```yaml
services:
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      POSTGRES_DB: ${POSTGRES_DB}
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER}"]
      interval: 5s
      timeout: 5s
      retries: 10
    restart: unless-stopped

  redis:
    image: redis:7-alpine
    restart: unless-stopped

  minio:
    image: minio/minio:latest
    command: server /data --console-address ":9001"
    environment:
      MINIO_ROOT_USER: ${S3_ACCESS_KEY}
      MINIO_ROOT_PASSWORD: ${S3_SECRET_KEY}
    volumes:
      - minio_data:/data
    restart: unless-stopped

  api:
    image: ghcr.io/captainlevi20/scrapperavanzado-api:latest
    env_file: .env.production
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_started
      minio:
        condition: service_started
    restart: unless-stopped

  worker:
    image: ghcr.io/captainlevi20/scrapperavanzado-worker:latest
    env_file: .env.production
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_started
      minio:
        condition: service_started
    restart: unless-stopped

  beat:
    image: ghcr.io/captainlevi20/scrapperavanzado-beat:latest
    env_file: .env.production
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_started
    restart: unless-stopped

  caddy:
    image: caddy:2-alpine
    env_file: .env.production
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./Caddyfile:/etc/caddy/Caddyfile:ro
      - ./frontend/dist:/srv/frontend:ro
      - caddy_data:/data
    depends_on:
      - api
    restart: unless-stopped

volumes:
  postgres_data:
  minio_data:
  caddy_data:
```

Nota sobre `postgres`/`redis`/`minio`: deliberadamente **no** tienen `ports:` mapeados al host — solo son alcanzables entre contenedores, dentro de la red interna de Docker. Únicamente `caddy` expone puertos (80/443) hacia la red de la oficina.

- [ ] **Step 2: Validar la sintaxis (no requiere el daemon de Docker corriendo)**

```bash
cp .env.production.example .env.production
docker compose --env-file .env.production -f docker-compose.prod.yml config --quiet
echo "exit code: $?"
rm .env.production
```

Expected: `exit code: 0` (si hay un error de sintaxis o una variable sin definir, `config` lo reporta y el exit code es distinto de 0).

- [ ] **Step 3: Commit**

```bash
git add docker-compose.prod.yml
git commit -m "Add production docker-compose file"
```

---

### Task 4: Crear el `Caddyfile`

**Files:**
- Create: `Caddyfile`

**Interfaces:**
- Consumes: variable `CADDY_DOMAIN` (Task 2), servicio `api` en el puerto 8000 (Task 3), carpeta `/srv/frontend` montada desde `./frontend/dist` (Task 5).
- Produces: rutas `/` (frontend) y `/api/*` (proxy al backend, prefijo `/api` recortado antes de reenviar) bajo el mismo origen.

- [ ] **Step 1: Crear el archivo**

Contenido completo de `Caddyfile`:

```
{$CADDY_DOMAIN} {
	tls internal

	handle_path /api/* {
		reverse_proxy api:8000
	}

	handle {
		root * /srv/frontend
		try_files {path} /index.html
		file_server
	}
}
```

`tls internal` le dice a Caddy que genere y use su propio certificado local (sin necesidad de internet ni de un dominio público) — es el "candado casero" que se planteó. La primera vez que alguien entre desde el navegador va a ver una advertencia de "sitio no verificado" que hay que aceptar una sola vez. Si sistemas confirma que tienen una autoridad certificadora interna propia, este bloque se reemplaza más adelante por su configuración — no bloquea el despliegue de esta semana.

- [ ] **Step 2: Validar la sintaxis (requiere Docker; si el daemon no está corriendo, iniciar Docker Desktop primero)**

```bash
docker run --rm -v "$(pwd)/Caddyfile:/etc/caddy/Caddyfile:ro" caddy:2-alpine caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
```

Expected: la última línea del output es `Valid configuration`.

- [ ] **Step 3: Commit**

```bash
git add Caddyfile
git commit -m "Add Caddyfile: SPA + /api reverse proxy, internal TLS"
```

---

### Task 5: Compilar el frontend para producción

El servidor no necesita tener Node.js instalado — el `frontend/dist` ya compilado se copia junto con los demás archivos. Este task lo genera y lo deja listo.

**Files:**
- Modify (generado, no versionado): `frontend/dist/`

**Interfaces:**
- Consumes: `VITE_API_BASE_URL` (leído por `frontend/src/api/client.ts:40`) — debe ser `/api` para que las llamadas del navegador usen la misma ruta relativa que el `Caddyfile` (Task 4) reenvía al backend.
- Produces: carpeta `frontend/dist/` con `index.html` y assets estáticos, que Task 3 monta en el contenedor `caddy` y Task 6 sirve en la prueba local.

- [ ] **Step 1: Compilar con la URL de API relativa**

```bash
cd frontend
VITE_API_BASE_URL=/api npm run build
cd ..
```

- [ ] **Step 2: Verificar que el build se generó correctamente**

```bash
test -f frontend/dist/index.html && echo "OK: index.html existe"
grep -c "assets/" frontend/dist/index.html
```

Expected: `OK: index.html existe`, y el segundo comando devuelve un número mayor a 0 (confirma que el HTML referencia los assets compilados).

No se hace commit de este paso — `frontend/dist/` no se versiona en git (es un artefacto de build); se regenera cada vez que se despliegue una nueva versión, y se copia al servidor junto con los demás archivos en la Task 7 (guía de instalación).

---

### Task 6: Ensayo local completo del stack de producción

Antes de mandarle instrucciones a sistemas, se levanta todo el stack de producción localmente (con Docker Desktop) para confirmar que arranca correctamente de punta a punta.

**Files:**
- No crea archivos nuevos — usa los de las Tasks 2-5, con una copia local desechable de `.env.production` (nunca commiteada).

**Interfaces:**
- Consumes: todos los artefactos de las Tasks 2-5.
- Produces: confirmación de que el stack funciona antes de escribir la guía de instalación (Task 7).

- [ ] **Step 1: Confirmar que Docker Desktop está corriendo**

```bash
docker ps
```

Expected: una tabla (aunque esté vacía), no un error de conexión. Si da error, iniciar Docker Desktop y esperar a que termine de arrancar antes de continuar.

- [ ] **Step 2: Crear un `.env.production` local de prueba (valores dummy, no reales)**

```bash
cp .env.production.example .env.production
sed -i 's/documentos.avancejuridico.com.co/localhost/g' .env.production
sed -i 's/CAMBIAR_ESTO_password_seguro/dummytestpassword123/g' .env.production
sed -i 's/CAMBIAR_ESTO_usuario_minio/dummyminiouser/g' .env.production
sed -i 's/CAMBIAR_ESTO_password_minio_largo_y_unico/dummyminiopassword123/g' .env.production
sed -i 's/CAMBIAR_ESTO_codigo_de_invitacion/dummy-invite-code/g' .env.production
```

- [ ] **Step 3: Levantar la infraestructura de base primero**

```bash
docker compose --env-file .env.production -f docker-compose.prod.yml up -d postgres redis minio
docker compose --env-file .env.production -f docker-compose.prod.yml ps
```

Expected: `postgres` muestra `healthy` (puede tardar unos segundos; repetir `ps` si aún dice `starting`).

- [ ] **Step 4: Aplicar las migraciones**

```bash
docker compose --env-file .env.production -f docker-compose.prod.yml run --rm api alembic upgrade head
```

Expected: termina sin errores, última línea menciona la revisión más reciente aplicada.

- [ ] **Step 5: Poblar los datos base (fuentes de scraping)**

```bash
docker compose --env-file .env.production -f docker-compose.prod.yml run --rm api python -m core.seed
```

Expected: termina sin errores.

- [ ] **Step 6: Levantar el resto de servicios**

```bash
docker compose --env-file .env.production -f docker-compose.prod.yml up -d api worker beat caddy
docker compose --env-file .env.production -f docker-compose.prod.yml ps
```

Expected: los 7 servicios (`postgres`, `redis`, `minio`, `api`, `worker`, `beat`, `caddy`) en estado `running` o `healthy`.

- [ ] **Step 7: Verificar que el frontend responde**

```bash
curl -k -s -o /dev/null -w "%{http_code}\n" https://localhost/
```

Expected: `200`

- [ ] **Step 8: Verificar que la API responde a través del proxy**

```bash
curl -k -s https://localhost/api/health
```

Expected: `{"status":"ok"}`

- [ ] **Step 9: Apagar y limpiar todo lo del ensayo**

```bash
docker compose --env-file .env.production -f docker-compose.prod.yml down -v
rm .env.production
```

Expected: `.env.production` ya no existe (`git status --short` no debe mostrar nada relacionado a archivos `.env`).

- [ ] **Step 10: Commit**

No hay archivos nuevos que commitear en este task (fue un ensayo, no generó artefactos versionables). Si algún paso anterior reveló un error en `docker-compose.prod.yml` o el `Caddyfile`, corregir esos archivos y volver a correr este task antes de continuar — con el fix ya corregido, commitear ese archivo puntual con un mensaje como `Fix production compose/Caddyfile issue found during local rehearsal`.

---

### Task 7: Guía de instalación para sistemas

**Files:**
- Create: `docs/guia-despliegue-sistemas.md`

**Interfaces:**
- Consumes: comandos verificados en la Task 6, requisitos de máquina y preguntas pendientes definidos en el spec (`docs/superpowers/specs/2026-07-27-despliegue-produccion-red-interna-design.md`).

- [ ] **Step 1: Crear el documento**

Contenido completo de `docs/guia-despliegue-sistemas.md`:

```markdown
# Guía de instalación de IURISYNC — para el equipo de sistemas

Esta guía no requiere conocimientos de programación. Sigue los pasos en orden.
Si algo no funciona como se describe aquí, detente en ese paso y avisa al
equipo de desarrollo antes de continuar.

## 1. Antes de empezar: qué necesitamos de tu parte

- [ ] Una máquina (física o virtual) **dentro de la red de la oficina**, con
      al menos: 4 núcleos de procesador, 8 GB de memoria RAM, 100 GB de disco.
- [ ] Docker instalado en esa máquina. Si no lo tienen, instrucciones oficiales
      aquí: https://docs.docker.com/engine/install/
- [ ] El nombre exacto del subdominio interno que van a usar (ejemplo:
      `documentos.avancejuridico.com.co`), y que su DNS interno ya apunte
      ese nombre a la IP de esta máquina.
- [ ] Confirmar: ¿tienen una autoridad certificadora (CA) interna propia para
      emitir certificados HTTPS? Si no están seguros, la respuesta por
      defecto es "no" y esta guía funciona igual (ver sección 5).
- [ ] Una regla de firewall que permita tráfico normal de navegación
      (puertos 80 y 443) desde la red de la oficina hacia esta máquina.

## 2. Copiar los archivos a la máquina

El equipo de desarrollo te entrega una carpeta comprimida con estos archivos.
Descomprímela en una carpeta de tu elección en el servidor, por ejemplo
`C:\iurisync\` o `/opt/iurisync/`:

- `docker-compose.prod.yml`
- `Caddyfile`
- `.env.production.example`
- `frontend/dist/` (carpeta ya compilada, no requiere Node.js)

## 3. Configurar las variables de producción

Copia `.env.production.example` a un archivo nuevo llamado `.env.production`,
en la misma carpeta. Ábrelo con un editor de texto simple (Bloc de notas
sirve) y reemplaza cada valor que dice `CAMBIAR_ESTO` por uno propio:

- `CADDY_DOMAIN` y `CORS_ORIGINS`: el subdominio interno real (el mismo en
  ambas líneas).
- `POSTGRES_PASSWORD` y la contraseña dentro de `DATABASE_URL`: deben ser
  **exactamente la misma contraseña**, elegida por ustedes, en ambos lugares.
- `S3_ACCESS_KEY` / `S3_SECRET_KEY`: un usuario y contraseña nuevos, elegidos
  por ustedes, para el almacenamiento de documentos.
- `REGISTRATION_CODE`: el código que cada persona del equipo va a usar para
  crear su cuenta la primera vez. Compártanlo solo con quienes deban tener
  acceso.

Guarda el archivo. **No lo compartas por correo ni lo subas a ningún sitio
público** — contiene contraseñas.

## 4. Levantar la herramienta

Abre una terminal (PowerShell en Windows, o una terminal normal en Linux),
ubícate en la carpeta donde copiaste los archivos, y ejecuta estos comandos
uno por uno, en este orden exacto:

```
docker compose --env-file .env.production -f docker-compose.prod.yml up -d postgres redis minio
```

Espera unos 15 segundos, luego:

```
docker compose --env-file .env.production -f docker-compose.prod.yml run --rm api alembic upgrade head
```

```
docker compose --env-file .env.production -f docker-compose.prod.yml run --rm api python -m core.seed
```

```
docker compose --env-file .env.production -f docker-compose.prod.yml up -d api worker beat caddy
```

Para confirmar que todo quedó corriendo:

```
docker compose --env-file .env.production -f docker-compose.prod.yml ps
```

Deberías ver 7 servicios, todos en estado `running` o `healthy`. Si alguno
dice `restarting` repetidamente, avisa al equipo de desarrollo con el
resultado de este comando (reemplaza `api` por el nombre del servicio que
falla):

```
docker compose --env-file .env.production -f docker-compose.prod.yml logs api
```

## 5. Sobre el candado de seguridad (HTTPS)

Por defecto, esta instalación genera su propio certificado de seguridad
("candado casero"). La primera vez que alguien entre desde el navegador al
subdominio, va a ver una advertencia tipo "conexión no privada" o "sitio no
verificado" — es normal, hay que darle click en "Avanzado" y luego
"Continuar de todos modos" (el texto exacto varía según el navegador). Una
vez aceptado, el navegador no debería volver a preguntar en esa misma
máquina.

Si su empresa sí tiene una autoridad certificadora interna propia, avisen al
equipo de desarrollo — se puede reemplazar este certificado casero por uno
oficial de la empresa, sin necesidad de rehacer el resto de la instalación.

## 6. Verificación final

Desde un computador conectado a la red de la oficina, abre un navegador y
entra a `https://` seguido del subdominio configurado (ejemplo:
`https://documentos.avancejuridico.com.co`). Deberías ver la pantalla de
inicio de sesión de IURISYNC. Usa el `REGISTRATION_CODE` que configuraste en
el paso 3 para crear la primera cuenta desde la pantalla de registro.

Si la página no carga, revisa en este orden: (1) que el DNS interno
realmente apunte al servidor (`ping <subdominio>` desde otro computador de la
oficina), (2) que el firewall deje pasar el puerto 443, (3) el resultado del
comando `docker compose ... ps` del paso 4.
```

- [ ] **Step 2: Verificar que todos los comandos de la guía coinciden con los usados en el ensayo local**

```bash
grep -c "docker compose --env-file .env.production -f docker-compose.prod.yml" docs/guia-despliegue-sistemas.md
```

Expected: un número mayor o igual a 5 (uno por cada comando de la sección 4).

- [ ] **Step 3: Commit**

```bash
git add docs/guia-despliegue-sistemas.md
git commit -m "Add plain-language deployment guide for the sistemas team"
```

---

### Task 8: Actualizar el README con la nueva ruta de despliegue

La sección "Despliegue" del `README.md` actual (líneas 25-45) dice explícitamente que `docker-compose.yml` no define `api`/`worker`/`beat` y da instrucciones de `docker build`/`docker run` sueltas — eso ya no refleja la realidad una vez existe `docker-compose.prod.yml`. Se actualiza para que apunte a los archivos nuevos y no quede contradictorio.

**Files:**
- Modify: `README.md:25-45`

**Interfaces:**
- Consumes: `docker-compose.prod.yml` (Task 3), `Caddyfile` (Task 4), `docs/guia-despliegue-sistemas.md` (Task 7).

- [ ] **Step 1: Reemplazar la sección "Despliegue"**

Reemplazar el bloque completo entre `## Despliegue` (línea 25) y el final de esa sección (línea 45, antes de `## Alcance`) por:

```markdown
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
```

- [ ] **Step 2: Verificar que no quedaron referencias contradictorias**

```bash
grep -n "no define los servicios" README.md
```

Expected: sin resultados (esa frase, ya obsoleta, debe haber desaparecido).

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "Update README deployment section for docker-compose.prod.yml"
```
