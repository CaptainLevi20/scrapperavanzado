# Complementar título de Consejo de Estado con número de la primera página — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cuando un documento de Consejo de Estado trae en la primera página de su PDF un número entre paréntesis junto al radicado (ej. `25000-23-37-000-2021-00423-01 (30146)`), ese número se añade al título del documento (`25000-23-37-000-2021-00423-01(30146)(NRD)`) — tanto para documentos nuevos como para los 1,056 ya guardados.

**Architecture:** Reutiliza el mecanismo `title_unverified` + `BaseScrapper.resolve_unverified_document` que el proyecto ya usa en `core/scrapers/families/corte_suprema.py` para el mismo tipo de necesidad (leer la primera página del PDF ya descargado y ajustar el título). Se añade la misma lógica a `core/scrapers/families/samai.py`, solo para Consejo de Estado, más un script de una sola corrida (`core/backfill_ce_titles.py`) para los documentos ya existentes.

**Tech Stack:** Python, `pypdf` (ya es dependencia del proyecto), SQLAlchemy, pytest.

## Global Constraints

- Aplica solo a Consejo de Estado (`corp_code == "1100103"`), nunca a los 27 Tribunales Administrativos de la misma familia `samai`.
- Si el número no aparece en la primera página, o el PDF no se puede leer, el título se deja exactamente igual — nunca debe lanzar una excepción hacia el worker.
- El formato final es `{radicado}({número})({sigla})`, o `{radicado}({número})` cuando no hay sigla de clase.
- El backfill debe poder correrse más de una vez sin duplicar el número en el título.

---

### Task 1: Helpers de extracción y regex en `samai.py`

**Files:**
- Modify: `core/scrapers/families/samai.py`
- Test: `tests/families/test_samai.py`

**Interfaces:**
- Produces (usadas por Task 2 y Task 3):
  - `_extraer_texto_primera_pagina(local_path) -> str`
  - `_TITULO_CE_RE` (regex compilado): matchea un título de Consejo de Estado, `group(1)` = radicado, `group(2)` = `"(SIGLA)"` o `None`.
  - `_numero_extra_desde_texto(texto: str, radicado: str) -> Optional[str]`
  - `_complementar_titulo_con_numero(titulo: str, numero: str) -> str`

- [ ] **Step 1: Escribir las pruebas que fallan para los helpers**

Añadir al final de `tests/families/test_samai.py`:

```python
# --- número extra entre paréntesis (primera página del PDF) -----------------
#
# Algunos documentos de Consejo de Estado traen, junto al radicado en su
# primera página, un número entre paréntesis que no aparece en la tabla de
# resultados de SAMAI (ej. "Radicación  25000-...-01 (30146)"). Cuando
# aparece, se añade al título entre el radicado y la sigla de clase.

from core.scrapers.families.samai import (
    _TITULO_CE_RE,
    _numero_extra_desde_texto,
    _complementar_titulo_con_numero,
)


def test_titulo_ce_re_splits_radicado_and_acronimo():
    match = _TITULO_CE_RE.match("25000-23-37-000-2021-00423-01(NRD)")
    assert match.group(1) == "25000-23-37-000-2021-00423-01"
    assert match.group(2) == "(NRD)"


def test_titulo_ce_re_handles_title_without_acronimo():
    match = _TITULO_CE_RE.match("11001-03-24-000-2026-99999-00")
    assert match.group(1) == "11001-03-24-000-2026-99999-00"
    assert match.group(2) is None


def test_titulo_ce_re_does_not_match_tribunal_administrativo_titles():
    assert _TITULO_CE_RE.match("T_CUND_25001233300020260001200") is None


def test_numero_extra_desde_texto_finds_number_right_after_radicado():
    texto = "Radicación  25000-23-37-000-2021-00423-01 (30146)\nDemandante..."
    assert _numero_extra_desde_texto(texto, "25000-23-37-000-2021-00423-01") == "30146"


def test_numero_extra_desde_texto_returns_none_when_absent():
    texto = "Radicación  25000-23-37-000-2021-00423-01\nDemandante..."
    assert _numero_extra_desde_texto(texto, "25000-23-37-000-2021-00423-01") is None


def test_numero_extra_desde_texto_ignores_unrelated_parenthetical_numbers():
    # El (30146) aparece en el texto pero NO justo después del radicado —
    # no debe confundirse con el dato que buscamos.
    texto = "Ver más en (30146) — Radicación 25000-23-37-000-2021-00423-01 sin número"
    assert _numero_extra_desde_texto(texto, "25000-23-37-000-2021-00423-01") is None


def test_complementar_titulo_con_numero_inserts_between_radicado_and_acronimo():
    assert _complementar_titulo_con_numero("25000-23-37-000-2021-00423-01(NRD)", "30146") == (
        "25000-23-37-000-2021-00423-01(30146)(NRD)"
    )


def test_complementar_titulo_con_numero_appends_when_no_acronimo():
    assert _complementar_titulo_con_numero("11001-03-24-000-2026-99999-00", "30146") == (
        "11001-03-24-000-2026-99999-00(30146)"
    )
```

- [ ] **Step 2: Confirmar que fallan**

Run: `.venv/Scripts/pytest tests/families/test_samai.py -k "titulo_ce_re or numero_extra or complementar_titulo" -v`
Expected: FAIL — `ImportError: cannot import name '_TITULO_CE_RE'`.

- [ ] **Step 3: Implementar los helpers**

En `core/scrapers/families/samai.py`, añadir `import logging` justo después de `import re` (línea 1), y `logger = logging.getLogger(__name__)` después de la constante `_URL` (después de la línea 17):

```python
import logging
import re
```

```python
_URL = "https://samai.consejodeestado.gov.co/vistas/utiles/WEstados.aspx"

logger = logging.getLogger(__name__)
```

Luego, justo antes de `@register_family("samai")` (antes de la línea 249 actual, después de `_all_inputs`), añadir:

```python
# Un título de Consejo de Estado es siempre "{radicado}" o
# "{radicado}({SIGLA})" (ver _normalizar_titulo) — nunca el formato
# "T_{CÓDIGO}_..." de un Tribunal Administrativo, así que este patrón sirve
# tanto para separar el radicado como para confirmar que el título es
# realmente de Consejo de Estado antes de tocarlo.
_TITULO_CE_RE = re.compile(r"^([\d-]+)(\([A-Z0-9]+\))?$")


def _extraer_texto_primera_pagina(local_path) -> str:
    # A diferencia de CSJ (core/scrapers/families/corte_suprema.py), SAMAI
    # solo entrega PDF a través de su hop jwt_indirect — no hace falta
    # distinguir por content_type ni soportar .docx.
    from pypdf import PdfReader

    reader = PdfReader(str(local_path))
    if not reader.pages:
        return ""
    return reader.pages[0].extract_text() or ""


def _numero_extra_desde_texto(texto: str, radicado: str) -> Optional[str]:
    match = re.search(re.escape(radicado) + r"\s*\((\d+)\)", texto or "")
    return match.group(1) if match else None


def _complementar_titulo_con_numero(titulo: str, numero: str) -> str:
    match = _TITULO_CE_RE.match(titulo)
    if not match:
        return titulo
    radicado, sufijo_acronimo = match.group(1), match.group(2) or ""
    return f"{radicado}({numero}){sufijo_acronimo}"
```

- [ ] **Step 4: Confirmar que pasan**

Run: `.venv/Scripts/pytest tests/families/test_samai.py -k "titulo_ce_re or numero_extra or complementar_titulo" -v`
Expected: PASSED (7 tests)

- [ ] **Step 5: Commit**

```bash
git add core/scrapers/families/samai.py tests/families/test_samai.py
git commit -m "feat: helpers para extraer el número extra del radicado en la primera página de Consejo de Estado"
```

---

### Task 2: Marcar `title_unverified` e implementar `resolve_unverified_document`

**Files:**
- Modify: `core/scrapers/families/samai.py`
- Test: `tests/families/test_samai.py`

**Interfaces:**
- Consumes: `_TITULO_CE_RE`, `_extraer_texto_primera_pagina`, `_numero_extra_desde_texto`, `_complementar_titulo_con_numero` (Task 1).
- Produces: `ScrapTribunales.resolve_unverified_document(self, doc, local_path, content_type) -> None` — consumido por `worker/tasks.py` (ya existente, sin cambios) y por Task 4 (backfill, vía las mismas funciones de Task 1).

- [ ] **Step 1: Escribir la prueba que falla — la bandera se activa solo para Consejo de Estado**

Añadir a `tests/families/test_samai.py`:

```python
def test_parse_row_flags_title_unverified_only_for_consejo_de_estado():
    row = BeautifulSoup(_ROW_HTML, "html.parser").find("tr")

    ce_scraper = ScrapTribunales("1100103", "Consejo de Estado")
    ce_doc = ce_scraper._parse_row(row, "1100103", "Consejo de Estado", "Sección Primera", "2026-06-15")
    assert ce_doc.title_unverified is True

    tribunal_scraper = ScrapTribunales("2500023", "Tribunal Administrativo de Cundinamarca")
    tribunal_doc = tribunal_scraper._parse_row(
        row, "2500023", "Tribunal Administrativo de Cundinamarca", "Sección Primera", "2026-06-15"
    )
    assert tribunal_doc.title_unverified is False
```

- [ ] **Step 2: Confirmar que falla**

Run: `.venv/Scripts/pytest tests/families/test_samai.py::test_parse_row_flags_title_unverified_only_for_consejo_de_estado -v`
Expected: FAIL — `AssertionError` (RawDocModel usa el default `title_unverified=False` para todos).

- [ ] **Step 3: Activar la bandera en `_parse_row`**

En `core/scrapers/families/samai.py`, dentro de `_parse_row` (busca el `return RawDocModel(` al final del método, alrededor de la línea 482), añadir el campo `title_unverified`:

```python
        return RawDocModel(
            source=corp_name,
            link={
                "url": jwt_url,
                "method": "jwt_indirect",
                "body": {"path": f"{corp_code}_{radicado}_{identidad_fecha}"},
            },
            title=titulo,
            tipo=tipo,
            detalle=actuacion,
            seccion=seccion,
            especialidad=_especialidad_legible(clase),
            f_public=estado_fecha_str,
            f_providencia=fecha_prov,
            save_path=path,
            # Solo Consejo de Estado: algunos de sus documentos traen, en la
            # primera página del PDF, un número entre paréntesis junto al
            # radicado que no aparece en esta tabla — resolve_unverified_document
            # lo busca una vez descargado el archivo y complementa el título.
            title_unverified=(corp_code == _CONSEJO_DE_ESTADO_CORP_CODE),
        )
```

- [ ] **Step 4: Confirmar que pasa**

Run: `.venv/Scripts/pytest tests/families/test_samai.py::test_parse_row_flags_title_unverified_only_for_consejo_de_estado -v`
Expected: PASSED

- [ ] **Step 5: Escribir las pruebas que fallan para `resolve_unverified_document`**

Añadir a `tests/families/test_samai.py` (necesita `from pathlib import Path` y `import core.scrapers.families.samai as samai_module` al inicio del archivo):

```python
def test_resolve_unverified_document_appends_extra_number_when_found_on_first_page(monkeypatch):
    monkeypatch.setattr(
        samai_module,
        "_extraer_texto_primera_pagina",
        lambda *_a, **_k: "Radicación  25000-23-37-000-2021-00423-01 (30146)",
    )

    class _Doc:
        title = "25000-23-37-000-2021-00423-01(NRD)"

    doc = _Doc()
    scraper = ScrapTribunales("1100103", "Consejo de Estado")
    scraper.resolve_unverified_document(doc, Path("fake.pdf"), "application/pdf")

    assert doc.title == "25000-23-37-000-2021-00423-01(30146)(NRD)"


def test_resolve_unverified_document_appends_number_when_title_has_no_acronimo(monkeypatch):
    monkeypatch.setattr(
        samai_module,
        "_extraer_texto_primera_pagina",
        lambda *_a, **_k: "Radicación  11001-03-24-000-2026-99999-00 (30146)",
    )

    class _Doc:
        title = "11001-03-24-000-2026-99999-00"

    doc = _Doc()
    scraper = ScrapTribunales("1100103", "Consejo de Estado")
    scraper.resolve_unverified_document(doc, Path("fake.pdf"), "application/pdf")

    assert doc.title == "11001-03-24-000-2026-99999-00(30146)"


def test_resolve_unverified_document_leaves_title_unchanged_when_number_not_found(monkeypatch):
    monkeypatch.setattr(
        samai_module,
        "_extraer_texto_primera_pagina",
        lambda *_a, **_k: "Radicación  25000-23-37-000-2021-00423-01",
    )

    class _Doc:
        title = "25000-23-37-000-2021-00423-01(NRD)"

    doc = _Doc()
    scraper = ScrapTribunales("1100103", "Consejo de Estado")
    scraper.resolve_unverified_document(doc, Path("fake.pdf"), "application/pdf")

    assert doc.title == "25000-23-37-000-2021-00423-01(NRD)"


def test_resolve_unverified_document_is_defensive_about_read_failures(monkeypatch, caplog):
    def _raise(*_a, **_k):
        raise RuntimeError("archivo corrupto")

    monkeypatch.setattr(samai_module, "_extraer_texto_primera_pagina", _raise)

    class _Doc:
        title = "25000-23-37-000-2021-00423-01(NRD)"

    doc = _Doc()
    scraper = ScrapTribunales("1100103", "Consejo de Estado")
    with caplog.at_level("WARNING", logger="core.scrapers.families.samai"):
        scraper.resolve_unverified_document(doc, Path("fake.pdf"), "application/pdf")  # no debe lanzar

    assert doc.title == "25000-23-37-000-2021-00423-01(NRD)"


def test_resolve_unverified_document_ignores_tribunal_administrativo_title_format(monkeypatch):
    monkeypatch.setattr(
        samai_module,
        "_extraer_texto_primera_pagina",
        lambda *_a, **_k: "cualquier texto con (30146) en la página",
    )

    class _Doc:
        title = "T_CUND_25001233300020260001200"

    doc = _Doc()
    scraper = ScrapTribunales("2500023", "Tribunal Administrativo de Cundinamarca")
    scraper.resolve_unverified_document(doc, Path("fake.pdf"), "application/pdf")

    assert doc.title == "T_CUND_25001233300020260001200"
```

- [ ] **Step 6: Confirmar que fallan**

Run: `.venv/Scripts/pytest tests/families/test_samai.py -k resolve_unverified_document -v`
Expected: FAIL — `AttributeError: 'ScrapTribunales' object has no attribute 'resolve_unverified_document'`.

- [ ] **Step 7: Implementar `resolve_unverified_document`**

En `core/scrapers/families/samai.py`, dentro de la clase `ScrapTribunales`, justo después de `__init__` (antes de `def scrap`, alrededor de la línea 271 actual), añadir:

```python
    def resolve_unverified_document(self, doc, local_path, content_type) -> None:
        # Se dispara solo para Consejo de Estado (ver title_unverified en
        # _parse_row) — este chequeo extra es defensivo: si algún día algo
        # más marca title_unverified=True, un título de Tribunal
        # Administrativo simplemente no matchea _TITULO_CE_RE y se ignora.
        match = _TITULO_CE_RE.match(doc.title)
        if not match:
            return
        radicado = match.group(1)

        try:
            texto = _extraer_texto_primera_pagina(local_path)
        except Exception as e:
            logger.warning(
                "No se pudo leer la primera página de %s para complementar el título: %s",
                local_path.name, e,
            )
            return

        numero = _numero_extra_desde_texto(texto, radicado)
        if not numero:
            return

        doc.title = _complementar_titulo_con_numero(doc.title, numero)
```

- [ ] **Step 8: Confirmar que pasan**

Run: `.venv/Scripts/pytest tests/families/test_samai.py -v`
Expected: PASSED (todas, incluyendo las de Task 1 y las ya existentes — el archivo completo no debe romperse)

- [ ] **Step 9: Commit**

```bash
git add core/scrapers/families/samai.py tests/families/test_samai.py
git commit -m "feat: complementa el título de Consejo de Estado con el número de la primera página del PDF"
```

---

### Task 3: Script de backfill para los documentos existentes

**Files:**
- Create: `core/backfill_ce_titles.py`
- Test: `tests/test_backfill_ce_titles.py`

**Interfaces:**
- Consumes: `_TITULO_CE_RE`, `_extraer_texto_primera_pagina`, `_numero_extra_desde_texto`, `_complementar_titulo_con_numero` (Task 1); `repository.update_document_title(db, document_id, title)` (ya existente); `core.storage.download_file(bucket, key, local_path)` (ya existente).
- Produces: `backfill(db: Session) -> dict` con clave `"documents_updated"`.

- [ ] **Step 1: Escribir las pruebas que fallan**

Crear `tests/test_backfill_ce_titles.py`:

```python
from pathlib import Path

from core.backfill_ce_titles import backfill
import core.backfill_ce_titles as backfill_module
from core.db import repository


def _consejo_de_estado_source(db_session):
    repository.create_source_family(db_session, key="samai", display_name="SAMAI")
    return repository.create_source(db_session, family_key="samai", name="Consejo de Estado", family_params={})


def test_backfill_updates_title_when_number_found_on_first_page(db_session, monkeypatch):
    source = _consejo_de_estado_source(db_session)
    doc = repository.insert_document(
        db_session,
        doc_id="doc-1",
        source_id=source.id,
        title="25000-23-37-000-2021-00423-01(NRD)",
        storage_bucket="iurisync-test",
        storage_key="a.pdf",
    )

    monkeypatch.setattr(backfill_module, "download_file", lambda *_a, **_k: None)
    monkeypatch.setattr(
        backfill_module,
        "_extraer_texto_primera_pagina",
        lambda *_a, **_k: "Radicación  25000-23-37-000-2021-00423-01 (30146)",
    )

    result = backfill(db_session)

    db_session.refresh(doc)
    assert doc.title == "25000-23-37-000-2021-00423-01(30146)(NRD)"
    assert result["documents_updated"] == 1


def test_backfill_leaves_title_untouched_when_number_not_found(db_session, monkeypatch):
    source = _consejo_de_estado_source(db_session)
    doc = repository.insert_document(
        db_session,
        doc_id="doc-1",
        source_id=source.id,
        title="25000-23-37-000-2021-00423-01(NRD)",
        storage_bucket="iurisync-test",
        storage_key="a.pdf",
    )

    monkeypatch.setattr(backfill_module, "download_file", lambda *_a, **_k: None)
    monkeypatch.setattr(
        backfill_module,
        "_extraer_texto_primera_pagina",
        lambda *_a, **_k: "Radicación  25000-23-37-000-2021-00423-01",
    )

    result = backfill(db_session)

    db_session.refresh(doc)
    assert doc.title == "25000-23-37-000-2021-00423-01(NRD)"
    assert result["documents_updated"] == 0


def test_backfill_is_idempotent_across_two_runs(db_session, monkeypatch):
    source = _consejo_de_estado_source(db_session)
    doc = repository.insert_document(
        db_session,
        doc_id="doc-1",
        source_id=source.id,
        title="25000-23-37-000-2021-00423-01(NRD)",
        storage_bucket="iurisync-test",
        storage_key="a.pdf",
    )

    monkeypatch.setattr(backfill_module, "download_file", lambda *_a, **_k: None)
    monkeypatch.setattr(
        backfill_module,
        "_extraer_texto_primera_pagina",
        lambda *_a, **_k: "Radicación  25000-23-37-000-2021-00423-01 (30146)",
    )

    backfill(db_session)
    second_result = backfill(db_session)

    db_session.refresh(doc)
    assert doc.title == "25000-23-37-000-2021-00423-01(30146)(NRD)"
    assert second_result["documents_updated"] == 0


def test_backfill_ignores_documents_from_other_sources(db_session, monkeypatch):
    repository.create_source_family(db_session, key="samai", display_name="SAMAI")
    tribunal = repository.create_source(
        db_session, family_key="samai", name="Tribunal Administrativo de Cundinamarca", family_params={}
    )
    repository.insert_document(
        db_session,
        doc_id="doc-1",
        source_id=tribunal.id,
        title="T_CUND_25001233300020260001200",
        storage_bucket="iurisync-test",
        storage_key="a.pdf",
    )

    called = []
    monkeypatch.setattr(backfill_module, "download_file", lambda *a, **k: called.append(a))

    result = backfill(db_session)

    assert called == []
    assert result["documents_updated"] == 0
```

- [ ] **Step 2: Confirmar que fallan**

Run: `.venv/Scripts/pytest tests/test_backfill_ce_titles.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'core.backfill_ce_titles'`.

- [ ] **Step 3: Implementar**

Crear `core/backfill_ce_titles.py`:

```python
"""Corrida única: complementa el título de los documentos de Consejo de
Estado ya guardados con el número entre paréntesis que a veces aparece junto
al radicado en la primera página del PDF — ver
docs/superpowers/specs/2026-08-03-titulo-consejo-estado-design.md.

Uso: .venv/Scripts/python -m core.backfill_ce_titles
Se puede correr más de una vez sin problema: un documento cuyo título ya
tiene el número entre paréntesis, o cuyo PDF no lo trae, se deja tal cual.
"""
import logging
import re
from pathlib import Path
from tempfile import TemporaryDirectory

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.db import repository
from core.db.models import Document, Source
from core.db.session import SessionLocal
from core.scrapers.families.samai import (
    _TITULO_CE_RE,
    _complementar_titulo_con_numero,
    _extraer_texto_primera_pagina,
    _numero_extra_desde_texto,
)
from core.storage import download_file

logger = logging.getLogger(__name__)

# Un título ya complementado trae el número justo después del radicado —
# "{radicado}({número})..." — si el título ya tiene esa forma no hay nada
# que hacer, lo que permite correr este backfill más de una vez sin duplicar
# el número ni volver a descargar el PDF innecesariamente.
_YA_COMPLEMENTADO_RE = re.compile(r"^[\d-]+\(\d+\)")


def backfill(db: Session) -> dict:
    documentos = db.scalars(
        select(Document).join(Source, Source.id == Document.source_id).where(Source.name == "Consejo de Estado")
    ).all()

    documents_updated = 0
    with TemporaryDirectory() as tmp_dir:
        for documento in documentos:
            if _YA_COMPLEMENTADO_RE.match(documento.title):
                continue
            match = _TITULO_CE_RE.match(documento.title)
            if not match:
                continue
            radicado = match.group(1)

            local_path = Path(tmp_dir) / f"{documento.id}.pdf"
            try:
                download_file(documento.storage_bucket, documento.storage_key, local_path)
                texto = _extraer_texto_primera_pagina(local_path)
            except Exception as e:
                logger.warning("No se pudo leer el documento %s: %s", documento.id, e)
                continue
            finally:
                local_path.unlink(missing_ok=True)

            numero = _numero_extra_desde_texto(texto, radicado)
            if not numero:
                continue

            nuevo_titulo = _complementar_titulo_con_numero(documento.title, numero)
            repository.update_document_title(db, documento.id, nuevo_titulo)
            documents_updated += 1

    return {"documents_updated": documents_updated}


def main():
    db = SessionLocal()
    try:
        result = backfill(db)
        print(f"Documentos actualizados: {result['documents_updated']}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Confirmar que pasan**

Run: `.venv/Scripts/pytest tests/test_backfill_ce_titles.py -v`
Expected: PASSED

- [ ] **Step 5: Commit**

```bash
git add core/backfill_ce_titles.py tests/test_backfill_ce_titles.py
git commit -m "feat: script de una sola corrida para complementar títulos de Consejo de Estado ya guardados"
```

---

### Task 4: Verificación final y corrida contra la base de desarrollo

**Files:** ninguno nuevo — solo ejecución y verificación.

- [ ] **Step 1: Correr toda la suite de pruebas de Python**

Run: `.venv/Scripts/pytest -v`
Expected: PASSED (todo, sin regresiones en otras familias ni en `test_tasks.py`)

- [ ] **Step 2: Correr el backfill contra la base de datos real de desarrollo**

Requiere que `scrapper-avanzado-postgres-1` y `scrapper-avanzado-minio-1` estén corriendo (`docker ps`).

Run: `.venv/Scripts/python -m core.backfill_ce_titles`
Expected: imprime `Documentos actualizados: N` (N puede ser 0 si ninguno de los 1,056 documentos actuales trae el número — no es un error, ver el diseño: se validó contra una muestra real que el patrón aparece solo en algunos documentos).

- [ ] **Step 3: Confirmar a mano contra la base de datos**

Run:
```bash
docker exec scrapper-avanzado-postgres-1 psql -U iurisync -d iurisync -c "
SELECT title FROM documents d JOIN sources s ON s.id = d.source_id
WHERE s.name = 'Consejo de Estado' AND title ~ '^[0-9-]+\(\d+\)\(' LIMIT 10;
"
```
Expected: si el backfill actualizó algún documento, aparece aquí con el formato `{radicado}({número})({sigla})`. Confirma con el usuario cuántos se actualizaron antes de dar la tarea por terminada.

- [ ] **Step 4: Reportar al usuario en español sencillo**

Resumir: cuántos documentos de los 1,056 existentes se actualizaron con el número extra, y que de ahora en adelante los documentos nuevos de Consejo de Estado lo incluirán automáticamente cuando el PDF lo traiga.
