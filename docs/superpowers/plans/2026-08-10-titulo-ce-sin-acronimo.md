# Quitar el acrónimo del título (Consejo de Estado) — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** El título de los documentos de Consejo de Estado (familia `samai`) deja de mostrar el acrónimo de la clase, tanto para documentos nuevos como para los ya guardados.

**Architecture:** Tres cambios independientes: (1) la generación del título ya no anexa el acrónimo; (2) los patrones que reconocen "título de un caso" (para agrupar actuaciones) se vuelven tolerantes al título sin acrónimo, sin dejar de reconocer los títulos viejos durante la transición; (3) una corrida única quita el acrónimo de los títulos ya guardados. La tabla `_CLASE_ACRONIMOS` NO se borra: sigue alimentando la columna "Especialidad/Proceso".

**Tech Stack:** Python 3, SQLAlchemy, pytest. Frontend intacto.

## Global Constraints

- Solo afecta a Consejo de Estado (`corp_code == "1100103"`, `_CONSEJO_DE_ESTADO_CORP_CODE`). Los Tribunales Administrativos (`T_{CÓDIGO}_...`) NO se tocan.
- La columna Especialidad y el desarrollo del número de caso (`_complementar_titulo_con_numero`, `resolve_unverified_document`, `core/backfill_ce_titles.py`) NO cambian de comportamiento.
- Intérprete de Python del proyecto: `.venv/Scripts/python` (Windows).
- Correr pruebas con: `.venv/Scripts/python -m pytest`.
- Número de caso = grupo `(...)` que empieza con **dígito**. Acrónimo = grupo `(...)` que empieza con **letra mayúscula**. Esta distinción es la base de todos los regex de este plan.
- Spec de referencia: `docs/superpowers/specs/2026-08-10-titulo-ce-sin-acronimo-design.md`.

---

### Task 1: La generación del título ya no anexa el acrónimo

**Files:**
- Modify: `core/scrapers/families/samai.py:206-208` (`_normalizar_titulo`)
- Test: `tests/families/test_samai.py`

**Interfaces:**
- Consumes: nada de tareas previas.
- Produces: `_normalizar_titulo(radicado, clase, corp_code)` para Consejo de Estado devuelve **solo** `radicado` (str), sin sufijo `(ACRÓNIMO)`. La rama de Tribunales Administrativos no cambia. `_especialidad_legible(clase)` sigue devolviendo el nombre legible.

- [ ] **Step 1: Reescribir las pruebas de título de Consejo de Estado**

En `tests/families/test_samai.py`, **reemplazar** las pruebas que hoy esperan el acrónimo en el título (`test_normalizar_titulo_appends_acronym_for_known_clase`, `test_normalizar_titulo_strips_ley_prefix_before_matching`, `test_normalizar_titulo_strips_accion_de_prefix_before_matching`, `test_normalizar_titulo_strips_articulo_decision_reference`, `test_normalizar_titulo_is_accent_and_case_insensitive`, `test_normalizar_titulo_merges_clases_the_user_confirmed_are_the_same`) por estas dos, que fijan el nuevo comportamiento del título:

```python
def test_normalizar_titulo_returns_bare_radicado_for_consejo_de_estado():
    # El título de Consejo de Estado ya NO lleva el acrónimo de la clase —
    # sin importar la clase, es solo el radicado.
    assert _normalizar_titulo(
        "11001-03-28-000-2026-00329-00", "ACCIONES DE CUMPLIMIENTO", _CONSEJO_ESTADO
    ) == "11001-03-28-000-2026-00329-00"


def test_normalizar_titulo_ignores_the_clase_entirely_for_consejo_de_estado():
    # Dos clases distintas producen exactamente el mismo título: el radicado.
    con_clase_conocida = _normalizar_titulo("r1", "Reparación directa", _CONSEJO_ESTADO)
    con_clase_desconocida = _normalizar_titulo("r1", "Una clase nunca vista", _CONSEJO_ESTADO)
    assert con_clase_conocida == con_clase_desconocida == "r1"
```

La cobertura de la normalización de la clase (prefijo LEY, prefijo ACCIÓN DE, referencia ARTÍCULO/DECISIÓN, acentos, fusiones) se conserva a través de `_especialidad_legible` en el Step siguiente — por eso se puede borrar esa cobertura del título sin perderla.

- [ ] **Step 2: Añadir la cobertura de normalización de clase a `_especialidad_legible`**

En `tests/families/test_samai.py`, junto a las pruebas de `_especialidad_legible` existentes, añadir las que antes solo existían vía título:

```python
def test_especialidad_legible_strips_accion_de_prefix_before_matching():
    # "ACCION DE NULIDAD" es la misma clase que "Nulidad".
    assert _especialidad_legible("ACCION DE NULIDAD") == "Nulidad"


def test_especialidad_legible_strips_articulo_decision_reference():
    assert _especialidad_legible("NULIDAD RELATIVA ARTÍCULO 172 DECISION 486") == "Nulidad relativa"
    assert _especialidad_legible("NULIDAD ABSOLUTA ARTÍCULO 172 DECISION 486") == "Nulidad absoluta"


def test_especialidad_legible_is_accent_insensitive():
    assert _especialidad_legible("reparación directa") == "Reparación directa"
    assert _especialidad_legible("REPARACION DIRECTA") == "Reparación directa"


def test_especialidad_legible_merges_clases_the_user_confirmed_are_the_same():
    assert _especialidad_legible("CONFLICTOS DE COMPETENCIA JUDICIAL") == "Conflictos de competencia"
    assert _especialidad_legible("Protección de los derechos e intereses colectivos") == (
        "Protección de los derechos e intereses colectivos"
    )
    assert _especialidad_legible("Acción de grupo") == "Acción de grupo"
    assert _especialidad_legible("LEY 1437 REPARACION DE PERJUICIOS CAUSADOS A UN GRUPO") == (
        "Reparación de perjuicios causados a un grupo"
    )
```

- [ ] **Step 3: Actualizar las pruebas de `_parse_row` que esperan acrónimo en el título**

En `tests/families/test_samai.py`, en las pruebas alrededor de las líneas 511 y 526, cambiar la aserción del título para que ya no lleve acrónimo (la aserción de `especialidad`, donde exista, se mantiene igual):

```python
# test_parse_row_..._NRD (antes: doc.title == "25001233300020260001200(NRD)")
    assert doc.especialidad == "Nulidad y restablecimiento del derecho"
    assert doc.title == "25001233300020260001200"

# test_parse_row_uses_clase_column_to_build_the_polished_title
# (antes: doc.title == "25001233300020260001200(ACU)")
    assert doc.title == "25001233300020260001200"
```

- [ ] **Step 4: Correr las pruebas para verlas fallar**

Run: `.venv/Scripts/python -m pytest tests/families/test_samai.py -q`
Expected: FAIL — `_normalizar_titulo` para Consejo de Estado todavía devuelve `radicado(ACRÓNIMO)`.

- [ ] **Step 5: Implementar el cambio en `_normalizar_titulo`**

En `core/scrapers/families/samai.py`, reemplazar el bloque de Consejo de Estado dentro de `_normalizar_titulo` (líneas 206-208):

```python
    if corp_code == _CONSEJO_DE_ESTADO_CORP_CODE:
        return radicado
```

(Se elimina la línea `acronimo = _CLASE_ACRONIMOS.get(_normalizar_clase(clase))` y el `return f"{radicado}({acronimo})" if acronimo else radicado`. La rama de Tribunales Administrativos de abajo NO se toca.)

Actualizar también el comentario de las líneas 22-24 y 196-205 para que no digan que el título de Consejo de Estado lleva el acrónimo (ahora solo el radicado; la tabla se usa únicamente en `_especialidad_legible`).

- [ ] **Step 6: Correr las pruebas del scraper para verlas pasar**

Run: `.venv/Scripts/python -m pytest tests/families/test_samai.py -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add core/scrapers/families/samai.py tests/families/test_samai.py
git commit -m "feat(samai): el título de Consejo de Estado ya no lleva el acrónimo de la clase"
```

---

### Task 2: Reconocer el título de caso sin acrónimo (agrupación de expedientes)

**Files:**
- Modify: `core/utils.py:44-52` (`SAMAI_CASE_TITLE_PATTERN`, `SAMAI_CASE_TITLE_RAW_PATTERN`)
- Test: `tests/test_core_utils.py`
- Test: `tests/test_repository.py`

**Interfaces:**
- Consumes: el título sin acrónimo que produce `_normalizar_titulo` (Task 1).
- Produces: `is_samai_case_title(title)` devuelve `True` para `{radicado}` y `{radicado}({número})` (formato nuevo) y sigue devolviendo `True` para los formatos viejos con acrónimo. `list_documents(collapse_case_families=True)` agrupa las actuaciones de un mismo expediente de Consejo de Estado con títulos sin acrónimo.

- [ ] **Step 1: Invertir las dos pruebas que exigían acrónimo y añadir el caso "solo número"**

En `tests/test_core_utils.py`, **reemplazar** `test_is_samai_case_title_rejects_a_bare_radicado_without_acronym` (líneas ~201-204) y `test_is_samai_case_title_rejects_a_bare_radicado_complemented_with_only_a_number` (líneas ~218-224) por:

```python
def test_is_samai_case_title_matches_a_bare_radicado():
    # Nuevo formato: el título de Consejo de Estado ya no lleva acrónimo, así
    # que el radicado solo SÍ es un título de caso válido.
    assert is_samai_case_title("11001-03-24-000-2022-00373-00") is True


def test_is_samai_case_title_matches_a_bare_radicado_complemented_with_only_a_number():
    # Nuevo formato con número de caso, sin acrónimo.
    assert is_samai_case_title("11001-03-24-000-2026-99999-00(30146)") is True


def test_is_samai_case_title_matches_a_bare_raw_radicado_without_acronym():
    # Mismo caso para el formato crudo de 23 dígitos (documentos viejos).
    assert is_samai_case_title("25000234200020200000801") is True
```

Las pruebas existentes que verifican los formatos VIEJOS con acrónimo (`..._matches_a_real_formatted_title`, `..._matches_a_multi_letter_acronym`, `..._matches_a_complemented_title_with_acronimo`, `..._matches_a_complemented_title_with_numero_ano_format`, `..._matches_a_complemented_title_with_dotted_digits`, `..._matches_a_raw_undashed_title`) se dejan tal cual: deben seguir pasando durante la transición.

- [ ] **Step 2: Añadir una prueba de agrupación con título sin acrónimo**

En `tests/test_repository.py`, junto a `test_list_documents_collapse_keeps_only_the_most_recent_actuacion_for_samai`, añadir:

```python
def test_list_documents_collapse_works_for_samai_titles_without_acronimo(db_session):
    """Nuevo formato: los títulos de Consejo de Estado ya no llevan acrónimo,
    y aun así las actuaciones de un mismo expediente deben colapsar a la más
    reciente."""
    from datetime import date
    repository.create_source_family(db_session, key="samai", display_name="SAMAI")
    source = repository.create_source(db_session, family_key="samai", name="Consejo de Estado", family_params={})
    shared_title = "11001-03-28-000-2026-00271-00"
    repository.insert_document(
        db_session, doc_id="doc-old", source_id=source.id, title=shared_title,
        storage_bucket="iurisync-test", storage_key="a.pdf", f_public=date(2026, 7, 14),
    )
    repository.insert_document(
        db_session, doc_id="doc-new", source_id=source.id, title=shared_title,
        storage_bucket="iurisync-test", storage_key="b.pdf", f_public=date(2026, 7, 27),
    )

    items, total = repository.list_documents(db_session, family_key="samai", collapse_case_families=True)

    assert total == 1
    assert [d.doc_id for d in items] == ["doc-new"]
```

- [ ] **Step 3: Correr las pruebas para verlas fallar**

Run: `.venv/Scripts/python -m pytest tests/test_core_utils.py tests/test_repository.py -q`
Expected: FAIL — los patrones actuales exigen el acrónimo final, así que el radicado solo y el radicado+número no se reconocen como título de caso.

- [ ] **Step 4: Actualizar los patrones en `core/utils.py`**

En `core/utils.py`, reemplazar `SAMAI_CASE_TITLE_PATTERN` y `SAMAI_CASE_TITLE_RAW_PATTERN` (líneas 44-52):

```python
# Normalized format (with dashes): 25000-23-42-002-0202-00008-01
# El grupo del número (empieza con dígito) y el del acrónimo (empieza con
# letra mayúscula) son AMBOS opcionales: el formato nuevo no lleva acrónimo,
# pero los títulos viejos ({radicado}({ACRÓNIMO}) y
# {radicado}({número})({ACRÓNIMO})) se siguen reconociendo durante la
# transición, hasta que el backfill los homogenice.
SAMAI_CASE_TITLE_PATTERN = re.compile(
    r"^\d{5}-\d{2}-\d{2}-\d{3}-\d{4}-\d{5}-\d{2}"
    r"(?:\(\d[^)]{0,29}\))?(?:\([A-Z][A-Z0-9]*\))?$"
)

# Raw format (without dashes, for documents captured before scraper started formatting):
# 25000234200020200000801
SAMAI_CASE_TITLE_RAW_PATTERN = re.compile(
    r"^\d{23}(?:\(\d[^)]{0,29}\))?(?:\([A-Z][A-Z0-9]*\))?$"
)
```

Actualizar el comentario de arriba (líneas 24-42) para reflejar que el acrónimo ya no es obligatorio.

- [ ] **Step 5: Correr las pruebas para verlas pasar**

Run: `.venv/Scripts/python -m pytest tests/test_core_utils.py tests/test_repository.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add core/utils.py tests/test_core_utils.py tests/test_repository.py
git commit -m "feat(samai): reconocer el título de caso de Consejo de Estado sin acrónimo"
```

---

### Task 3: Limpieza única de los títulos ya guardados

**Files:**
- Create: `core/backfill_ce_titles_sin_acronimo.py`
- Test: `tests/test_backfill_ce_titles_sin_acronimo.py`

**Interfaces:**
- Consumes: `repository.update_document_title(db, document_id, title)` (existente, `core/db/repository.py:887`).
- Produces: `_quitar_acronimo(title: str) -> str | None` (devuelve el título sin el acrónimo final, o `None` si no hay nada que quitar) y `backfill(db) -> dict` con clave `"documents_updated"`.

- [ ] **Step 1: Escribir las pruebas unitarias de `_quitar_acronimo`**

Crear `tests/test_backfill_ce_titles_sin_acronimo.py`:

```python
from core.backfill_ce_titles_sin_acronimo import _quitar_acronimo


def test_quitar_acronimo_removes_a_bare_acronimo():
    assert _quitar_acronimo("25000-23-37-000-2021-00423-01(NRD)") == "25000-23-37-000-2021-00423-01"


def test_quitar_acronimo_keeps_the_case_number_and_removes_only_the_acronimo():
    assert _quitar_acronimo("25000-23-37-000-2021-00423-01(30146)(NRD)") == (
        "25000-23-37-000-2021-00423-01(30146)"
    )


def test_quitar_acronimo_handles_the_raw_undashed_format():
    assert _quitar_acronimo("25000234200020200000801(NRD)") == "25000234200020200000801"


def test_quitar_acronimo_returns_none_for_a_bare_radicado():
    # Nada que quitar → None (para que la corrida sea idempotente).
    assert _quitar_acronimo("11001-03-24-000-2026-99999-00") is None


def test_quitar_acronimo_returns_none_when_only_a_number_is_present():
    # El número de caso NO es el acrónimo y se conserva.
    assert _quitar_acronimo("11001-03-24-000-2026-99999-00(30146)") is None


def test_quitar_acronimo_does_not_touch_tribunal_administrativo_titles():
    assert _quitar_acronimo("T_ANTI_05001_23_33_000_2018_01895_00") is None
```

- [ ] **Step 2: Correr las pruebas unitarias para verlas fallar**

Run: `.venv/Scripts/python -m pytest tests/test_backfill_ce_titles_sin_acronimo.py -q`
Expected: FAIL con `ModuleNotFoundError: core.backfill_ce_titles_sin_acronimo`.

- [ ] **Step 3: Crear el módulo de backfill**

Crear `core/backfill_ce_titles_sin_acronimo.py`:

```python
"""Corrida única: quita el acrónimo de la clase del título de los documentos
de Consejo de Estado ya guardados — ver
docs/superpowers/specs/2026-08-10-titulo-ce-sin-acronimo-design.md.

Uso: .venv/Scripts/python -m core.backfill_ce_titles_sin_acronimo
Idempotente: un título que ya no tiene acrónimo se deja tal cual, así que se
puede correr más de una vez sin problema.
"""
import logging
import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.db import repository
from core.db.models import Document, Source
from core.db.session import SessionLocal

logger = logging.getLogger(__name__)

# El título de Consejo de Estado ya guardado puede venir en cuatro formas:
#   {radicado}, {radicado}({número}), {radicado}({ACRÓNIMO}) y
#   {radicado}({número})({ACRÓNIMO}).
# El acrónimo es el último grupo entre paréntesis que empieza con letra
# mayúscula; el número de caso empieza con dígito y se conserva. El grupo 1
# captura todo menos el acrónimo. Cubre el formato con guiones y el crudo de
# 23 dígitos (documentos viejos). Un título de Tribunal Administrativo
# (T_{CÓDIGO}_...) no matchea y se deja intacto.
_TITULO_CON_ACRONIMO_RE = re.compile(
    r"^(\d{5}-\d{2}-\d{2}-\d{3}-\d{4}-\d{5}-\d{2}(?:\(\d[^)]{0,29}\))?"
    r"|\d{23}(?:\(\d[^)]{0,29}\))?)"
    r"\([A-Z][A-Z0-9]*\)$"
)


def _quitar_acronimo(title: str) -> str | None:
    match = _TITULO_CON_ACRONIMO_RE.match(title or "")
    if not match:
        return None
    return match.group(1)


def backfill(db: Session) -> dict:
    documentos = db.scalars(
        select(Document).join(Source, Source.id == Document.source_id).where(Source.name == "Consejo de Estado")
    ).all()

    documents_updated = 0
    for documento in documentos:
        nuevo_titulo = _quitar_acronimo(documento.title)
        if nuevo_titulo is None:
            continue
        try:
            repository.update_document_title(db, documento.id, nuevo_titulo)
            documents_updated += 1
        except Exception as e:
            logger.warning("No se pudo actualizar el documento %s: %s", documento.id, e)
            db.rollback()
            continue

    return {"documents_updated": documents_updated}


def main():
    db = SessionLocal()
    try:
        result = backfill(db)
        print(f"Documentos actualizados (acrónimo quitado): {result['documents_updated']}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Correr las pruebas unitarias para verlas pasar**

Run: `.venv/Scripts/python -m pytest tests/test_backfill_ce_titles_sin_acronimo.py -q`
Expected: PASS.

- [ ] **Step 5: Escribir la prueba de integración con base de datos**

Añadir a `tests/test_backfill_ce_titles_sin_acronimo.py`:

```python
from datetime import date

from core.backfill_ce_titles_sin_acronimo import backfill
from core.db import repository


def test_backfill_strips_acronimo_from_stored_ce_titles(db_session):
    repository.create_source_family(db_session, key="samai", display_name="SAMAI")
    source = repository.create_source(db_session, family_key="samai", name="Consejo de Estado", family_params={})
    repository.insert_document(
        db_session, doc_id="con-acronimo", source_id=source.id,
        title="25000-23-37-000-2021-00423-01(NRD)",
        storage_bucket="iurisync-test", storage_key="a.pdf", f_public=date(2026, 7, 14),
    )
    repository.insert_document(
        db_session, doc_id="numero-y-acronimo", source_id=source.id,
        title="25000-23-37-000-2021-00423-01(30146)(NRD)",
        storage_bucket="iurisync-test", storage_key="b.pdf", f_public=date(2026, 7, 15),
    )
    repository.insert_document(
        db_session, doc_id="sin-acronimo", source_id=source.id,
        title="11001-03-24-000-2026-99999-00",
        storage_bucket="iurisync-test", storage_key="c.pdf", f_public=date(2026, 7, 16),
    )

    result = backfill(db_session)

    assert result["documents_updated"] == 2
    titulos = {
        d.doc_id: d.title
        for d in repository.list_documents(db_session, family_key="samai")[0]
    }
    assert titulos["con-acronimo"] == "25000-23-37-000-2021-00423-01"
    assert titulos["numero-y-acronimo"] == "25000-23-37-000-2021-00423-01(30146)"
    assert titulos["sin-acronimo"] == "11001-03-24-000-2026-99999-00"


def test_backfill_is_idempotent(db_session):
    repository.create_source_family(db_session, key="samai", display_name="SAMAI")
    source = repository.create_source(db_session, family_key="samai", name="Consejo de Estado", family_params={})
    repository.insert_document(
        db_session, doc_id="con-acronimo", source_id=source.id,
        title="25000-23-37-000-2021-00423-01(NRD)",
        storage_bucket="iurisync-test", storage_key="a.pdf", f_public=date(2026, 7, 14),
    )

    assert backfill(db_session)["documents_updated"] == 1
    assert backfill(db_session)["documents_updated"] == 0
```

Nota: `db_session` es el fixture de pytest ya usado en `tests/test_repository.py`; reutilizarlo aquí (está en `tests/conftest.py`).

- [ ] **Step 6: Correr toda la prueba del backfill para verla pasar**

Run: `.venv/Scripts/python -m pytest tests/test_backfill_ce_titles_sin_acronimo.py -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add core/backfill_ce_titles_sin_acronimo.py tests/test_backfill_ce_titles_sin_acronimo.py
git commit -m "feat(samai): backfill para quitar el acrónimo de títulos de Consejo de Estado ya guardados"
```

---

### Task 4: Verificación final de toda la suite

**Files:** ninguno (solo verificación).

- [ ] **Step 1: Correr toda la suite de pruebas**

Run: `.venv/Scripts/python -m pytest -q`
Expected: PASS. Prestar atención especial a `tests/test_api_documents.py` (conteo de documentos por caso para títulos crudos de samai) y a `tests/test_backfill_ce_titles.py` (el backfill del número de caso), que comparten el formato de título de Consejo de Estado.

- [ ] **Step 2: Si algo falla, arreglar y volver a correr**

Cualquier prueba que aún espere el acrónimo en un título de Consejo de Estado se actualiza al formato nuevo (radicado, o radicado+número). No cambiar el comportamiento del número de caso ni de los Tribunales Administrativos.

---

## Despliegue en producción (fuera del alcance del código, para referencia del usuario)

Ruta estándar del proyecto (Claude no tiene acceso directo a producción):

1. Fusionar el PR → CI construye las imágenes en GHCR.
2. En el servidor de la oficina: `docker compose pull` + `docker compose up -d`.
3. Correr **una sola vez** la limpieza dentro del contenedor:
   `python -m core.backfill_ce_titles_sin_acronimo`

Tras la limpieza, títulos viejos y nuevos quedan homogéneos.
