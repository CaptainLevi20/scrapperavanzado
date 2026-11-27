# Fuente Cámara de Comercio de Cali — Implementation Plan

**Goal:** Añadir la familia `cc_cali` (laudos arbitrales del Centro de
Conciliación, Arbitraje y Amigable Composición de la Cámara de Comercio de
Cali), sin piso de año.

**Architecture:** Un módulo `core/scrapers/families/cc_cali.py` con
`ScrapCcCali(BaseScrapper)` registrada con `@register_family("cc_cali")`.
WordPress sin API: se lee el índice de laudos, se toman de sus enlaces las
páginas de año (`/laudos-AAAA/`, `/laudos/laudos-AAAA/`, `/laudos-1980-1996/`)
y de cada una los enlaces de `table.tabla3` dentro de `<article>`. Familia
plana: sin actuaciones, sin anexos, sin `family_params`, sin migración.

**Spec:** `docs/superpowers/specs/2026-11-23-fuente-cc_cali-design.md`
(aprobado por el administrador el 2026-11-26).

## Global Constraints

- `_SOURCE = "Cámara de Comercio de Cali"` (igual al `name` del seed). Sigla
  `CCC`, prefijo `LA`, tipo `Laudo arbitral`.
- Título: radicado tal cual (`LA_CCC_A-20201223-0803_2022`) > fecha completa
  (`LA_CCC_20240306_2024`) > respaldo con las partes (≤ 80 caracteres, en
  palabra entera) y `title_unverified=True`.
- Fecha: texto del enlace o nombre del archivo (lector propio: `dd-mm-aa(aa)`,
  `dd.mm.aa(aa)`, `dd mm aaaa`, `ddmmaa`, `ABR 13_ 2020`,
  `12-de-diciembre-de-2018`); si no, `<año de la página>-01-01`. Página
  `1980-1996` → `1996-01-01` + aviso + sin verificar. Fecha del nombre de otro
  año → manda el nombre + aviso.
- Sin piso; `scheduled_min_lookback_days = 20_000`; sin `alerta_margen_dias`;
  `checks_for_republication = True` (HEAD funciona).
- Títulos repetidos: sufijo `_2`, `_3`… por orden de ruta de subida, asignado
  sobre todo el sitio antes de filtrar por fecha. Enlaces repetidos: se omiten
  con aviso.
- TLS válido, sin `verify=False`. Pruebas sin internet (`responses`).

## Tasks

- [x] **1. Lector de fechas y títulos** — `_fecha`, `_titulo`, `_respaldo`;
  pruebas de cada forma de la tabla, números que no son fecha (`Acuavalle
  2010`, `0097.1.`, `001.3`, `40.1.`, radicados) y corte a 80.
- [x] **2. Índice y páginas de año** — `_paginas_de_anio`, `_filas`; HTML real
  del menú del índice y de la tabla (`table.tabla3` dentro de `<article>`).
- [x] **3. `scrap()`** — sitio simulado: fechas, sin piso, sufijos por ruta de
  subida independientes del rango, enlace repetido, página que falla, índice
  vacío o caído, `stop_event`, `limit`.
- [ ] **4. Registro** — import en `core/scrapers/families/__init__.py`, familia
  y fuente en `core/seed.py`, conteos en `tests/test_seed.py`.
- [ ] **5. Corrida real local** completa (desde 1980) y segunda corrida sin
  descargas nuevas. (Hecha la lectura en vivo del sitio el 2026-11-26: 273
  laudos, 245 sin verificar, 6 títulos con `_2`; 5 PDF bajados con el
  descargador real.)
- [ ] **6. Ficha** en `docs/guia-despliegue-sistemas.md`.

Pruebas dirigidas: `.venv/bin/pytest tests/families/test_cc_cali.py tests/test_seed.py`.
