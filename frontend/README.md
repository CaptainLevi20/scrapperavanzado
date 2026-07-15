# IURISYNC Admin Dashboard

Panel interno para gestionar fuentes de scraping, disparar/monitorear runs y buscar documentos. Ver el diseño completo en `docs/superpowers/specs/2026-07-10-admin-dashboard-design.md`.

## Setup local

1. `cd frontend && npm install`
2. `copy .env.example .env` (ajusta `VITE_API_BASE_URL` si el backend no corre en `http://localhost:8000`)
3. Asegúrate de que el backend esté corriendo con `CORS_ORIGINS` incluyendo `http://localhost:5173` (valor por defecto en `.env.example` del backend)

## Correr en desarrollo

`npm run dev` — sirve en `http://localhost:5173`

## Tests

`npm test` (Vitest + React Testing Library + MSW, sin red real)

## Build de producción

`npm run build` — genera `dist/`, servible como estático detrás de cualquier hosting (Nginx, S3+CDN, etc.)

## Login

Regístrate en `/register` con un usuario, una contraseña (mínimo 8 caracteres) y el código de invitación configurado en `REGISTRATION_CODE` (backend), o inicia sesión en `/login` si ya tienes una cuenta.
