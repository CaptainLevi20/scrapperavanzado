# Fuente ADRES (v2) — Implementation Plan

> **For agentic workers:** Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reescribir la familia `adres` (rota en silencio desde el cambio del
sitio de agosto de 2026) para traer Resoluciones, Circulares y Acuerdos
propios de la ADRES desde el payload RSC de Next.js, con títulos canónicos, y
migrar los documentos ya guardados sin bajarlos otra vez (opción A).

**Architecture:** `core/scrapers/families/adres.py` reescrito (misma clave y
clase `ScrapADRES`). Una petición por sección; se concatenan los
`self.__next_f.push([1,"…"])`, se lee cada `"documents":[…]` con
`json.JSONDecoder.raw_decode` y el `heading` que sigue al arreglo; sólo el
bloque "ADRES". Familia plana. Migración: `core/backfill_adres_v2.py`
(simula por defecto, `--aplicar` para cambiar).

**Spec:** `docs/superpowers/specs/2026-11-23-fuente-adres-design.md`
(aprobado por el administrador el 2026-11-26).

## Global Constraints

- `_SOURCE` = "Administradora de los Recursos del Sistema General de
  Seguridad Social en Salud" (igual al `name` del seed, que no cambia).
- Títulos `R_ADRES_{n}_{año}`, `C_ADRES_{n}_{año}`, `A_ADRES_{n}_{año}`, con
  el número **tal cual** del `name`; dedup por `int(número)` y año.
- Piso 2015; `f_public = f_providencia = meta.Fecha`; año del nombre distinto
  → día/mes de Fecha + año del nombre, `title_unverified=True` y aviso.
- `User-Agent` de navegador (el gateway rechaza el de `requests`).
- `checks_for_republication = False`, `scheduled_min_lookback_days = 45`,
  `alerta_margen_dias = 140` (pausa más larga desde 2022: 133 días).
- No se tocan `core/seed.py`, `tests/test_seed.py` ni `families/__init__.py`.
- Pruebas dirigidas: `pytest tests/families/test_adres.py tests/test_backfill_adres_v2.py`.

## Tasks

- [x] **1. Lector del RSC** — `bloques_doclist(html)`; prueba con dos bloques
  seguidos partidos entre dos `push` (caso 1 del diseño).
- [x] **2. Número y año** — `numero_y_anio(seccion, name)` con las tres regex
  del diseño más `(?!\d)` tras el número (sin él, `0000014_24_06_2024` se
  partía en número `000` y año `0014`); casos 2 y 4.
- [x] **3. `documentos_de_seccion`** — enlace (dominio ajeno fuera, ruta vieja
  `/normativa/Documents/` → `/api/media/file/` con aviso), fecha, año
  corregido, dedup por fecha más antigua, `detalle` sin espacios de ancho
  cero; casos 3, 5 y 6.
- [x] **4. `scrap()`** — filtro y piso, aviso "Error:" si la página no trae
  bloque "ADRES", sección que falla, `limit`, `stop_event`, User-Agent;
  casos 7-10.
- [x] **5. Backfill (opción A)** — `core/backfill_adres_v2.py`: empareja por
  nombre de archivo (sin codificar, minúsculas) y desempata por fecha; no
  pisa un `doc_id` existente ni junta dos guardados en uno; renombra el
  archivo con `storage_sync`. Aborta si el listado vino incompleto. Pruebas
  puras sin BD + pruebas con `db_session`.
- [x] **6. Comprobación en vivo (sin BD)** — `scrap()` desde 2015 y descarga de
  7 archivos verificados con `verificar_archivo`.
- [ ] **7. Corrida real local con el worker** y segunda corrida sin descargas
  nuevas (requiere el entorno levantado).
- [ ] **8. Ficha** en `docs/guia-despliegue-sistemas.md` (la integra quien
  junta las fuentes).
- [ ] **9. Producción:** desplegar, correr `python -m core.backfill_adres_v2`
  (simulación), revisar los pendientes, `--aplicar`, y después la corrida
  completa desde 2015.
