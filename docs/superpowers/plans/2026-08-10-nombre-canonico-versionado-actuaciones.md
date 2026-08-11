# Nombre canónico con versionado y actuaciones — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Un único nombre canónico por documento —`{base}[_{fecha_providencia AAAAMMDD}][_v{n}]`— idéntico en la app y en todas las descargas (individual, versión, ZIP, previsualización), para todas las fuentes.

**Architecture:** El nombre se **calcula** a partir de datos ya existentes (`title`, familia con actuaciones, `f_providencia`/`f_public`) más un `version_no` persistido; no se renombran ni mueven archivos en el almacenamiento. Rama Judicial extrae la fecha de providencia de la primera página del PDF (con respaldo a la fecha de listado). El backend expone un campo `nombre`; el frontend lo usa para mostrar y para nombrar la descarga.

**Tech Stack:** Python/FastAPI, SQLAlchemy, Alembic, Celery, pypdf; React/TypeScript/Vite; Postgres/MinIO vía Docker.

## Global Constraints

- **Enfoque calculado, sin tocar almacenamiento:** no renombrar `storage_key`, no mover objetos en MinIO, no cambiar `doc_id` ni la detección de republicación.
- **`title` se conserva** como "base" (uso interno + agrupación de actuaciones); el nombre canónico es capa de presentación.
- **Regla del nombre:** `{base}` → `_{fecha:%Y%m%d}` solo si familia con actuaciones (`samai`, `rama_judicial`) **y** título con forma de radicado → `_v{n}` solo si `version_no > 1`. Orden fijo: base, fecha, versión.
- **Fecha para el sufijo:** `f_providencia` si existe, si no `f_public` (respaldo), solo para familias con actuaciones.
- **Dependencia nueva:** `cryptography>=3.1` en `requirements.txt` (PDFs de Rama Judicial cifrados con AES).
- **Comentarios y textos de usuario en español**, siguiendo el estilo del repo.
- **Pruebas:** backend `.venv/Scripts/pytest` (suites de BD dirigidas, no en paralelo). Frontend `cd frontend && npm test -- --run`. Ignorar el fallo pre-existente de `test_migrations.py` en Windows.
- **Producción:** servidor de oficina en Windows/PowerShell; despliegue vía merge → CI (GHCR) → `docker compose pull/up` → correr backfill una vez.

---

### Task 1: Columna `version_no` en `documents` y `document_versions` (+ migración)

**Files:**
- Modify: `core/db/models.py:103-153` (clases `Document` y `DocumentVersion`)
- Create: `alembic/versions/b2c3d4e5f6a7_add_version_no.py`
- Test: `tests/test_repository.py`

**Interfaces:**
- Produces: `Document.version_no: int` (no nulo, default 1) y `DocumentVersion.version_no: int` (no nulo, default 1).

- [ ] **Step 1: Escribir el test que falla**

En `tests/test_repository.py` agregar:

```python
def test_new_document_defaults_to_version_no_1(db_session):
    repository.create_source_family(db_session, key="constitucional", display_name="Corte Constitucional")
    source = repository.create_source(db_session, family_key="constitucional", name="Corte Constitucional", family_params={})
    doc = repository.insert_document(
        db_session,
        doc_id="doc-vn-1",
        source_id=source.id,
        title="T-100/24",
        storage_bucket="iurisync-test",
        storage_key="a.pdf",
    )
    assert doc.version_no == 1
```

- [ ] **Step 2: Correr el test y verificar que falla**

Run: `.venv/Scripts/pytest tests/test_repository.py::test_new_document_defaults_to_version_no_1 -v`
Expected: FAIL (`AttributeError: 'Document' object has no attribute 'version_no'` o error de columna inexistente).

- [ ] **Step 3: Agregar la columna en el modelo**

En `core/db/models.py`, dentro de `class Document` (después de `review_status`/`reviewed_at`):

```python
    # Número de versión de esta actuación. 1 al crearse; se incrementa en cada
    # republicación (ver archive_and_replace_document). El nombre canónico
    # muestra "_v{n}" solo cuando hay más de una versión (version_no > 1).
    version_no = Column(Integer, nullable=False, default=1, server_default="1")
```

Dentro de `class DocumentVersion` (después de `superseded_at`):

```python
    # Número de versión que tenía el documento cuando ESTA versión era la
    # vigente (la más antigua = 1). Fijado al archivar en
    # archive_and_replace_document.
    version_no = Column(Integer, nullable=False, default=1, server_default="1")
```

- [ ] **Step 4: Crear la migración Alembic**

Crear `alembic/versions/b2c3d4e5f6a7_add_version_no.py`:

```python
"""add version_no to documents and document_versions

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-08-10

"""
from alembic import op
import sqlalchemy as sa

revision = "b2c3d4e5f6a7"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column("version_no", sa.Integer(), nullable=False, server_default="1"),
    )
    op.add_column(
        "document_versions",
        sa.Column("version_no", sa.Integer(), nullable=False, server_default="1"),
    )


def downgrade() -> None:
    op.drop_column("document_versions", "version_no")
    op.drop_column("documents", "version_no")
```

- [ ] **Step 5: Aplicar la migración y correr el test**

Run:
```bash
.venv/Scripts/alembic upgrade head && .venv/Scripts/pytest tests/test_repository.py::test_new_document_defaults_to_version_no_1 -v
```
Expected: migración OK y test PASS.

- [ ] **Step 6: Commit**

```bash
git add core/db/models.py alembic/versions/b2c3d4e5f6a7_add_version_no.py tests/test_repository.py
git commit -m "feat(db): version_no en documents y document_versions"
```

---

### Task 2: Incrementar `version_no` al republicar

**Files:**
- Modify: `core/db/repository.py:316-355` (`archive_and_replace_document`)
- Test: `tests/test_repository.py`

**Interfaces:**
- Consumes: `Document.version_no`, `DocumentVersion.version_no` (Task 1).
- Produces: al archivar, la versión guardada hereda el `version_no` actual del documento y el documento incrementa en 1.

- [ ] **Step 1: Escribir el test que falla**

```python
def test_republication_increments_version_no(db_session):
    repository.create_source_family(db_session, key="samai", display_name="SAMAI")
    source = repository.create_source(db_session, family_key="samai", name="Consejo de Estado", family_params={})
    doc = repository.insert_document(
        db_session, doc_id="doc-vn-2", source_id=source.id, title="rad-1",
        storage_bucket="iurisync-test", storage_key="v1.pdf",
    )
    assert doc.version_no == 1

    repository.archive_and_replace_document(
        db_session, doc.id, storage_bucket="iurisync-test", storage_key="v2.pdf",
    )
    versions = repository.list_document_versions(db_session, doc.id)
    assert [v.version_no for v in versions] == [1]
    refreshed = repository.get_document(db_session, doc.id)
    assert refreshed.version_no == 2

    repository.archive_and_replace_document(
        db_session, doc.id, storage_bucket="iurisync-test", storage_key="v3.pdf",
    )
    versions = repository.list_document_versions(db_session, doc.id)
    assert sorted(v.version_no for v in versions) == [1, 2]
    assert repository.get_document(db_session, doc.id).version_no == 3
```

- [ ] **Step 2: Correr el test y verificar que falla**

Run: `.venv/Scripts/pytest tests/test_repository.py::test_republication_increments_version_no -v`
Expected: FAIL (versión archivada con `version_no` incorrecto / documento no incrementa).

- [ ] **Step 3: Implementar el incremento**

En `core/db/repository.py`, dentro de `archive_and_replace_document`, al construir `version = DocumentVersion(...)` agregar el campo `version_no=document.version_no`, y después de `document.downloaded_at = ...` agregar el incremento. Queda así:

```python
    version = DocumentVersion(
        document_id=document.id,
        storage_bucket=document.storage_bucket,
        storage_key=document.storage_key,
        content_type=document.content_type,
        file_extension=document.file_extension,
        file_size_bytes=document.file_size_bytes,
        converted_format=document.converted_format,
        source_url=document.source_url,
        downloaded_at=document.downloaded_at,
        version_no=document.version_no,
    )
    db.add(version)
    for key, value in new_fields.items():
        setattr(document, key, value)
    document.downloaded_at = datetime.now(timezone.utc)
    # La versión recién archivada conserva el número que tenía el documento; la
    # nueva versión vigente es el siguiente entero. Así "_v{n}" del nombre
    # canónico refleja el orden real (la más antigua = 1, la vigente = la mayor).
    document.version_no = document.version_no + 1
```

- [ ] **Step 4: Correr el test y verificar que pasa**

Run: `.venv/Scripts/pytest tests/test_repository.py::test_republication_increments_version_no -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add core/db/repository.py tests/test_repository.py
git commit -m "feat(repo): incrementar version_no al republicar y archivar"
```

---

### Task 3: Función pura de nombre canónico + detección de familia con actuaciones

**Files:**
- Create: `core/naming.py`
- Test: `tests/test_naming.py`

**Interfaces:**
- Consumes: `core.utils.is_radicado_title`, `core.utils.is_samai_case_title`.
- Produces:
  - `es_familia_con_actuaciones(family_key: Optional[str], title: str) -> bool`
  - `construir_nombre(base: str, fecha: Optional[date], es_caso: bool, version_no: int, total_versiones: int) -> str`

- [ ] **Step 1: Escribir el test que falla**

Crear `tests/test_naming.py`:

```python
from datetime import date

from core.naming import construir_nombre, es_familia_con_actuaciones


def test_sin_actuaciones_una_version():
    assert construir_nombre("T-123-24", None, es_caso=False, version_no=1, total_versiones=1) == "T-123-24"


def test_sin_actuaciones_republicado():
    assert construir_nombre("T-123-24", None, es_caso=False, version_no=1, total_versiones=2) == "T-123-24_v1"
    assert construir_nombre("T-123-24", None, es_caso=False, version_no=2, total_versiones=2) == "T-123-24_v2"


def test_con_actuaciones():
    n = construir_nombre("11001-03-28-000-2026-00300-00", date(2026, 7, 31), es_caso=True, version_no=1, total_versiones=1)
    assert n == "11001-03-28-000-2026-00300-00_20260731"


def test_con_actuaciones_y_version():
    n = construir_nombre("11001-03-28-000-2026-00300-00", date(2026, 7, 31), es_caso=True, version_no=1, total_versiones=2)
    assert n == "11001-03-28-000-2026-00300-00_20260731_v1"


def test_con_actuaciones_sin_fecha_no_agrega_sufijo_fecha():
    assert construir_nombre("rad-x", None, es_caso=True, version_no=1, total_versiones=1) == "rad-x"


def test_familia_samai_con_titulo_de_radicado_es_caso():
    assert es_familia_con_actuaciones("samai", "11001-03-28-000-2026-00300-00") is True


def test_familia_rama_judicial_con_titulo_de_radicado_es_caso():
    assert es_familia_con_actuaciones("rama_judicial", "T_11_11001_31_03_022_2019_00814_02") is True


def test_familia_sin_actuaciones_no_es_caso():
    assert es_familia_con_actuaciones("constitucional", "T-123-24") is False


def test_familia_desconocida_o_none_no_es_caso():
    assert es_familia_con_actuaciones(None, "cualquier-cosa") is False
```

- [ ] **Step 2: Correr el test y verificar que falla**

Run: `.venv/Scripts/pytest tests/test_naming.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'core.naming'`).

- [ ] **Step 3: Implementar `core/naming.py`**

```python
from datetime import date
from typing import Optional

from core.utils import is_radicado_title, is_samai_case_title

# Familias cuyo título identifica un proceso (no una providencia puntual): sus
# documentos "tienen actuaciones" y llevan el sufijo de fecha. Cada una trae su
# propio chequeo de "¿este título parece de caso?" — mismo criterio que la
# agrupación en api/routers/documents.py, centralizado aquí para reutilizarlo.
_FAMILIAS_CON_ACTUACIONES = {
    "rama_judicial": is_radicado_title,
    "samai": lambda t: is_samai_case_title(t) or is_radicado_title(t),
}


def es_familia_con_actuaciones(family_key: Optional[str], title: str) -> bool:
    check = _FAMILIAS_CON_ACTUACIONES.get(family_key or "")
    return bool(check and check(title))


def construir_nombre(
    base: str,
    fecha: Optional[date],
    es_caso: bool,
    version_no: int,
    total_versiones: int,
) -> str:
    """Arma el nombre canónico: base, luego fecha de providencia (AAAAMMDD) solo
    si el documento tiene actuaciones y hay una fecha, luego "_v{n}" solo si hay
    más de una versión. No incluye la extensión del archivo."""
    nombre = base
    if es_caso and fecha is not None:
        nombre = f"{nombre}_{fecha.strftime('%Y%m%d')}"
    if total_versiones > 1:
        nombre = f"{nombre}_v{version_no}"
    return nombre
```

- [ ] **Step 4: Correr el test y verificar que pasa**

Run: `.venv/Scripts/pytest tests/test_naming.py -v`
Expected: PASS (9 tests).

- [ ] **Step 5: Commit**

```bash
git add core/naming.py tests/test_naming.py
git commit -m "feat(naming): función de nombre canónico y detección de familia con actuaciones"
```

---

### Task 4: Envoltorios de nombre para documento/versión y helpers de archivo (con extensión)

**Files:**
- Modify: `core/naming.py`
- Test: `tests/test_naming.py`

**Interfaces:**
- Consumes: `construir_nombre`, `es_familia_con_actuaciones` (Task 3). Objetos con atributos: documento (`title`, `f_providencia`, `f_public`, `version_no`, `storage_key`); versión (`version_no`, `storage_key`).
- Produces:
  - `nombre_documento(document, family_key: Optional[str]) -> str`
  - `nombre_version(document, version, family_key: Optional[str]) -> str`
  - `nombre_archivo_documento(document, family_key: Optional[str]) -> str`
  - `nombre_archivo_version(document, version, family_key: Optional[str]) -> str`

- [ ] **Step 1: Escribir el test que falla**

Agregar a `tests/test_naming.py`:

```python
from datetime import date
from types import SimpleNamespace

from core.naming import (
    nombre_archivo_documento,
    nombre_archivo_version,
    nombre_documento,
    nombre_version,
)


def _doc(**kw):
    base = dict(title="rad-1", f_providencia=None, f_public=None, version_no=1, storage_key="x.pdf")
    base.update(kw)
    return SimpleNamespace(**base)


def test_nombre_documento_caso_usa_f_providencia():
    d = _doc(title="11001", f_providencia=date(2026, 7, 31), version_no=1)
    assert nombre_documento(d, "samai") == "11001_20260731"


def test_nombre_documento_caso_respaldo_f_public_cuando_no_hay_providencia():
    d = _doc(title="T_11_x", f_providencia=None, f_public=date(2026, 8, 10), version_no=1)
    assert nombre_documento(d, "rama_judicial") == "T_11_x_20260810"


def test_nombre_documento_no_caso_ignora_fecha():
    d = _doc(title="T-123-24", f_providencia=date(2026, 7, 31), version_no=1)
    assert nombre_documento(d, "constitucional") == "T-123-24"


def test_nombre_documento_vigente_con_varias_versiones():
    d = _doc(title="T-123-24", version_no=2)
    assert nombre_documento(d, "constitucional") == "T-123-24_v2"


def test_nombre_version_usa_su_propio_numero_y_la_fecha_del_documento():
    d = _doc(title="11001", f_providencia=date(2026, 7, 31), version_no=2)
    v = SimpleNamespace(version_no=1, storage_key="v1.pdf")
    assert nombre_version(d, v, "samai") == "11001_20260731_v1"


def test_nombre_archivo_agrega_extension_del_storage_key():
    d = _doc(title="T-123-24", version_no=1, storage_key="carpeta/archivo.rtf")
    assert nombre_archivo_documento(d, "constitucional") == "T-123-24.rtf"


def test_nombre_archivo_version_agrega_extension_del_storage_key_de_la_version():
    d = _doc(title="11001", f_providencia=date(2026, 7, 31), version_no=2)
    v = SimpleNamespace(version_no=1, storage_key="a/b/v1.pdf")
    assert nombre_archivo_version(d, v, "samai") == "11001_20260731_v1.pdf"
```

- [ ] **Step 2: Correr el test y verificar que falla**

Run: `.venv/Scripts/pytest tests/test_naming.py -v`
Expected: FAIL (`ImportError` de los nuevos nombres).

- [ ] **Step 3: Implementar los envoltorios en `core/naming.py`**

Agregar al final (y a los imports `from pathlib import PurePosixPath`):

```python
def _fecha_para_nombre(document):
    # f_providencia manda; si no está, se usa f_public como respaldo (solo
    # relevante para familias con actuaciones, ver es_familia_con_actuaciones).
    return document.f_providencia or document.f_public


def nombre_documento(document, family_key: Optional[str]) -> str:
    es_caso = es_familia_con_actuaciones(family_key, document.title)
    # El documento vigente siempre lleva el número de versión más alto, así que
    # total_versiones == version_no y el sufijo aparece cuando version_no > 1.
    return construir_nombre(
        document.title, _fecha_para_nombre(document), es_caso,
        version_no=document.version_no, total_versiones=document.version_no,
    )


def nombre_version(document, version, family_key: Optional[str]) -> str:
    es_caso = es_familia_con_actuaciones(family_key, document.title)
    # Una versión archivada solo existe si hubo republicación, así que el total
    # (el version_no del documento vigente) siempre es > 1 y el sufijo aparece.
    return construir_nombre(
        document.title, _fecha_para_nombre(document), es_caso,
        version_no=version.version_no, total_versiones=document.version_no,
    )


def _con_extension(nombre: str, storage_key: str) -> str:
    ext = PurePosixPath(storage_key).suffix
    return f"{nombre}{ext}" if ext else nombre


def nombre_archivo_documento(document, family_key: Optional[str]) -> str:
    return _con_extension(nombre_documento(document, family_key), document.storage_key)


def nombre_archivo_version(document, version, family_key: Optional[str]) -> str:
    return _con_extension(nombre_version(document, version, family_key), version.storage_key)
```

- [ ] **Step 4: Correr el test y verificar que pasa**

Run: `.venv/Scripts/pytest tests/test_naming.py -v`
Expected: PASS (todos).

- [ ] **Step 5: Commit**

```bash
git add core/naming.py tests/test_naming.py
git commit -m "feat(naming): envoltorios de nombre para documento/versión y helpers de archivo"
```

---

### Task 5: Parser de fecha de providencia en español

**Files:**
- Create: `core/fecha_es.py`
- Test: `tests/test_fecha_es.py`

**Interfaces:**
- Produces: `parse_fecha_providencia_es(texto: str) -> Optional[date]`

- [ ] **Step 1: Escribir el test que falla**

Crear `tests/test_fecha_es.py` con cadenas reales capturadas de PDFs de Rama Judicial:

```python
from datetime import date

from core.fecha_es import parse_fecha_providencia_es


def test_dia_en_digitos():
    assert parse_fecha_providencia_es("Bogotá, 8 de mayo de 2026") == date(2026, 5, 8)


def test_dia_en_digitos_con_cero():
    assert parse_fecha_providencia_es("05 de marzo de 2026") == date(2026, 3, 5)


def test_dia_en_letras_con_numero_entre_parentesis():
    txt = "Bogotá, diez (10) de agosto de dos mil veintiséis (2026)"
    assert parse_fecha_providencia_es(txt) == date(2026, 8, 10)


def test_con_salto_de_linea():
    assert parse_fecha_providencia_es("6 de agosto \n de 2026") == date(2026, 8, 6)


def test_toma_la_primera_fecha_valida():
    txt = "Auto del 2 de junio de 2026 que confirma el del 3 de octubre de 2025"
    assert parse_fecha_providencia_es(txt) == date(2026, 6, 2)


def test_sin_fecha_devuelve_none():
    assert parse_fecha_providencia_es("No hay fecha aquí") is None


def test_mes_invalido_devuelve_none():
    assert parse_fecha_providencia_es("32 de mayo de 2026") is None
```

- [ ] **Step 2: Correr el test y verificar que falla**

Run: `.venv/Scripts/pytest tests/test_fecha_es.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'core.fecha_es'`).

- [ ] **Step 3: Implementar `core/fecha_es.py`**

```python
import re
from datetime import date
from typing import Optional

_MESES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10,
    "noviembre": 11, "diciembre": 12,
}

# Día como dígito (opcionalmente entre paréntesis, como en "diez (10) de ...")
# seguido de "de {mes} de", y luego el primer número de 4 dígitos que aparezca
# (el año, que puede venir entre paréntesis tras "dos mil ...").
_PATRON = re.compile(
    r"\(?\s*(\d{1,2})\s*\)?\s+de\s+"
    r"(enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|setiembre|octubre|noviembre|diciembre)"
    r"\s+de\s+[^\d]{0,40}?\(?\s*(\d{4})",
    re.IGNORECASE,
)


def parse_fecha_providencia_es(texto: str) -> Optional[date]:
    """Extrae la primera fecha de providencia de un texto en español. Acepta el
    día en dígitos ("8 de mayo de 2026") o en letras con el número entre
    paréntesis ("diez (10) de agosto de dos mil veintiséis (2026)"). Tolera
    saltos de línea. Devuelve None si no encuentra una fecha válida."""
    if not texto:
        return None
    normalizado = re.sub(r"\s+", " ", texto)
    for m in _PATRON.finditer(normalizado):
        dia = int(m.group(1))
        mes = _MESES[m.group(2).lower()]
        anio = int(m.group(3))
        try:
            return date(anio, mes, dia)
        except ValueError:
            continue  # p. ej. "32 de mayo": sigue buscando una fecha válida
    return None
```

- [ ] **Step 4: Correr el test y verificar que pasa**

Run: `.venv/Scripts/pytest tests/test_fecha_es.py -v`
Expected: PASS (7 tests).

- [ ] **Step 5: Commit**

```bash
git add core/fecha_es.py tests/test_fecha_es.py
git commit -m "feat(fecha): parser de fecha de providencia en español"
```

---

### Task 6: Extracción de fecha de providencia en Rama Judicial (+ dependencia cryptography)

**Files:**
- Modify: `core/scrapers/families/rama_judicial.py` (imports; `_parse`/construcción de `RawDocModel` ~413-423; nueva clase `resolve_unverified_document` y helper de PDF)
- Modify: `requirements.txt`
- Test: `tests/families/test_rama_judicial.py`

**Interfaces:**
- Consumes: `core.fecha_es.parse_fecha_providencia_es` (Task 5), `core.utils.is_radicado_title`.
- Produces: `ScrapRamaJudicial.resolve_unverified_document(doc, local_path, content_type)` fija `doc.f_providencia` (str "YYYY-MM-DD") desde la primera página del PDF; los documentos con título de radicado se marcan `title_unverified=True`.

- [ ] **Step 1: Escribir el test que falla**

En `tests/families/test_rama_judicial.py` agregar (usa monkeypatch del extractor de texto para no depender de un PDF real):

```python
from datetime import date

from core.scrapers.families import rama_judicial
from core.models import RawDocModel


def _raw(title):
    return RawDocModel(source="Rama Judicial", link={"url": "u", "method": "GET", "body": {"path": "uuid"}},
                       title=title, tipo="Sentencias", f_public="2026-08-10")


def test_resolve_llena_f_providencia_desde_pdf(monkeypatch, tmp_path):
    scraper = rama_judicial.ScrapRamaJudicial(dept_code="11", dept_name="Rama Judicial")
    monkeypatch.setattr(
        rama_judicial, "_extraer_texto_primera_pagina",
        lambda p: "Bogotá, diez (10) de agosto de dos mil veintiséis (2026)",
    )
    doc = _raw("T_11_11001_31_03_022_2019_00814_02")
    scraper.resolve_unverified_document(doc, tmp_path / "x.pdf", "application/pdf")
    assert doc.f_providencia == "2026-08-10"


def test_resolve_sin_fecha_deja_f_providencia_none(monkeypatch, tmp_path):
    scraper = rama_judicial.ScrapRamaJudicial(dept_code="11", dept_name="Rama Judicial")
    monkeypatch.setattr(rama_judicial, "_extraer_texto_primera_pagina", lambda p: "sin fecha")
    doc = _raw("T_11_11001_31_03_022_2019_00814_02")
    scraper.resolve_unverified_document(doc, tmp_path / "x.pdf", "application/pdf")
    assert doc.f_providencia is None


def test_resolve_ignora_error_de_lectura(monkeypatch, tmp_path):
    scraper = rama_judicial.ScrapRamaJudicial(dept_code="11", dept_name="Rama Judicial")
    def _boom(p):
        raise RuntimeError("pdf ilegible")
    monkeypatch.setattr(rama_judicial, "_extraer_texto_primera_pagina", _boom)
    doc = _raw("T_11_x")
    scraper.resolve_unverified_document(doc, tmp_path / "x.pdf", "application/pdf")
    assert doc.f_providencia is None
```

- [ ] **Step 2: Correr el test y verificar que falla**

Run: `.venv/Scripts/pytest tests/families/test_rama_judicial.py -k resolve -v`
Expected: FAIL (`AttributeError: _extraer_texto_primera_pagina` / método no implementado).

- [ ] **Step 3: Implementar el helper de PDF y el enganche**

En `core/scrapers/families/rama_judicial.py`, en los imports superiores agregar:

```python
from core.fecha_es import parse_fecha_providencia_es
```

Agregar a nivel de módulo (junto a los otros helpers):

```python
def _extraer_texto_primera_pagina(local_path) -> str:
    # Los PDFs de Rama Judicial vienen cifrados con AES (contraseña vacía);
    # pypdf los abre solo si 'cryptography' está instalado (ver requirements).
    from pypdf import PdfReader

    reader = PdfReader(str(local_path))
    if reader.is_encrypted:
        try:
            reader.decrypt("")
        except Exception:
            pass
    if not reader.pages:
        return ""
    return reader.pages[0].extract_text() or ""
```

Dentro de `class ScrapRamaJudicial`, agregar el método:

```python
    def resolve_unverified_document(self, doc, local_path, content_type) -> None:
        # Rama Judicial no expone la fecha de providencia en sus metadatos; se
        # extrae de la primera página del PDF. Solo se intenta para documentos
        # con título de radicado (providencias individuales); si no se puede
        # leer o parsear, f_providencia queda None y el nombre canónico usa el
        # respaldo (f_public). Nunca interrumpe la ingestión.
        if not is_radicado_title(doc.title):
            return
        try:
            texto = _extraer_texto_primera_pagina(local_path)
        except Exception as e:
            logger.warning("No se pudo leer la primera página de %s: %s", getattr(local_path, "name", local_path), e)
            return
        fecha = parse_fecha_providencia_es(texto)
        if fecha is not None:
            doc.f_providencia = fecha.strftime("%Y-%m-%d")
```

Asegurar el import de `is_radicado_title` en el archivo (agregar a la línea de import de `core.utils` si no está):

```python
from core.utils import is_radicado_title
```

En la construcción del `RawDocModel` (~línea 413-423), marcar los títulos de radicado para que el worker invoque el enganche. Agregar el argumento:

```python
                        docs.append(RawDocModel(
                            source=self.source,
                            link={"url": download_url, "method": "GET", "body": {"path": file_uuid}},
                            title=_normalize_title(name_no_ext, self._dept_code),
                            tipo=tipo,
                            especialidad=especialidad_raw,
                            seccion=despacho_raw,
                            f_public=fecha_p,
                            detalle=_extract_detalle(name_no_ext),
                            save_path=save_path,
                            title_unverified=is_radicado_title(_normalize_title(name_no_ext, self._dept_code)),
                        ))
```

- [ ] **Step 4: Agregar la dependencia**

En `requirements.txt`, agregar una línea:

```
cryptography>=3.1
```

- [ ] **Step 5: Instalar y correr los tests**

Run:
```bash
.venv/Scripts/pip install "cryptography>=3.1" -q && .venv/Scripts/pytest tests/families/test_rama_judicial.py -v
```
Expected: los 3 tests nuevos PASS; los existentes de Rama Judicial siguen PASS.

- [ ] **Step 6: Commit**

```bash
git add core/scrapers/families/rama_judicial.py requirements.txt tests/families/test_rama_judicial.py
git commit -m "feat(rama_judicial): extraer fecha de providencia del PDF (con respaldo) + cryptography"
```

---

### Task 7: Exponer `nombre` en la API y fijar el nombre en las descargas

**Files:**
- Modify: `api/schemas.py:68-91` (`DocumentOut`), `api/schemas.py:127-134` (`DocumentVersionOut`)
- Modify: `api/routers/documents.py` (list, single, patches, versions, download, download_version, preview)
- Test: `tests/test_api_documents.py`

**Interfaces:**
- Consumes: `core.naming.nombre_documento`, `nombre_version`, `nombre_archivo_documento`, `nombre_archivo_version`, `es_familia_con_actuaciones`; `repository.get_source_family_keys`.
- Produces: `DocumentOut.nombre: str`, `DocumentVersionOut.nombre: str`; `Content-Disposition` con el nombre canónico en las descargas.

- [ ] **Step 1: Escribir el test que falla**

En `tests/test_api_documents.py` agregar (ajustar el patrón de cliente/fixtures al que ya usa ese archivo):

```python
def test_document_out_incluye_nombre_con_version(client, db_session):
    # SAMAI (familia con actuaciones) + f_providencia + una republicación → nombre con fecha y _v2
    from core.db import repository
    repository.create_source_family(db_session, key="samai", display_name="SAMAI")
    source = repository.create_source(db_session, family_key="samai", name="Consejo de Estado", family_params={})
    from datetime import date
    doc = repository.insert_document(
        db_session, doc_id="apx-1", source_id=source.id, title="11001-03-28-000-2026-00300-00",
        storage_bucket="iurisync-test", storage_key="a.pdf", f_providencia=date(2026, 7, 31),
    )
    repository.archive_and_replace_document(db_session, doc.id, storage_bucket="iurisync-test", storage_key="b.pdf")

    resp = client.get(f"/documents/{doc.id}")
    assert resp.status_code == 200
    assert resp.json()["nombre"] == "11001-03-28-000-2026-00300-00_20260731_v2"
```

- [ ] **Step 2: Correr el test y verificar que falla**

Run: `.venv/Scripts/pytest tests/test_api_documents.py::test_document_out_incluye_nombre_con_version -v`
Expected: FAIL (`KeyError: 'nombre'` / campo ausente).

- [ ] **Step 3: Agregar `nombre` a los esquemas**

En `api/schemas.py`, en `DocumentOut` agregar `nombre: str` (después de `title`). En `DocumentVersionOut` agregar `nombre: str` (después de `id`/`document_id`).

- [ ] **Step 4: Poblar `nombre` y fijar el nombre en el router**

En `api/routers/documents.py`:

1. Importar los helpers y quitar la duplicación de `_CASE_TITLE_CHECKS`:

```python
from core.naming import (
    es_familia_con_actuaciones,
    nombre_archivo_documento,
    nombre_archivo_version,
    nombre_documento,
    nombre_version,
)
```

2. En `get_documents`, reemplazar el bloque `_CASE_TITLE_CHECKS = {...}` y el conteo por el uso de `es_familia_con_actuaciones` con los `family_keys` ya cargados, y poblar `nombre`:

```python
    family_keys = repository.get_source_family_keys(db, [d.source_id for d in items])
    case_titles_por_familia: dict[str, list[str]] = {}
    for d in items:
        fam = family_keys.get(d.source_id)
        if es_familia_con_actuaciones(fam, d.title):
            case_titles_por_familia.setdefault(fam, []).append(d.title)
    counts: dict[str, int] = {}
    for fam, titles in case_titles_por_familia.items():
        counts.update(repository.count_documents_by_title_within_family(db, titles, fam))
    for d in items:
        count = counts.get(d.title)
        d.case_document_count = count if count and count > 1 else None
        d.nombre = nombre_documento(d, family_keys.get(d.source_id))
```

3. Agregar un helper y usarlo en cada endpoint que devuelve un `DocumentOut` individual:

```python
def _poblar_nombre(db: Session, document: Document) -> Document:
    fam = repository.get_source_family_keys(db, [document.source_id]).get(document.source_id)
    document.nombre = nombre_documento(document, fam)
    return document
```

Llamarlo en `get_document` (antes de `return document`), en `patch_document_review_status` y en `patch_document_title` (antes de sus `return document`).

4. En `get_document_versions`, poblar el `nombre` de cada versión:

```python
@router.get("/documents/{document_id}/versions", response_model=list[DocumentVersionOut])
def get_document_versions(document_id: int, db: Session = Depends(get_db)):
    document = repository.get_document(db, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Documento no encontrado")
    fam = repository.get_source_family_keys(db, [document.source_id]).get(document.source_id)
    versions = repository.list_document_versions(db, document_id)
    for v in versions:
        v.nombre = nombre_version(document, v, fam)
    return versions
```

5. En `download_document`, fijar el `Content-Disposition`:

```python
@router.get("/documents/{document_id}/download")
def download_document(document_id: int, db: Session = Depends(get_db)):
    document = repository.get_document(db, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Documento no encontrado")
    fam = repository.get_source_family_keys(db, [document.source_id]).get(document.source_id)
    filename = _INVALID_FILENAME_CHARS.sub("-", nombre_archivo_documento(document, fam))
    disposition = f'attachment; filename="{filename}"'
    url = presigned_url(document.storage_bucket, document.storage_key, response_content_disposition=disposition)
    return RedirectResponse(url)
```

6. En `download_document_version`, fijar el nombre de la versión:

```python
@router.get("/documents/{document_id}/versions/{version_id}/download")
def download_document_version(document_id: int, version_id: int, db: Session = Depends(get_db)):
    version = repository.get_document_version(db, version_id)
    if version is None or version.document_id != document_id:
        raise HTTPException(status_code=404, detail="Versión no encontrada")
    document = repository.get_document(db, document_id)
    fam = repository.get_source_family_keys(db, [document.source_id]).get(document.source_id)
    filename = _INVALID_FILENAME_CHARS.sub("-", nombre_archivo_version(document, version, fam))
    disposition = f'attachment; filename="{filename}"'
    url = presigned_url(version.storage_bucket, version.storage_key, response_content_disposition=disposition)
    return {"url": url}
```

7. En `_preview_content_disposition`, usar el nombre canónico como base (recibe también el family_key):

```python
def _preview_content_disposition(document: Document, family_key) -> str:
    safe = _INVALID_FILENAME_CHARS.sub("-", nombre_documento(document, family_key))
    return f'inline; filename="{safe}.pdf"'
```

Y en `preview_document`, calcular `fam` y pasarlo:

```python
    fam = repository.get_source_family_keys(db, [document.source_id]).get(document.source_id)
    disposition = _preview_content_disposition(document, fam)
```

- [ ] **Step 5: Correr los tests del API y verificar que pasan**

Run: `.venv/Scripts/pytest tests/test_api_documents.py -v`
Expected: el test nuevo PASS y los existentes siguen PASS (ajustar cualquier test que asumía la ausencia de `nombre`).

- [ ] **Step 6: Commit**

```bash
git add api/schemas.py api/routers/documents.py tests/test_api_documents.py
git commit -m "feat(api): exponer nombre canónico y fijarlo en descargas/preview"
```

---

### Task 8: ZIP masivo con nombre canónico y desambiguación de colisiones

**Files:**
- Modify: `worker/tasks.py:532-559` (armado del ZIP)
- Create (helper puro): en `worker/tasks.py` una función `_nombres_zip(...)`
- Test: `tests/test_worker_zip_names.py`

**Interfaces:**
- Consumes: `core.naming.nombre_archivo_documento`; `repository.get_source_family_keys`.
- Produces: cada entrada del ZIP usa el nombre canónico con extensión; nombres repetidos se desambiguan con ` (2)`, ` (3)`…

- [ ] **Step 1: Escribir el test que falla**

Crear `tests/test_worker_zip_names.py`:

```python
from datetime import date
from types import SimpleNamespace

from worker.tasks import _nombres_zip


def _doc(title, storage_key, source_id=1, f_providencia=None, version_no=1):
    return SimpleNamespace(title=title, storage_key=storage_key, source_id=source_id,
                           f_providencia=f_providencia, f_public=None, version_no=version_no)


def test_nombres_zip_desambigua_colisiones():
    docs = [_doc("T-1", "a.pdf"), _doc("T-1", "b.pdf")]
    fam = {1: "constitucional"}
    assert _nombres_zip(docs, fam) == ["T-1.pdf", "T-1 (2).pdf"]


def test_nombres_zip_caso_lleva_fecha():
    docs = [_doc("11001", "a.pdf", f_providencia=date(2026, 7, 31))]
    fam = {1: "samai"}
    assert _nombres_zip(docs, fam) == ["11001_20260731.pdf"]
```

- [ ] **Step 2: Correr el test y verificar que falla**

Run: `.venv/Scripts/pytest tests/test_worker_zip_names.py -v`
Expected: FAIL (`ImportError: cannot import name '_nombres_zip'`).

- [ ] **Step 3: Implementar el helper y usarlo en el ZIP**

En `worker/tasks.py`, agregar el import y el helper:

```python
from core.naming import nombre_archivo_documento
from pathlib import PurePosixPath  # si no está ya importado


def _nombres_zip(documents, family_keys) -> list[str]:
    """Nombre de cada entrada del ZIP = nombre canónico + extensión. Desambigua
    colisiones agregando ' (2)', ' (3)'… antes de la extensión, para no
    sobrescribir un archivo con otro dentro del mismo ZIP."""
    usados: dict[str, int] = {}
    nombres: list[str] = []
    for d in documents:
        base = nombre_archivo_documento(d, family_keys.get(d.source_id))
        if base not in usados:
            usados[base] = 1
            nombres.append(base)
        else:
            usados[base] += 1
            p = PurePosixPath(base)
            nombres.append(f"{p.stem} ({usados[base]}){p.suffix}")
    return nombres
```

En la función que arma el ZIP (`build_bulk_download_zip`), antes del `with zipfile.ZipFile(...)`, calcular los nombres:

```python
            family_keys = repository.get_source_family_keys(db, [d.source_id for d in documents])
            arcnames = _nombres_zip(documents, family_keys)
```

Dentro del bucle `for document in documents:`, cambiar a enumerar y usar el arcname canónico (la ruta local temporal sigue usando `storage_key` para evitar choques en disco):

```python
            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                for document, arcname in zip(documents, arcnames):
                    if not is_safe_storage_key(document.storage_key):
                        logger.warning("Clave de almacenamiento no segura, se omite de la descarga masiva: %s", document.storage_key)
                        failed_count += 1
                        continue
                    local_path = downloads_dir / document.storage_key
                    local_path.parent.mkdir(parents=True, exist_ok=True)
                    try:
                        download_file(document.storage_bucket, document.storage_key, local_path)
                        zf.write(local_path, arcname=arcname)
                        downloaded_count += 1
                    except Exception as exc:
                        logger.warning("No se pudo incluir %s en la descarga masiva: %s", document.storage_key, exc)
                        failed_count += 1
                    finally:
                        local_path.unlink(missing_ok=True)
```

- [ ] **Step 4: Correr el test y verificar que pasa**

Run: `.venv/Scripts/pytest tests/test_worker_zip_names.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add worker/tasks.py tests/test_worker_zip_names.py
git commit -m "feat(zip): entradas del ZIP con nombre canónico y desambiguación"
```

---

### Task 9: Backfill de `version_no` para lo existente

**Files:**
- Create: `core/backfill_version_no.py`
- Test: `tests/test_backfill_version_no.py`

**Interfaces:**
- Consumes: modelos `Document`, `DocumentVersion` (Task 1).
- Produces: `asignar_version_no(db) -> int` (devuelve cuántos documentos actualizó); función `main()` para correr como script.

- [ ] **Step 1: Escribir el test que falla**

Crear `tests/test_backfill_version_no.py`:

```python
from datetime import datetime, timezone, timedelta

from core.db import repository
from core.db.models import DocumentVersion
from core.backfill_version_no import asignar_version_no


def test_backfill_numera_versiones_por_antiguedad(db_session):
    repository.create_source_family(db_session, key="samai", display_name="SAMAI")
    source = repository.create_source(db_session, family_key="samai", name="Consejo de Estado", family_params={})
    doc = repository.insert_document(
        db_session, doc_id="bf-1", source_id=source.id, title="rad-1",
        storage_bucket="iurisync-test", storage_key="v3.pdf",
    )
    ahora = datetime.now(timezone.utc)
    # Dos versiones archivadas, la más antigua primero (superseded_at menor).
    db_session.add(DocumentVersion(document_id=doc.id, storage_bucket="b", storage_key="v1.pdf",
                                   downloaded_at=ahora, superseded_at=ahora - timedelta(days=2)))
    db_session.add(DocumentVersion(document_id=doc.id, storage_bucket="b", storage_key="v2.pdf",
                                   downloaded_at=ahora, superseded_at=ahora - timedelta(days=1)))
    db_session.commit()

    actualizados = asignar_version_no(db_session)

    versions = repository.list_document_versions(db_session, doc.id)
    por_key = {v.storage_key: v.version_no for v in versions}
    assert por_key == {"v1.pdf": 1, "v2.pdf": 2}
    assert repository.get_document(db_session, doc.id).version_no == 3
    assert actualizados == 1


def test_backfill_documento_sin_versiones_queda_en_1(db_session):
    repository.create_source_family(db_session, key="constitucional", display_name="Corte Constitucional")
    source = repository.create_source(db_session, family_key="constitucional", name="Corte Constitucional", family_params={})
    doc = repository.insert_document(
        db_session, doc_id="bf-2", source_id=source.id, title="T-1",
        storage_bucket="iurisync-test", storage_key="a.pdf",
    )
    asignar_version_no(db_session)
    assert repository.get_document(db_session, doc.id).version_no == 1
```

- [ ] **Step 2: Correr el test y verificar que falla**

Run: `.venv/Scripts/pytest tests/test_backfill_version_no.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'core.backfill_version_no'`).

- [ ] **Step 3: Implementar `core/backfill_version_no.py`**

```python
"""Corrida única: rellena documents.version_no y document_versions.version_no
en lo ya guardado, según el orden real de las versiones (la más antigua = 1;
el documento vigente = k+1). Solo base de datos; no toca archivos."""
import logging

from sqlalchemy import select

from core.db.models import Document, DocumentVersion
from core.db.session import SessionLocal

logger = logging.getLogger(__name__)


def asignar_version_no(db) -> int:
    actualizados = 0
    documentos = db.scalars(select(Document)).all()
    for doc in documentos:
        versiones = db.scalars(
            select(DocumentVersion)
            .where(DocumentVersion.document_id == doc.id)
            .order_by(DocumentVersion.superseded_at.asc())
        ).all()
        if not versiones:
            doc.version_no = 1
            continue
        for i, v in enumerate(versiones, start=1):
            v.version_no = i
        doc.version_no = len(versiones) + 1
        actualizados += 1
    db.commit()
    return actualizados


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    db = SessionLocal()
    try:
        n = asignar_version_no(db)
        logger.info("version_no asignado; documentos con versiones actualizados: %s", n)
    finally:
        db.close()


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Correr el test y verificar que pasa**

Run: `.venv/Scripts/pytest tests/test_backfill_version_no.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add core/backfill_version_no.py tests/test_backfill_version_no.py
git commit -m "feat(backfill): asignar version_no a documentos y versiones existentes"
```

---

### Task 10: Frontend — mostrar y descargar con el `nombre` canónico

**Files:**
- Modify: `frontend/src/api/types.ts:56-79` (`Document`), `frontend/src/api/types.ts:139-146` (`DocumentVersion`)
- Modify: `frontend/src/api/documents.ts:109-131` (builders de nombre de archivo)
- Modify: `frontend/src/pages/DocumentsPage.tsx`, `frontend/src/components/DocumentPreviewDialog.tsx` (mostrar `nombre` en vez de `title`)
- Test: `frontend/src/api/documents.test.ts`, `frontend/src/pages/DocumentsPage.test.tsx`, `frontend/src/components/DocumentPreviewDialog.test.tsx`

**Interfaces:**
- Consumes: `Document.nombre`, `DocumentVersion.nombre` (Task 7).
- Produces: nombres de archivo y nombre visible basados en `nombre`.

- [ ] **Step 1: Escribir el test que falla**

En `frontend/src/api/documents.test.ts` agregar:

```ts
import { buildDownloadFilename, buildVersionDownloadFilename } from "./documents";

it("usa el nombre canónico para el archivo de descarga", () => {
  const doc = { nombre: "11001_20260731_v2", storage_key: "x/y.pdf", content_type: "application/pdf" } as any;
  expect(buildDownloadFilename(doc)).toBe("11001_20260731_v2.pdf");
});

it("usa el nombre canónico de la versión", () => {
  const version = { nombre: "11001_20260731_v1", content_type: "application/pdf", id: 5 } as any;
  expect(buildVersionDownloadFilename(version)).toBe("11001_20260731_v1.pdf");
});
```

- [ ] **Step 2: Correr el test y verificar que falla**

Run: `cd frontend && npm test -- --run src/api/documents.test.ts`
Expected: FAIL (tipos/firmas no coinciden; `nombre` inexistente).

- [ ] **Step 3: Actualizar tipos y builders**

En `frontend/src/api/types.ts`, agregar `nombre: string;` a `interface Document` (tras `title`) y a `interface DocumentVersion` (tras `document_id`).

En `frontend/src/api/documents.ts`:

```ts
export function buildDownloadFilename(document: Document): string {
  const ext = extensionFromStorageKey(document.storage_key) ?? (document.content_type ? CONTENT_TYPE_EXTENSIONS[document.content_type] : undefined);
  const sanitized = sanitizeFilename(document.nombre);
  return ext ? `${sanitized}.${ext}` : sanitized;
}

export function buildPreviewDownloadFilename(document: Document): string {
  return `${sanitizeFilename(document.nombre)}.pdf`;
}

// Firma nueva: la versión ya trae su propio nombre canónico (con "_v{n}").
export function buildVersionDownloadFilename(version: DocumentVersion): string {
  const ext = version.content_type ? CONTENT_TYPE_EXTENSIONS[version.content_type] : undefined;
  const sanitized = sanitizeFilename(version.nombre);
  return ext ? `${sanitized}.${ext}` : sanitized;
}
```

Actualizar cualquier llamador de `buildVersionDownloadFilename` (buscar en `frontend/src`) para pasar solo `version` (ya no `documentTitle, version`).

- [ ] **Step 4: Mostrar `nombre` en la interfaz**

En `frontend/src/pages/DocumentsPage.tsx` y `frontend/src/components/DocumentPreviewDialog.tsx`, reemplazar la lectura de `document.title` **para presentación** (celda de nombre en la tabla, título del diálogo, encabezado de la lista de versiones) por `document.nombre`. Dejar intacto el flujo de edición manual de título (`updateDocumentTitle`), que sigue editando la base (`title`).

- [ ] **Step 5: Actualizar los tests de UI y correr toda la suite del frontend**

Ajustar `DocumentsPage.test.tsx` y `DocumentPreviewDialog.test.tsx` para incluir `nombre` en los documentos de prueba y afirmar que se muestra el `nombre`.

Run: `cd frontend && npm test -- --run`
Expected: toda la suite del frontend PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/api/types.ts frontend/src/api/documents.ts frontend/src/pages/DocumentsPage.tsx frontend/src/components/DocumentPreviewDialog.tsx frontend/src/api/documents.test.ts frontend/src/pages/DocumentsPage.test.tsx frontend/src/components/DocumentPreviewDialog.test.tsx
git commit -m "feat(frontend): mostrar y descargar con el nombre canónico"
```

---

### Task 11: Verificación integral y puesta en marcha

**Files:**
- No hay cambios de código; verificación de extremo a extremo.

- [ ] **Step 1: Correr las suites backend afectadas (dirigidas)**

Run:
```bash
.venv/Scripts/pytest tests/test_naming.py tests/test_fecha_es.py tests/test_repository.py tests/families/test_rama_judicial.py tests/test_api_documents.py tests/test_worker_zip_names.py tests/test_backfill_version_no.py -v
```
Expected: todo PASS (ignorar el fallo pre-existente de `test_migrations.py`, que no se corre aquí).

- [ ] **Step 2: Correr la suite del frontend**

Run: `cd frontend && npm test -- --run`
Expected: PASS.

- [ ] **Step 3: Prueba end-to-end con la app (skill run-iurisync)**

Con el entorno levantado, lanzar un run real de una fuente con actuaciones (p. ej. `Consejo de Estado`) y una sin actuaciones, y verificar en la UI que el nombre mostrado y el archivo descargado coinciden y llevan los sufijos correctos. Descargar una versión y un ZIP para confirmar nombres.

- [ ] **Step 4: Notas de despliegue (para el merge y la oficina)**

Registrar en el PR:
- Ejecutar la migración (`alembic upgrade head`) — incluida en el arranque del contenedor.
- Nueva dependencia `cryptography>=3.1` (ya en `requirements.txt`; se hornea en la imagen GHCR).
- Tras `docker compose pull/up`, correr una vez el backfill:
  ```
  docker compose run --rm api python -m core.backfill_version_no
  ```

- [ ] **Step 5: Commit (si hubo ajustes de verificación)**

```bash
git add -A
git commit -m "test: verificación integral del nombre canónico"
```

---

## Self-Review

**Cobertura del spec:**
- Receta del nombre → Tasks 3, 4. ✓
- Nombre idéntico en app/descarga/versión/ZIP/preview → Tasks 7, 8, 10. ✓
- `title` conservado como base + agrupación intacta → Tasks 3, 7 (reutiliza detección, no muta `title`). ✓
- Numeración de versiones persistida (solo si >1) → Tasks 1, 2, 3. ✓
- Fecha de providencia en Rama Judicial desde el PDF + respaldo → Tasks 5, 6. ✓
- Detección "con actuaciones" por familia → Task 3. ✓
- Backfill solo BD → Task 9. ✓
- Dependencia `cryptography` → Task 6. ✓
- Manejo de colisiones en ZIP → Task 8. ✓
- Casos límite (sin fecha → sin sufijo; PDF ilegible → respaldo) → Tasks 3, 6. ✓
- Frontend usa `nombre` → Task 10. ✓
- Puesta en marcha (migración, dependencia, backfill) → Task 11. ✓

**Consistencia de tipos:** los nombres `construir_nombre`, `es_familia_con_actuaciones`, `nombre_documento`, `nombre_version`, `nombre_archivo_documento`, `nombre_archivo_version`, `parse_fecha_providencia_es`, `asignar_version_no`, `_nombres_zip`, `buildVersionDownloadFilename(version)` se usan de forma coherente entre tareas.

**Sin placeholders:** cada paso trae código y comando reales.
