# Publicación automática del frontend como imagen Docker — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Empaquetar el frontend como una cuarta imagen Docker publicada automáticamente por CI, para que actualizarlo en producción sea `docker compose pull && up -d`, sin compilar ni copiar nada a mano.

**Architecture:** `frontend/Dockerfile` (multi-stage: `node:24-alpine` compila, `caddy:2-alpine` sirve los archivos estáticos con su propio `frontend/Caddyfile`) se publica en GHCR desde un nuevo job de CI, paralelo al job `docker` existente. `docker-compose.prod.yml` y el `Caddyfile` principal pasan de leer una carpeta local a reenviar peticiones a ese nuevo contenedor.

**Tech Stack:** Docker multi-stage build, Node 24, Caddy 2, GitHub Actions (`docker/build-push-action`).

## Global Constraints

- No se automatiza la actualización del servidor en sí — sistemas sigue ejecutando `pull` + `up -d` manualmente, cuando se le avise. Decisión explícita del usuario: un cambio a producción no debe poder llegar sin que alguien lo autorice ese día.
- `VITE_API_BASE_URL=/api` es el único valor válido para compilar el frontend en esta imagen — es la ruta relativa que el `Caddyfile` principal ya reenvía a `api:8000`.
- El `Dockerfile` de Python en la raíz del repo no se toca — el frontend tiene su propio `frontend/Dockerfile`, autocontenido.
- El `frontend/Caddyfile` (nuevo, dentro de la imagen) es distinto del `Caddyfile` principal (en la raíz del repo, el que hace de proxy) — no confundir los dos al editar.

---

### Task 1: Crear `frontend/Dockerfile`, `frontend/Caddyfile` y `frontend/.dockerignore`

**Files:**
- Create: `frontend/Dockerfile`
- Create: `frontend/Caddyfile`
- Create: `frontend/.dockerignore`

**Interfaces:**
- Consumes: script `npm run build` de `frontend/package.json` (ya existente: `tsc -b && vite build`, genera `frontend/dist/`); `VITE_API_BASE_URL` leído en `frontend/src/api/client.ts:40`.
- Produces: una imagen Docker que sirve la aplicación en el puerto `80` interno — Task 3 la referencia como servicio `frontend` en `docker-compose.prod.yml`, con ese mismo puerto.

- [ ] **Step 1: Crear `frontend/.dockerignore`**

Contenido completo:

```
node_modules
dist
dist-ssr
coverage
```

- [ ] **Step 2: Crear `frontend/Caddyfile`**

Contenido completo — sirve los archivos estáticos con el mismo comportamiento de aplicación de una sola página que ya tenía el `Caddyfile` principal (rutas internas de React Router deben devolver `index.html`, no un 404):

```
:80 {
	root * /srv
	try_files {path} /index.html
	file_server
}
```

- [ ] **Step 3: Crear `frontend/Dockerfile`**

Contenido completo:

```dockerfile
FROM node:24-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN VITE_API_BASE_URL=/api npm run build

FROM caddy:2-alpine
COPY --from=build /app/dist /srv
COPY Caddyfile /etc/caddy/Caddyfile
```

- [ ] **Step 4: Construir la imagen localmente**

```bash
cd frontend
docker build -t iurisync-frontend-test .
cd ..
```

Expected: termina con `Successfully tagged iurisync-frontend-test` (o el mensaje equivalente de BuildKit), sin errores de `npm ci` ni de `vite build`.

- [ ] **Step 5: Levantarla sola y verificar que sirve la aplicación**

```bash
docker run --rm -d --name iurisync-frontend-test -p 18080:80 iurisync-frontend-test
sleep 1
curl -s -o /dev/null -w "index: %{http_code}\n" http://localhost:18080/
curl -s -o /dev/null -w "ruta interna (SPA fallback): %{http_code}\n" http://localhost:18080/documents
grep -c "/api" $(docker exec iurisync-frontend-test sh -c "ls /srv/assets/*.js") 2>/dev/null || \
  docker exec iurisync-frontend-test sh -c "grep -c '/api' /srv/assets/*.js"
docker stop iurisync-frontend-test
```

Expected: `index: 200`, `ruta interna (SPA fallback): 200` (si diera 404, `try_files` no está funcionando), y el `grep` de `/api` devuelve un número mayor a 0 (confirma que `VITE_API_BASE_URL=/api` sí quedó compilado en el bundle, igual que se verificó a mano en el despliegue original).

- [ ] **Step 6: Commit**

```bash
git add frontend/Dockerfile frontend/Caddyfile frontend/.dockerignore
git commit -m "Add frontend/Dockerfile: build and serve the frontend as its own image"
```

---

### Task 2: Publicar la imagen automáticamente desde CI

**Files:**
- Modify: `.github/workflows/ci.yml`

**Interfaces:**
- Consumes: `frontend/Dockerfile` (Task 1); el job `frontend` ya existente en este mismo archivo (líneas 51-70), que hace `npm ci` + lint + test + build del frontend — el nuevo job depende de que ese termine bien, no de que termine el job `test` (que es de Python, independiente).
- Produces: imagen `ghcr.io/captainlevi20/scrapperavanzado-frontend:latest` (y `:${{ github.sha }}`) — Task 3 la referencia por ese nombre exacto en `docker-compose.prod.yml`.

- [ ] **Step 1: Agregar el job `docker-frontend`**

Al final de `.github/workflows/ci.yml` (después del job `docker` existente, líneas 72-100), agregar:

```yaml
  docker-frontend:
    name: Build and push (frontend)
    runs-on: ubuntu-latest
    needs: [frontend]
    if: github.event_name == 'push' && github.ref == 'refs/heads/master'
    permissions:
      contents: read
      packages: write
    steps:
      - uses: actions/checkout@v4
      - uses: docker/setup-buildx-action@v3
      - uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      - uses: docker/build-push-action@v6
        with:
          context: ./frontend
          push: true
          tags: |
            ghcr.io/captainlevi20/scrapperavanzado-frontend:latest
            ghcr.io/captainlevi20/scrapperavanzado-frontend:${{ github.sha }}
          cache-from: type=gha,scope=docker-frontend
          cache-to: type=gha,scope=docker-frontend,mode=max
```

Este job es independiente del job `docker` existente (que sigue publicando `api`/`worker`/`beat` exactamente igual que antes, sin ningún cambio) — los dos corren en paralelo.

- [ ] **Step 2: Verificar que el YAML quedó válido**

```bash
python -c "
import yaml
from pathlib import Path
doc = yaml.safe_load(Path('.github/workflows/ci.yml').read_text(encoding='utf-8'))
assert 'docker-frontend' in doc['jobs'], 'falta el job docker-frontend'
assert doc['jobs']['docker-frontend']['needs'] == ['frontend']
assert doc['jobs']['docker']['strategy']['matrix']['target'] == ['api', 'worker', 'beat'], 'el job docker no debia cambiar'
print('OK: ci.yml valido, docker-frontend presente, job docker sin cambios')
"
```

Expected: `OK: ci.yml valido, docker-frontend presente, job docker sin cambios`

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "CI: publish the frontend image automatically on push to master"
```

---

### Task 3: Usar el contenedor del frontend en vez de la carpeta copiada

**Files:**
- Modify: `docker-compose.prod.yml`
- Modify: `Caddyfile`

**Interfaces:**
- Consumes: imagen `ghcr.io/captainlevi20/scrapperavanzado-frontend:latest` (Task 2), sirviendo en el puerto `80` interno (Task 1).
- Produces: servicio Docker Compose `frontend`, alcanzable como `frontend:80` desde otros contenedores de la misma red — Task 4 depende de que este servicio exista y esté sano antes de levantar `caddy`.

- [ ] **Step 1: Agregar el servicio `frontend` a `docker-compose.prod.yml`**

Agregar este bloque entre el servicio `beat` (termina en la línea 63 actual) y el servicio `caddy`:

```yaml
  frontend:
    image: ghcr.io/captainlevi20/scrapperavanzado-frontend:latest
    restart: unless-stopped
```

- [ ] **Step 2: Quitar la carpeta copiada y ajustar `depends_on` del servicio `caddy`**

En el servicio `caddy`, reemplazar:

```yaml
    volumes:
      - ./Caddyfile:/etc/caddy/Caddyfile:ro
      - ./frontend/dist:/srv/frontend:ro
      - caddy_data:/data
    depends_on:
      - api
```

por:

```yaml
    volumes:
      - ./Caddyfile:/etc/caddy/Caddyfile:ro
      - caddy_data:/data
    depends_on:
      - api
      - frontend
```

- [ ] **Step 3: Actualizar el `Caddyfile` principal para reenviar al nuevo contenedor**

En `Caddyfile` (raíz del repo), dentro del primer bloque `{$CADDY_DOMAIN} { ... }`, reemplazar:

```
	handle {
		root * /srv/frontend
		try_files {path} /index.html
		file_server
	}
```

por:

```
	handle {
		reverse_proxy frontend:80
	}
```

El resto del archivo (el `handle_path /api/*` y el bloque completo de `:9443` para MinIO) no cambia.

- [ ] **Step 4: Validar la sintaxis de ambos archivos**

```bash
cp .env.production.example .env.production
docker compose --env-file .env.production -f docker-compose.prod.yml config --quiet
echo "docker-compose exit code: $?"
rm .env.production

MSYS_NO_PATHCONV=1 docker run --rm -v "$(pwd)/Caddyfile:/etc/caddy/Caddyfile:ro" caddy:2-alpine caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
```

Expected: `docker-compose exit code: 0`, y la última línea del segundo comando es `Valid configuration`.

- [ ] **Step 5: Commit**

```bash
git add docker-compose.prod.yml Caddyfile
git commit -m "Serve the frontend from its own container instead of a copied folder"
```

---

### Task 4: Ensayo local completo con el contenedor del frontend

La imagen `scrapperavanzado-frontend` todavía no existe en GHCR (se publica recién cuando esto se fusione a `master` y corra CI) — este ensayo usa la imagen construida en la Task 1, re-etiquetada con el mismo nombre que `docker-compose.prod.yml` espera, para que Docker la use en vez de intentar descargarla.

**Files:**
- No crea archivos nuevos — usa los de las Tasks 1-3, con una copia local desechable de `.env.production` (nunca commiteada).

**Interfaces:**
- Consumes: todos los artefactos de las Tasks 1-3.
- Produces: confirmación de que el stack completo funciona con el contenedor nuevo, antes de fusionar.

- [ ] **Step 1: Confirmar que Docker Desktop está corriendo**

```bash
docker ps
```

Expected: una tabla (aunque esté vacía), no un error de conexión.

- [ ] **Step 2: Etiquetar la imagen local con el nombre que espera `docker-compose.prod.yml`**

```bash
docker tag iurisync-frontend-test ghcr.io/captainlevi20/scrapperavanzado-frontend:latest
```

Esto hace que `docker compose up` use esta imagen local en vez de intentar descargarla de GHCR (Docker Compose no vuelve a descargar una imagen que ya existe localmente con ese tag exacto).

- [ ] **Step 3: Crear un `.env.production` local de prueba (valores dummy, no reales)**

```bash
cp .env.production.example .env.production
sed -i 's/documentos.avancejuridico.com.co/localhost/g' .env.production
sed -i 's/CAMBIAR_ESTO_password_seguro/dummytestpassword123/g' .env.production
sed -i 's/CAMBIAR_ESTO_usuario_minio/dummyminiouser/g' .env.production
sed -i 's/CAMBIAR_ESTO_password_minio_largo_y_unico/dummyminiopassword123/g' .env.production
sed -i 's/CAMBIAR_ESTO_codigo_de_invitacion/dummy-invite-code/g' .env.production
```

- [ ] **Step 4: Levantar la infraestructura de base primero**

```bash
docker compose --env-file .env.production -f docker-compose.prod.yml up -d postgres redis minio
docker compose --env-file .env.production -f docker-compose.prod.yml ps
```

Expected: `postgres` en `healthy` (repetir `ps` si aún dice `starting`).

- [ ] **Step 5: Aplicar migraciones y poblar datos base**

```bash
docker compose --env-file .env.production -f docker-compose.prod.yml run --rm api alembic upgrade head
docker compose --env-file .env.production -f docker-compose.prod.yml run --rm api python -m core.seed
```

Expected: ambos comandos terminan sin errores.

- [ ] **Step 6: Levantar el resto de servicios, incluido el frontend nuevo**

```bash
docker compose --env-file .env.production -f docker-compose.prod.yml up -d frontend api worker beat caddy
docker compose --env-file .env.production -f docker-compose.prod.yml ps
```

Expected: los 8 servicios (`postgres`, `redis`, `minio`, `frontend`, `api`, `worker`, `beat`, `caddy`) en `running` o `healthy`.

- [ ] **Step 7: Verificar que la página carga a través de Caddy (ya no de una carpeta local)**

```bash
curl -k -s -o /dev/null -w "%{http_code}\n" https://localhost/
curl -k -s -o /dev/null -w "ruta interna: %{http_code}\n" https://localhost/documents
```

Expected: `200` para ambos — el segundo confirma que el `reverse_proxy` al contenedor `frontend` preserva el comportamiento de aplicación de una sola página.

- [ ] **Step 8: Repetir la prueba de descarga de documentos (regresión del fix anterior)**

```bash
docker compose --env-file .env.production -f docker-compose.prod.yml exec -T api python -c "
from core.storage import upload_file, presigned_url
from pathlib import Path
import tempfile, os

content = b'CONTENIDO DE PRUEBA IURISYNC - verificacion frontend docker'
with tempfile.NamedTemporaryFile(delete=False, suffix='.txt') as f:
    f.write(content)
    tmp_path = Path(f.name)

# upload_file() calls ensure_bucket() internally, no need to call it separately.
bucket, key = upload_file(tmp_path, 'test/verificacion-frontend-docker.txt', content_type='text/plain')
os.unlink(tmp_path)
url = presigned_url(bucket, key)
print(url)
"
```

Copia la URL impresa y pruébala desde tu propia terminal (fuera de cualquier contenedor, como lo haría un navegador):

```bash
curl -k -s "<URL_IMPRESA_ARRIBA>"
```

Expected: el comando anterior imprime una URL con el dominio y puerto configurados en `S3_PUBLIC_ENDPOINT_URL` del `.env.production` de prueba; el `curl` final devuelve exactamente `CONTENIDO DE PRUEBA IURISYNC - verificacion frontend docker`.

- [ ] **Step 9: Apagar y limpiar todo**

```bash
docker compose --env-file .env.production -f docker-compose.prod.yml down -v
rm .env.production
docker rmi ghcr.io/captainlevi20/scrapperavanzado-frontend:latest iurisync-frontend-test
git status --short
```

Expected: `git status --short` no muestra ningún archivo `.env.production`; el `docker rmi` confirma que se quitó la etiqueta de prueba (para no confundirla más adelante con la imagen real que publique CI).

- [ ] **Step 10: Commit**

No hay archivos nuevos que commitear en este task (fue un ensayo). Si algún paso reveló un problema en los archivos de las Tasks 1-3, corregirlo ahí, volver a construir la imagen (Task 1, Step 4) y repetir este ensayo antes de continuar.

---

### Task 5: Actualizar la guía de sistemas y el README

**Files:**
- Modify: `docs/guia-despliegue-sistemas.md`
- Modify: `README.md`

**Interfaces:**
- Consumes: el hecho de que, desde esta iteración, `frontend/dist` ya no se copia a mano — sistemas nunca vuelve a necesitar esa carpeta, en la instalación inicial ni en actualizaciones futuras.

- [ ] **Step 1: Actualizar la sección 2 de la guía (qué archivos copiar)**

En `docs/guia-despliegue-sistemas.md`, reemplazar el bloque completo de la sección `## 2. Copiar los archivos a la máquina` (desde el encabezado hasta el bloque de estructura de carpetas, antes de `## 3. Configurar las variables de producción`) por:

```markdown
## 2. Copiar los archivos a la máquina

El equipo de desarrollo te entrega estos tres archivos. Cópialos en una
carpeta de tu elección en el servidor, por ejemplo `C:\iurisync\` o
`/opt/iurisync/`, todos juntos en la misma carpeta:

- `docker-compose.prod.yml`
- `Caddyfile`
- `.env.production.example`
```

- [ ] **Step 2: Quitar la referencia a la carpeta `frontend` en la sección 7 (actualizar versión)**

En la sección `### Actualizar a una versión nueva`, quitar la frase:

```
Si además te entregan una carpeta `frontend` nueva, reemplaza la anterior
antes de ejecutar esos dos comandos.
```

(Ya no aplica — el `pull` trae el frontend actualizado igual que el resto.)

- [ ] **Step 3: Actualizar el README**

En `README.md`, en la sección `## Despliegue` (agregada en el despliegue anterior), reemplazar el párrafo que menciona `VITE_API_BASE_URL=/api npm run build` como paso manual por:

```markdown
El frontend se compila y publica automáticamente como una cuarta imagen
(`ghcr.io/captainlevi20/scrapperavanzado-frontend`) por el mismo CI, desde
`frontend/Dockerfile` — no requiere ningún paso manual de compilación ni
copia de archivos.
```

- [ ] **Step 4: Verificar que no quedaron referencias obsoletas**

```bash
grep -n "frontend/dist\|carpeta \`frontend\` nueva\|VITE_API_BASE_URL=/api npm run build" docs/guia-despliegue-sistemas.md README.md
```

Expected: sin resultados (todas las menciones al proceso manual anterior deben haber desaparecido de ambos archivos).

- [ ] **Step 5: Commit**

```bash
git add docs/guia-despliegue-sistemas.md README.md
git commit -m "Docs: frontend now ships as its own image, no manual copy step"
```

---

## Después de fusionar a `master` (no es parte de las tasks — depende de que CI corra de verdad)

1. Confirmar en GitHub que el job `docker-frontend` corrió y publicó `ghcr.io/captainlevi20/scrapperavanzado-frontend`.
2. Cambiar la visibilidad de ese paquete a **Public** de inmediato (Package settings → Danger Zone → Change visibility) — el mismo paso que ya se hizo para `api`/`worker`/`beat`, para no repetir el mismo bloqueo que se encontró la vez pasada.
3. Si en algún momento se genera la carpeta de entrega (`iurisync-despliegue/`) para sistemas otra vez, ya no debe incluir `frontend/dist` — solo los 3 archivos.
