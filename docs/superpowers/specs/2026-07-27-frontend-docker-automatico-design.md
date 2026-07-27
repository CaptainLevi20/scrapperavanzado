# Publicación automática del frontend como imagen Docker — Diseño

Fecha: 2026-07-27

## Contexto y objetivo

El despliegue de producción (ver `docs/superpowers/specs/2026-07-27-despliegue-produccion-red-interna-design.md`) ya deja las imágenes `api`, `worker` y `beat` publicándose solas en GHCR en cada push a `master`, gracias al job `docker` de `.github/workflows/ci.yml`. El frontend, en cambio, sigue siendo un paso manual: compilarlo (`VITE_API_BASE_URL=/api npm run build`), copiar `frontend/dist` a una carpeta de entrega, comprimirla, y entregársela a sistemas para que la copie al servidor — un proceso que hay que repetir cada vez que cambia el frontend.

Este diseño extiende el mismo patrón ya usado para `api`/`worker`/`beat` al frontend: se empaqueta como una cuarta imagen Docker, publicada automáticamente por CI, para que actualizar el frontend en producción se reduzca a los mismos dos comandos (`pull` + `up -d`) que ya usa sistemas para el backend — sin compilar ni copiar nada a mano, nunca más.

Explícitamente en alcance:
- Una imagen Docker nueva (`ghcr.io/captainlevi20/scrapperavanzado-frontend`) que compila el frontend y lo sirve como archivos estáticos.
- Publicación automática de esa imagen por CI, en cada push a `master`, igual que las otras tres.
- Actualizar `docker-compose.prod.yml` y el `Caddyfile` principal para usar esa imagen en vez de una carpeta copiada a mano.
- Actualizar la guía de sistemas y el `README` para reflejar que la carpeta de entrega se reduce a 3 archivos (ya no incluye `frontend/dist`).

Explícitamente fuera de alcance (decisión explícita del usuario en esta sesión):
- Que el servidor se actualice solo, sin que nadie ejecute ningún comando — se descartó por el riesgo de que un cambio llegue a producción sin autorización explícita ese día, tratándose de una herramienta que maneja documentos legales. Sistemas sigue ejecutando `pull` + `up -d` manualmente, cuando se le avise que hay versión nueva.
- Cualquier otro cambio a `api`/`worker`/`beat` — este diseño toca únicamente el frontend.

## Arquitectura

```
Push a master
      │
      ▼
CI (.github/workflows/ci.yml)
      │
      ├── job "docker"           → publica api / worker / beat  (sin cambios)
      └── job "docker-frontend"  → publica frontend              (nuevo)
                                        │
                                        ▼
                      ghcr.io/captainlevi20/scrapperavanzado-frontend

Servidor de producción, cuando sistemas corre pull + up -d:
┌─────────────────────────────────────────────┐
│  Caddy (443 / 9443, HTTPS)                   │
│    ├── /            → reverse_proxy frontend │
│    ├── /api/*        → reverse_proxy api     │
│    └── :9443         → reverse_proxy minio   │
│                                               │
│   Contenedores:                              │
│    - frontend (NUEVO — imagen GHCR)          │
│    - api / worker / beat (imágenes GHCR)     │
│    - postgres / redis / minio                │
└─────────────────────────────────────────────┘
```

`frontend` no publica ningún puerto hacia el servidor — solo Caddy le habla, igual que ya pasa con `api`/`postgres`/`redis`/`minio`.

## Componentes nuevos

1. **`frontend/Dockerfile`** — multi-stage, autocontenido dentro de la carpeta `frontend/` (no toca el `Dockerfile` de Python en la raíz, que sigue siendo responsabilidad exclusiva de `api`/`worker`/`beat`):
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
   `VITE_API_BASE_URL=/api` queda fijo dentro de la imagen — es el mismo valor que se usaba al compilar a mano, y no cambia entre despliegues (el frontend siempre llega a la API por la misma ruta relativa, sin importar el dominio real).

2. **`frontend/Caddyfile`** (nuevo, vive *dentro* de la imagen, no se confunde con el `Caddyfile` principal del despliegue) — sirve los archivos estáticos con el mismo comportamiento de "aplicación de una sola página" que ya tenía el `Caddyfile` principal:
   ```
   :80 {
   	root * /srv
   	try_files {path} /index.html
   	file_server
   }
   ```

## Componentes modificados

3. **`.github/workflows/ci.yml`** — nuevo job `docker-frontend`, paralelo al job `docker` existente, mismo patrón (`docker/build-push-action`, mismas condiciones `if: github.event_name == 'push' && github.ref == 'refs/heads/master'`, mismos permisos), pero con `context: ./frontend`, `file: ./frontend/Dockerfile`, `needs: [frontend]` (el job de test/lint/build del frontend que ya existe — no necesita esperar al job `test` de Python, que es independiente). Tags: `ghcr.io/captainlevi20/scrapperavanzado-frontend:latest` y `:${{ github.sha }}`, mismo esquema que las otras tres imágenes.

4. **`docker-compose.prod.yml`** — se agrega el servicio `frontend` (imagen GHCR, `restart: unless-stopped`, sin puertos publicados). Se quita del servicio `caddy` el volumen `./frontend/dist:/srv/frontend:ro`; se agrega `frontend` a su `depends_on`.

5. **`Caddyfile`** (el principal, en la raíz del repo) — el bloque `handle { root * /srv/frontend; try_files {path} /index.html; file_server }` se reemplaza por `handle { reverse_proxy frontend:80 }`. El resto del archivo (rutas `/api/*` y el bloque de `:9443` para MinIO) no cambia.

6. **`docs/guia-despliegue-sistemas.md`** — sección 2: ya no se copia la carpeta `frontend/dist`, solo los 3 archivos (`docker-compose.prod.yml`, `Caddyfile`, `.env.production.example`). Sección 7: se elimina la frase "si además te entregan una carpeta `frontend` nueva, reemplázala" — el `pull` ya trae todo.

7. **`README.md`** — la línea que documenta `VITE_API_BASE_URL=/api npm run build` como paso manual se reemplaza por una nota de que el frontend se compila automáticamente dentro de `frontend/Dockerfile`, publicado por CI igual que los otros tres servicios.

## Verificación

- Construir `frontend/Dockerfile` localmente y confirmar que la imagen arranca y sirve la aplicación correctamente (incluyendo que una ruta interna de la aplicación recargada directamente en el navegador no dé 404 — la prueba real de que `try_files` sigue funcionando).
- Levantar el stack completo de producción localmente con este contenedor nuevo en lugar de la carpeta copiada, y repetir la verificación de extremo a extremo ya usada en el despliegue original: la página carga, y **abrir/descargar un documento sigue funcionando** (regresión del fix crítico de la iteración anterior).
- Después de fusionar a `master`: confirmar que el job `docker-frontend` corre y publica la imagen en GHCR, y cambiar su visibilidad a **público** de inmediato (mismo paso que ya se hizo para `api`/`worker`/`beat`, para no repetir el mismo bloqueo de la vez pasada).
