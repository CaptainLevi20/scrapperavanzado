# Documentos: filtros anidados — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Agregar Sección, Especialidad/Proceso y Magistrado como filtros nuevos en el apartado Documentos, encadenados en cascada después de Fuente → Tipo (Fuente → Tipo → Sección → Especialidad → Magistrado), igual que Tipo ya se acota hoy según la Fuente elegida.

**Architecture:** Tres funciones nuevas de "valores distintos" en `core/db/repository.py` (una por campo, cada una scoped por los filtros que la preceden en la cascada) expuestas como tres endpoints `GET` nuevos en `api/routers/documents.py`, replicando exactamente el patrón ya existente de `list_distinct_document_tipos` + `GET /documents/tipos`. `list_documents`/`GET /documents` ganan `seccion`, `especialidad`, `magistrado` como filtros opcionales adicionales. El frontend agrega tres `NativeSelect` nuevos en `DocumentsPage.tsx`, cada uno con su propio `useQuery` scoped y un `useEffect` que resetea su valor si deja de ser válido al cambiar un filtro de nivel superior — mismo patrón que el `useEffect` que ya existe para `tipo`.

**Tech Stack:** FastAPI + SQLAlchemy (backend), React + TanStack Query (frontend), pytest / vitest.

## Global Constraints

- Orden de cascada exacto: Fuente → Tipo → Sección → Especialidad → Magistrado (spec, sección "Alcance").
- Sin comportamiento por defecto: sin ningún filtro nuevo seleccionado, `GET /documents` se comporta exactamente igual que hoy.
- No se toca el filtro de Tipo existente, ni Fecha providencia, ni ninguna lógica de agrupamiento de expedientes (`title_exact`/`collapse_case_families`).
- No se agrega lógica de combinación AND/OR ni filtros guardados — fuera de alcance (spec).

---

### Task 1: Repositorio — valores distintos de Sección, Especialidad y Magistrado

**Files:**
- Modify: `core/db/repository.py` (junto a `list_distinct_document_tipos`, líneas 369-374)
- Test: `tests/test_repository.py` (junto a los tests de `list_distinct_document_tipos`, líneas 298-341)

**Interfaces:**
- Produces:
  - `repository.list_distinct_document_secciones(db, source_id: Optional[int] = None, tipo: Optional[str] = None) -> list[str]`
  - `repository.list_distinct_document_especialidades(db, source_id: Optional[int] = None, tipo: Optional[str] = None, seccion: Optional[str] = None) -> list[str]`
  - `repository.list_distinct_document_magistrados(db, source_id: Optional[int] = None, tipo: Optional[str] = None, seccion: Optional[str] = None, especialidad: Optional[str] = None) -> list[str]`

- [ ] **Step 1: Escribir los tests que fallan**

En `tests/test_repository.py`, justo después de `test_list_distinct_document_tipos_scoped_to_a_source` (línea 341):

```python
def test_list_distinct_document_secciones_scoped_to_tipo(db_session):
    from core.db import repository

    repository.create_source_family(db_session, key="constitucional", display_name="Corte Constitucional")
    source = repository.create_source(db_session, family_key="constitucional", name="Corte Constitucional", family_params={})
    repository.insert_document(
        db_session, doc_id="doc-1", source_id=source.id, title="A", tipo="Sentencia", seccion="SECCION PRIMERA",
        storage_bucket="iurisync-test", storage_key="a.pdf",
    )
    repository.insert_document(
        db_session, doc_id="doc-2", source_id=source.id, title="B", tipo="Auto", seccion="SECCION SEGUNDA",
        storage_bucket="iurisync-test", storage_key="b.pdf",
    )
    repository.insert_document(
        db_session, doc_id="doc-3", source_id=source.id, title="C", tipo=None, seccion=None,
        storage_bucket="iurisync-test", storage_key="c.pdf",
    )

    assert repository.list_distinct_document_secciones(db_session) == ["SECCION PRIMERA", "SECCION SEGUNDA"]
    assert repository.list_distinct_document_secciones(db_session, source_id=source.id, tipo="Sentencia") == ["SECCION PRIMERA"]
    assert repository.list_distinct_document_secciones(db_session, tipo="Auto") == ["SECCION SEGUNDA"]


def test_list_distinct_document_especialidades_scoped_to_seccion(db_session):
    from core.db import repository

    repository.create_source_family(db_session, key="constitucional", display_name="Corte Constitucional")
    source = repository.create_source(db_session, family_key="constitucional", name="Corte Constitucional", family_params={})
    repository.insert_document(
        db_session, doc_id="doc-1", source_id=source.id, title="A", seccion="SECCION PRIMERA", especialidad="Nulidad",
        storage_bucket="iurisync-test", storage_key="a.pdf",
    )
    repository.insert_document(
        db_session, doc_id="doc-2", source_id=source.id, title="B", seccion="SECCION SEGUNDA", especialidad="Conciliación",
        storage_bucket="iurisync-test", storage_key="b.pdf",
    )

    assert repository.list_distinct_document_especialidades(db_session) == ["Conciliación", "Nulidad"]
    assert repository.list_distinct_document_especialidades(db_session, seccion="SECCION PRIMERA") == ["Nulidad"]
    assert repository.list_distinct_document_especialidades(db_session, seccion="SECCION SEGUNDA") == ["Conciliación"]


def test_list_distinct_document_magistrados_scoped_to_especialidad(db_session):
    from core.db import repository

    repository.create_source_family(db_session, key="constitucional", display_name="Corte Constitucional")
    source = repository.create_source(db_session, family_key="constitucional", name="Corte Constitucional", family_params={})
    repository.insert_document(
        db_session, doc_id="doc-1", source_id=source.id, title="A", especialidad="Nulidad", magistrado="Ana Pérez",
        storage_bucket="iurisync-test", storage_key="a.pdf",
    )
    repository.insert_document(
        db_session, doc_id="doc-2", source_id=source.id, title="B", especialidad="Conciliación", magistrado="Luis Gómez",
        storage_bucket="iurisync-test", storage_key="b.pdf",
    )

    assert repository.list_distinct_document_magistrados(db_session) == ["Ana Pérez", "Luis Gómez"]
    assert repository.list_distinct_document_magistrados(db_session, especialidad="Nulidad") == ["Ana Pérez"]
    assert repository.list_distinct_document_magistrados(db_session, especialidad="Conciliación") == ["Luis Gómez"]
```

- [ ] **Step 2: Correr los tests y confirmar que fallan**

Run: `.venv/Scripts/pytest tests/test_repository.py -k "secciones_scoped_to_tipo or especialidades_scoped_to_seccion or magistrados_scoped_to_especialidad" -v`
Expected: FAIL con `AttributeError: module 'core.db.repository' has no attribute 'list_distinct_document_secciones'` (y equivalentes para las otras dos).

- [ ] **Step 3: Implementar las tres funciones**

En `core/db/repository.py`, justo después de `list_distinct_document_tipos` (línea 374) y antes de `def list_documents(` (línea 377):

```python
def list_distinct_document_secciones(
    db: Session, source_id: Optional[int] = None, tipo: Optional[str] = None
) -> list[str]:
    stmt = select(Document.seccion).distinct().where(Document.seccion.is_not(None))
    if source_id is not None:
        stmt = stmt.where(Document.source_id == source_id)
    if tipo is not None:
        stmt = stmt.where(Document.tipo == tipo)
    stmt = stmt.order_by(Document.seccion)
    return list(db.scalars(stmt).all())


def list_distinct_document_especialidades(
    db: Session,
    source_id: Optional[int] = None,
    tipo: Optional[str] = None,
    seccion: Optional[str] = None,
) -> list[str]:
    stmt = select(Document.especialidad).distinct().where(Document.especialidad.is_not(None))
    if source_id is not None:
        stmt = stmt.where(Document.source_id == source_id)
    if tipo is not None:
        stmt = stmt.where(Document.tipo == tipo)
    if seccion is not None:
        stmt = stmt.where(Document.seccion == seccion)
    stmt = stmt.order_by(Document.especialidad)
    return list(db.scalars(stmt).all())


def list_distinct_document_magistrados(
    db: Session,
    source_id: Optional[int] = None,
    tipo: Optional[str] = None,
    seccion: Optional[str] = None,
    especialidad: Optional[str] = None,
) -> list[str]:
    stmt = select(Document.magistrado).distinct().where(Document.magistrado.is_not(None))
    if source_id is not None:
        stmt = stmt.where(Document.source_id == source_id)
    if tipo is not None:
        stmt = stmt.where(Document.tipo == tipo)
    if seccion is not None:
        stmt = stmt.where(Document.seccion == seccion)
    if especialidad is not None:
        stmt = stmt.where(Document.especialidad == especialidad)
    stmt = stmt.order_by(Document.magistrado)
    return list(db.scalars(stmt).all())
```

- [ ] **Step 4: Correr los tests y confirmar que pasan**

Run: `.venv/Scripts/pytest tests/test_repository.py -k "secciones_scoped_to_tipo or especialidades_scoped_to_seccion or magistrados_scoped_to_especialidad" -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add core/db/repository.py tests/test_repository.py
git commit -m "feat: agrega valores distintos de seccion/especialidad/magistrado al repositorio"
```

---

### Task 2: API — endpoints de opciones para Sección, Especialidad y Magistrado

**Files:**
- Modify: `api/routers/documents.py` (junto a `get_document_tipos`, líneas 111-113)
- Test: `tests/test_api_documents.py` (junto a los tests de `/documents/tipos`, líneas 334-372)

**Interfaces:**
- Consumes: las tres funciones de `repository.py` de la Task 1.
- Produces: rutas `GET /documents/secciones`, `GET /documents/especialidades`, `GET /documents/magistrados`, cada una `response_model=list[str]`.

- [ ] **Step 1: Escribir los tests que fallan**

En `tests/test_api_documents.py`, justo después de `test_get_document_tipos_scoped_to_a_source` (línea 372):

```python
def test_get_document_secciones_scoped_to_tipo(api_client, auth_header, db_session):
    from core.db import repository

    repository.create_source_family(db_session, key="constitucional", display_name="Corte Constitucional")
    source = repository.create_source(db_session, family_key="constitucional", name="Corte Constitucional", family_params={})
    repository.insert_document(
        db_session, doc_id="doc-1", source_id=source.id, title="A", tipo="Sentencia", seccion="SECCION PRIMERA",
        storage_bucket="iurisync-test", storage_key="a.pdf",
    )
    repository.insert_document(
        db_session, doc_id="doc-2", source_id=source.id, title="B", tipo="Auto", seccion="SECCION SEGUNDA",
        storage_bucket="iurisync-test", storage_key="b.pdf",
    )

    response = api_client.get(f"/documents/secciones?tipo=Sentencia", headers=auth_header)

    assert response.status_code == 200
    assert response.json() == ["SECCION PRIMERA"]


def test_get_document_especialidades_scoped_to_seccion(api_client, auth_header, db_session):
    from core.db import repository

    repository.create_source_family(db_session, key="constitucional", display_name="Corte Constitucional")
    source = repository.create_source(db_session, family_key="constitucional", name="Corte Constitucional", family_params={})
    repository.insert_document(
        db_session, doc_id="doc-1", source_id=source.id, title="A", seccion="SECCION PRIMERA", especialidad="Nulidad",
        storage_bucket="iurisync-test", storage_key="a.pdf",
    )
    repository.insert_document(
        db_session, doc_id="doc-2", source_id=source.id, title="B", seccion="SECCION SEGUNDA", especialidad="Conciliación",
        storage_bucket="iurisync-test", storage_key="b.pdf",
    )

    response = api_client.get("/documents/especialidades?seccion=SECCION+PRIMERA", headers=auth_header)

    assert response.status_code == 200
    assert response.json() == ["Nulidad"]


def test_get_document_magistrados_scoped_to_especialidad(api_client, auth_header, db_session):
    from core.db import repository

    repository.create_source_family(db_session, key="constitucional", display_name="Corte Constitucional")
    source = repository.create_source(db_session, family_key="constitucional", name="Corte Constitucional", family_params={})
    repository.insert_document(
        db_session, doc_id="doc-1", source_id=source.id, title="A", especialidad="Nulidad", magistrado="Ana Pérez",
        storage_bucket="iurisync-test", storage_key="a.pdf",
    )
    repository.insert_document(
        db_session, doc_id="doc-2", source_id=source.id, title="B", especialidad="Conciliación", magistrado="Luis Gómez",
        storage_bucket="iurisync-test", storage_key="b.pdf",
    )

    response = api_client.get("/documents/magistrados?especialidad=Nulidad", headers=auth_header)

    assert response.status_code == 200
    assert response.json() == ["Ana Pérez"]
```

- [ ] **Step 2: Correr los tests y confirmar que fallan**

Run: `.venv/Scripts/pytest tests/test_api_documents.py -k "secciones_scoped_to_tipo or especialidades_scoped_to_seccion or magistrados_scoped_to_especialidad" -v`
Expected: FAIL con `404 Not Found` (las rutas no existen todavía) — el assert de `status_code == 200` falla.

- [ ] **Step 3: Implementar los tres endpoints**

En `api/routers/documents.py`, justo después de `get_document_tipos` (línea 113):

```python
@router.get("/documents/secciones", response_model=list[str])
def get_document_secciones(
    source_id: Optional[int] = None, tipo: Optional[str] = None, db: Session = Depends(get_db)
):
    return repository.list_distinct_document_secciones(db, source_id=source_id, tipo=tipo)


@router.get("/documents/especialidades", response_model=list[str])
def get_document_especialidades(
    source_id: Optional[int] = None,
    tipo: Optional[str] = None,
    seccion: Optional[str] = None,
    db: Session = Depends(get_db),
):
    return repository.list_distinct_document_especialidades(
        db, source_id=source_id, tipo=tipo, seccion=seccion
    )


@router.get("/documents/magistrados", response_model=list[str])
def get_document_magistrados(
    source_id: Optional[int] = None,
    tipo: Optional[str] = None,
    seccion: Optional[str] = None,
    especialidad: Optional[str] = None,
    db: Session = Depends(get_db),
):
    return repository.list_distinct_document_magistrados(
        db, source_id=source_id, tipo=tipo, seccion=seccion, especialidad=especialidad
    )
```

- [ ] **Step 4: Correr los tests y confirmar que pasan**

Run: `.venv/Scripts/pytest tests/test_api_documents.py -k "secciones_scoped_to_tipo or especialidades_scoped_to_seccion or magistrados_scoped_to_especialidad" -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add api/routers/documents.py tests/test_api_documents.py
git commit -m "feat: agrega endpoints de opciones para seccion/especialidad/magistrado"
```

---

### Task 3: Filtrar `GET /documents` por Sección, Especialidad y Magistrado

**Files:**
- Modify: `core/db/repository.py` (`list_documents`, líneas 377-418)
- Modify: `api/routers/documents.py` (`get_documents`, líneas 53-84)
- Test: `tests/test_repository.py`
- Test: `tests/test_api_documents.py`

**Interfaces:**
- Produces: `repository.list_documents(..., seccion: Optional[str] = None, especialidad: Optional[str] = None, magistrado: Optional[str] = None)`; `GET /documents` gana los mismos tres query params opcionales.

- [ ] **Step 1: Escribir el test de repositorio que falla**

En `tests/test_repository.py`, justo después de `test_list_distinct_document_magistrados_scoped_to_especialidad` (agregado en la Task 1):

```python
def test_list_documents_filters_by_seccion_especialidad_magistrado(db_session):
    from core.db import repository

    repository.create_source_family(db_session, key="constitucional", display_name="Corte Constitucional")
    source = repository.create_source(db_session, family_key="constitucional", name="Corte Constitucional", family_params={})
    match = repository.insert_document(
        db_session, doc_id="doc-1", source_id=source.id, title="Coincide",
        seccion="SECCION PRIMERA", especialidad="Nulidad", magistrado="Ana Pérez",
        storage_bucket="iurisync-test", storage_key="a.pdf",
    )
    repository.insert_document(
        db_session, doc_id="doc-2", source_id=source.id, title="No coincide",
        seccion="SECCION SEGUNDA", especialidad="Conciliación", magistrado="Luis Gómez",
        storage_bucket="iurisync-test", storage_key="b.pdf",
    )

    items, total = repository.list_documents(
        db_session, seccion="SECCION PRIMERA", especialidad="Nulidad", magistrado="Ana Pérez"
    )

    assert total == 1
    assert items[0].id == match.id
```

- [ ] **Step 2: Correr el test y confirmar que falla**

Run: `.venv/Scripts/pytest tests/test_repository.py -k "filters_by_seccion_especialidad_magistrado" -v`
Expected: FAIL con `TypeError: list_documents() got an unexpected keyword argument 'seccion'`

- [ ] **Step 3: Agregar los filtros a `list_documents`**

En `core/db/repository.py`, la firma de `list_documents` (línea 377) gana tres parámetros nuevos, y el cuerpo (después del `if tipo is not None:` en línea 399) tres `if` nuevos:

```python
def list_documents(
    db: Session,
    source_id: Optional[int] = None,
    family_key: Optional[str] = None,
    tipo: Optional[str] = None,
    seccion: Optional[str] = None,
    especialidad: Optional[str] = None,
    magistrado: Optional[str] = None,
    review_status: Optional[str] = None,
    f_public_from: Optional[date] = None,
    f_public_to: Optional[date] = None,
    downloaded_from: Optional[date] = None,
    downloaded_to: Optional[date] = None,
    title_contains: Optional[str] = None,
    title_exact: Optional[str] = None,
    collapse_case_families: bool = False,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[Document], int]:
    stmt = select(Document)
    if source_id is not None:
        stmt = stmt.where(Document.source_id == source_id)
    if family_key is not None:
        stmt = stmt.join(Source, Source.id == Document.source_id).where(Source.family_key == family_key)
    if tipo is not None:
        stmt = stmt.where(Document.tipo == tipo)
    if seccion is not None:
        stmt = stmt.where(Document.seccion == seccion)
    if especialidad is not None:
        stmt = stmt.where(Document.especialidad == especialidad)
    if magistrado is not None:
        stmt = stmt.where(Document.magistrado == magistrado)
    if review_status is not None:
```

(El resto de la función, desde `if review_status is not None:` en adelante, no cambia — solo se insertan las tres líneas `if seccion/especialidad/magistrado` entre el `if tipo` existente y el `if review_status` existente.)

- [ ] **Step 4: Correr el test de repositorio y confirmar que pasa**

Run: `.venv/Scripts/pytest tests/test_repository.py -k "filters_by_seccion_especialidad_magistrado" -v`
Expected: PASS

- [ ] **Step 5: Escribir el test de API que falla**

En `tests/test_api_documents.py`, junto a los tests agregados en la Task 2:

```python
def test_get_documents_filters_by_seccion_especialidad_magistrado(api_client, auth_header, db_session):
    from core.db import repository

    repository.create_source_family(db_session, key="constitucional", display_name="Corte Constitucional")
    source = repository.create_source(db_session, family_key="constitucional", name="Corte Constitucional", family_params={})
    repository.insert_document(
        db_session, doc_id="doc-1", source_id=source.id, title="Coincide",
        seccion="SECCION PRIMERA", especialidad="Nulidad", magistrado="Ana Pérez",
        storage_bucket="iurisync-test", storage_key="a.pdf",
    )
    repository.insert_document(
        db_session, doc_id="doc-2", source_id=source.id, title="No coincide",
        seccion="SECCION SEGUNDA", especialidad="Conciliación", magistrado="Luis Gómez",
        storage_bucket="iurisync-test", storage_key="b.pdf",
    )

    response = api_client.get(
        "/documents?seccion=SECCION+PRIMERA&especialidad=Nulidad&magistrado=Ana+P%C3%A9rez",
        headers=auth_header,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["title"] == "Coincide"
```

- [ ] **Step 6: Correr el test y confirmar que falla**

Run: `.venv/Scripts/pytest tests/test_api_documents.py -k "filters_by_seccion_especialidad_magistrado" -v`
Expected: FAIL — `total` viene en 2, no 1 (el endpoint todavía ignora esos query params).

- [ ] **Step 7: Pasar los parámetros nuevos desde el endpoint**

En `api/routers/documents.py`, la firma de `get_documents` (línea 54) gana los tres parámetros, y la llamada a `repository.list_documents` (línea 69) los propaga:

```python
def get_documents(
    source_id: Optional[int] = None,
    family_key: Optional[str] = None,
    tipo: Optional[str] = None,
    seccion: Optional[str] = None,
    especialidad: Optional[str] = None,
    magistrado: Optional[str] = None,
    title: Optional[str] = None,
    title_exact: Optional[str] = None,
    review_status: Optional[str] = None,
    f_public_from: Optional[date] = None,
    f_public_to: Optional[date] = None,
    downloaded_from: Optional[date] = None,
    downloaded_to: Optional[date] = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    items, total = repository.list_documents(
        db,
        source_id=source_id,
        family_key=family_key,
        tipo=tipo,
        seccion=seccion,
        especialidad=especialidad,
        magistrado=magistrado,
        review_status=review_status,
        f_public_from=f_public_from,
        f_public_to=f_public_to,
        downloaded_from=downloaded_from,
        downloaded_to=downloaded_to,
        title_contains=title,
        title_exact=title_exact,
        collapse_case_families=title_exact is None,
        limit=limit,
        offset=offset,
    )
```

- [ ] **Step 8: Correr el test y confirmar que pasa**

Run: `.venv/Scripts/pytest tests/test_api_documents.py -k "filters_by_seccion_especialidad_magistrado" -v`
Expected: PASS

- [ ] **Step 9: Correr toda la suite de backend para descartar regresiones**

Run: `.venv/Scripts/pytest -v`
Expected: mismos resultados que antes de esta tarea (90 passed, 1 pre-existing failure de `test_migrations.py` — ver Gotchas del skill `run-iurisync`) más los tests nuevos de las Tasks 1-3, todos en PASS.

- [ ] **Step 10: Commit**

```bash
git add core/db/repository.py api/routers/documents.py tests/test_repository.py tests/test_api_documents.py
git commit -m "feat: filtra GET /documents por seccion, especialidad y magistrado"
```

---

### Task 4: Cliente frontend — funciones de API nuevas

**Files:**
- Modify: `frontend/src/api/documents.ts` (líneas 6-28)
- Test: `frontend/src/api/documents.test.ts`

**Interfaces:**
- Consumes: endpoints `GET /documents/secciones`, `/especialidades`, `/magistrados` de la Task 2; parámetros `seccion`/`especialidad`/`magistrado` de `GET /documents` de la Task 3.
- Produces:
  - `fetchDocumentSecciones(sourceId?: number, tipo?: string): Promise<string[]>`
  - `fetchDocumentEspecialidades(sourceId?: number, tipo?: string, seccion?: string): Promise<string[]>`
  - `fetchDocumentMagistrados(sourceId?: number, tipo?: string, seccion?: string, especialidad?: string): Promise<string[]>`
  - `ListDocumentsParams` gana `seccion?: string`, `especialidad?: string`, `magistrado?: string`.

- [ ] **Step 1: Escribir los tests que fallan**

En `frontend/src/api/documents.test.ts`, agregar `fetchDocumentSecciones`, `fetchDocumentEspecialidades`, `fetchDocumentMagistrados` al bloque de imports (líneas 5-16), y agregar, justo después del test `"fetchDocumentTipos fetches the distinct list of tipos"` (línea 39-45):

```typescript
  it("fetchDocumentSecciones fetches the distinct list of secciones, scoped by tipo", async () => {
    let receivedUrl = "";
    server.use(
      http.get(`${BASE_URL}/documents/secciones`, ({ request }) => {
        receivedUrl = request.url;
        return HttpResponse.json(["SECCION PRIMERA", "SECCION SEGUNDA"]);
      })
    );

    const secciones = await fetchDocumentSecciones(1, "Sentencia");

    expect(secciones).toEqual(["SECCION PRIMERA", "SECCION SEGUNDA"]);
    expect(receivedUrl).toContain("source_id=1");
    expect(receivedUrl).toContain("tipo=Sentencia");
  });

  it("fetchDocumentEspecialidades fetches the distinct list of especialidades, scoped by seccion", async () => {
    let receivedUrl = "";
    server.use(
      http.get(`${BASE_URL}/documents/especialidades`, ({ request }) => {
        receivedUrl = request.url;
        return HttpResponse.json(["Nulidad"]);
      })
    );

    const especialidades = await fetchDocumentEspecialidades(1, "Sentencia", "SECCION PRIMERA");

    expect(especialidades).toEqual(["Nulidad"]);
    expect(receivedUrl).toContain("seccion=SECCION+PRIMERA");
  });

  it("fetchDocumentMagistrados fetches the distinct list of magistrados, scoped by especialidad", async () => {
    let receivedUrl = "";
    server.use(
      http.get(`${BASE_URL}/documents/magistrados`, ({ request }) => {
        receivedUrl = request.url;
        return HttpResponse.json(["Ana Pérez"]);
      })
    );

    const magistrados = await fetchDocumentMagistrados(1, "Sentencia", "SECCION PRIMERA", "Nulidad");

    expect(magistrados).toEqual(["Ana Pérez"]);
    expect(receivedUrl).toContain("especialidad=Nulidad");
  });
```

- [ ] **Step 2: Correr los tests y confirmar que fallan**

Run: `cd frontend && npm test -- --run documents.test.ts`
Expected: FAIL — `fetchDocumentSecciones is not a function` (y equivalentes).

- [ ] **Step 3: Implementar las funciones y extender `ListDocumentsParams`**

En `frontend/src/api/documents.ts`, la interfaz `ListDocumentsParams` (líneas 6-20) gana tres campos, y se agregan tres funciones nuevas justo después de `fetchDocumentTipos` (línea 28):

```typescript
export interface ListDocumentsParams {
  source_id?: number;
  family_key?: string;
  tipo?: string;
  seccion?: string;
  especialidad?: string;
  magistrado?: string;
  title?: string;
  title_exact?: string;
  review_status?: DocumentReviewStatus;
  f_public_from?: string;
  f_public_to?: string;
  downloaded_from?: string;
  downloaded_to?: string;
  limit?: number;
  offset?: number;
  [key: string]: string | number | boolean | undefined;
}

export function fetchDocuments(params: ListDocumentsParams = {}): Promise<PaginatedDocuments> {
  return apiFetch<PaginatedDocuments>(`/documents${buildQuery(params)}`);
}

export function fetchDocumentTipos(sourceId?: number): Promise<string[]> {
  return apiFetch<string[]>(`/documents/tipos${buildQuery({ source_id: sourceId })}`);
}

export function fetchDocumentSecciones(sourceId?: number, tipo?: string): Promise<string[]> {
  return apiFetch<string[]>(`/documents/secciones${buildQuery({ source_id: sourceId, tipo })}`);
}

export function fetchDocumentEspecialidades(sourceId?: number, tipo?: string, seccion?: string): Promise<string[]> {
  return apiFetch<string[]>(`/documents/especialidades${buildQuery({ source_id: sourceId, tipo, seccion })}`);
}

export function fetchDocumentMagistrados(
  sourceId?: number,
  tipo?: string,
  seccion?: string,
  especialidad?: string
): Promise<string[]> {
  return apiFetch<string[]>(
    `/documents/magistrados${buildQuery({ source_id: sourceId, tipo, seccion, especialidad })}`
  );
}
```

- [ ] **Step 4: Correr los tests y confirmar que pasan**

Run: `cd frontend && npm test -- --run documents.test.ts`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api/documents.ts frontend/src/api/documents.test.ts
git commit -m "feat: agrega funciones de cliente para secciones/especialidades/magistrados"
```

---

### Task 5: `DocumentsPage.tsx` — filtros en cascada Sección → Especialidad → Magistrado

**Files:**
- Modify: `frontend/src/pages/DocumentsPage.tsx`
- Test: `frontend/src/pages/DocumentsPage.test.tsx`

**Interfaces:**
- Consumes: `fetchDocumentSecciones`, `fetchDocumentEspecialidades`, `fetchDocumentMagistrados`, `ListDocumentsParams` de la Task 4.

- [ ] **Step 1: Actualizar `mockFilterEndpoints` y el test manual de cascada de Tipo con los tres endpoints nuevos**

`DocumentsPage.tsx` va a disparar `useQuery` para `/documents/secciones`, `/documents/especialidades` y `/documents/magistrados` en cada render, incluso antes de escribir la UI de esta tarea (los tests de la página se escriben primero). Como el servidor de pruebas usa `onUnhandledRequest: "error"` (`frontend/src/test/setup.ts:5`), toda petición sin mock hace fallar el test. Hay que agregar los tres mocks por defecto ahora, antes de escribir el test de cascada.

En `frontend/src/pages/DocumentsPage.test.tsx`, `mockFilterEndpoints` (líneas 112-118):

```typescript
function mockFilterEndpoints() {
  server.use(
    http.get(`${BASE_URL}/sources`, () => HttpResponse.json([SOURCE])),
    http.get(`${BASE_URL}/source-families`, () => HttpResponse.json([FAMILY])),
    http.get(`${BASE_URL}/documents/tipos`, () => HttpResponse.json(["Auto", "Sentencia"])),
    http.get(`${BASE_URL}/documents/secciones`, () => HttpResponse.json([])),
    http.get(`${BASE_URL}/documents/especialidades`, () => HttpResponse.json([])),
    http.get(`${BASE_URL}/documents/magistrados`, () => HttpResponse.json([]))
  );
}
```

Y en el test `"scopes the Tipo dropdown to the selected Fuente (nested filters)"` (líneas 409-432), que arma sus propios handlers en vez de usar `mockFilterEndpoints()`, agregar los mismos tres mocks vacíos al bloque `server.use(...)` (líneas 411-420):

```typescript
    server.use(
      http.get(`${BASE_URL}/sources`, () => HttpResponse.json([SOURCE])),
      http.get(`${BASE_URL}/source-families`, () => HttpResponse.json([FAMILY])),
      http.get(`${BASE_URL}/documents/tipos`, ({ request }) => {
        lastTiposUrl = request.url;
        return lastTiposUrl.includes("source_id=1")
          ? HttpResponse.json(["Sentencia"])
          : HttpResponse.json(["Auto", "Sentencia"]);
      }),
      http.get(`${BASE_URL}/documents/secciones`, () => HttpResponse.json([])),
      http.get(`${BASE_URL}/documents/especialidades`, () => HttpResponse.json([])),
      http.get(`${BASE_URL}/documents/magistrados`, () => HttpResponse.json([])),
      http.get(`${BASE_URL}/documents`, () => HttpResponse.json({ items: [], total: 0, limit: 50, offset: 0 }))
    );
```

Run: `cd frontend && npm test -- --run DocumentsPage.test.tsx`
Expected: PASS — la suite completa de `DocumentsPage.test.tsx` sigue en verde (todavía no se agregó UI nueva, este paso solo evita romper los tests existentes en el siguiente paso).

- [ ] **Step 2: Escribir el test de cascada que falla**

Justo después del test `"scopes the Tipo dropdown to the selected Fuente (nested filters)"` (línea 432), agregar:

```typescript
  it("scopes the Sección dropdown to the selected Tipo, and resets Sección/Especialidad in cascade when they become invalid (nested filters)", async () => {
    let lastSeccionesUrl = "";
    server.use(
      http.get(`${BASE_URL}/sources`, () => HttpResponse.json([SOURCE])),
      http.get(`${BASE_URL}/source-families`, () => HttpResponse.json([FAMILY])),
      http.get(`${BASE_URL}/documents/tipos`, () => HttpResponse.json(["Auto", "Sentencia"])),
      http.get(`${BASE_URL}/documents/secciones`, ({ request }) => {
        lastSeccionesUrl = request.url;
        return lastSeccionesUrl.includes("tipo=Sentencia")
          ? HttpResponse.json(["SECCION PRIMERA"])
          : HttpResponse.json(["SECCION PRIMERA", "SECCION SEGUNDA"]);
      }),
      http.get(`${BASE_URL}/documents/especialidades`, ({ request }) => {
        const url = request.url;
        return url.includes("seccion=SECCION+SEGUNDA")
          ? HttpResponse.json(["Conciliación"])
          : HttpResponse.json(["Nulidad"]);
      }),
      http.get(`${BASE_URL}/documents/magistrados`, () => HttpResponse.json([])),
      http.get(`${BASE_URL}/documents`, () => HttpResponse.json({ items: [], total: 0, limit: 50, offset: 0 }))
    );
    const user = userEvent.setup();
    renderPage();

    await waitFor(() => expect(screen.getByLabelText("Sección")).toHaveTextContent("SECCION SEGUNDA"));

    await user.selectOptions(screen.getByLabelText("Sección"), "SECCION SEGUNDA");
    await waitFor(() => expect(screen.getByLabelText("Especialidad/Proceso")).toHaveTextContent("Conciliación"));
    await user.selectOptions(screen.getByLabelText("Especialidad/Proceso"), "Conciliación");
    expect((screen.getByLabelText("Especialidad/Proceso") as HTMLSelectElement).value).toBe("Conciliación");

    await user.selectOptions(screen.getByLabelText("Tipo"), "Sentencia");

    await waitFor(() => expect(lastSeccionesUrl).toContain("tipo=Sentencia"));
    // "SECCION SEGUNDA" ya no es una opción válida bajo Tipo="Sentencia" (solo
    // queda "SECCION PRIMERA"), así que el filtro de Sección debe resetearse a
    // "Todas" — y ese reseteo, a su vez, invalida "Conciliación" en Especialidad
    // (que solo aplicaba bajo "SECCION SEGUNDA"), reseteándolo también en cascada.
    await waitFor(() => expect((screen.getByLabelText("Sección") as HTMLSelectElement).value).toBe(""));
    await waitFor(() => expect((screen.getByLabelText("Especialidad/Proceso") as HTMLSelectElement).value).toBe(""));
  });
```

- [ ] **Step 3: Correr el test y confirmar que falla**

Run: `cd frontend && npm test -- --run DocumentsPage.test.tsx -t "scopes the Sección dropdown"`
Expected: FAIL con `Unable to find a label with the text of: Sección` (la UI todavía no existe).

- [ ] **Step 4: Agregar estado, queries y efectos de reseteo en cascada**

En `frontend/src/pages/DocumentsPage.tsx`, después del estado de `tipo` (línea 47), agregar:

```typescript
  const [seccion, setSeccion] = useState("");
  const [especialidad, setEspecialidad] = useState("");
  const [magistrado, setMagistrado] = useState("");
```

Después del `useEffect` que resetea `tipo` (líneas 102-106), agregar los `useQuery` y `useEffect` de cascada:

```typescript
  const seccionesQuery = useQuery({
    queryKey: ["documents", "secciones", sourceId, tipo],
    queryFn: () => fetchDocumentSecciones(sourceId ? Number(sourceId) : undefined, tipo || undefined),
  });

  useEffect(() => {
    if (seccion && seccionesQuery.data && !seccionesQuery.data.includes(seccion)) {
      setSeccion("");
    }
  }, [seccion, seccionesQuery.data]);

  const especialidadesQuery = useQuery({
    queryKey: ["documents", "especialidades", sourceId, tipo, seccion],
    queryFn: () =>
      fetchDocumentEspecialidades(sourceId ? Number(sourceId) : undefined, tipo || undefined, seccion || undefined),
  });

  useEffect(() => {
    if (especialidad && especialidadesQuery.data && !especialidadesQuery.data.includes(especialidad)) {
      setEspecialidad("");
    }
  }, [especialidad, especialidadesQuery.data]);

  const magistradosQuery = useQuery({
    queryKey: ["documents", "magistrados", sourceId, tipo, seccion, especialidad],
    queryFn: () =>
      fetchDocumentMagistrados(
        sourceId ? Number(sourceId) : undefined,
        tipo || undefined,
        seccion || undefined,
        especialidad || undefined
      ),
  });

  useEffect(() => {
    if (magistrado && magistradosQuery.data && !magistradosQuery.data.includes(magistrado)) {
      setMagistrado("");
    }
  }, [magistrado, magistradosQuery.data]);
```

Y actualizar el import de `../api/documents` (línea 8) para incluir las tres funciones nuevas:

```typescript
import { fetchDocuments, fetchDocumentTipos, fetchDocumentSecciones, fetchDocumentEspecialidades, fetchDocumentMagistrados } from "../api/documents";
```

- [ ] **Step 5: Agregar los tres campos a `documentsQuery`**

En `documentsQuery` (líneas 113-128), agregar `seccion`, `especialidad`, `magistrado` al `queryKey` y a los parámetros de `fetchDocuments`:

```typescript
  const documentsQuery = useQuery({
    queryKey: ["documents", title, tipo, seccion, especialidad, magistrado, sourceId, reviewStatus, fPublicFrom, fPublicTo, downloadedFrom, downloadedTo, page],
    queryFn: () =>
      fetchDocuments({
        title: title || undefined,
        tipo: tipo || undefined,
        seccion: seccion || undefined,
        especialidad: especialidad || undefined,
        magistrado: magistrado || undefined,
        source_id: sourceId ? Number(sourceId) : undefined,
        review_status: reviewStatus || undefined,
        f_public_from: fPublicFrom || undefined,
        f_public_to: fPublicTo || undefined,
        downloaded_from: downloadedFrom || undefined,
        downloaded_to: downloadedTo || undefined,
        limit: PAGE_SIZE,
        offset: page * PAGE_SIZE,
      }),
  });
```

- [ ] **Step 6: Agregar los tres `NativeSelect` en la barra de filtros**

Después del bloque `<label>` de "Tipo" (líneas 225-242), y antes del bloque `<label>` de "Revisión" (línea 243), agregar:

```tsx
        <label className="flex items-center gap-2 text-sm text-muted-foreground">
          Sección
          <NativeSelect
            value={seccion}
            onChange={(event) => {
              setSeccion(event.target.value);
              setPage(0);
            }}
            className="w-40"
          >
            <option value="">Todas</option>
            {seccionesQuery.data?.map((seccionOption) => (
              <option key={seccionOption} value={seccionOption}>
                {seccionOption}
              </option>
            ))}
          </NativeSelect>
        </label>
        <label className="flex items-center gap-2 text-sm text-muted-foreground">
          Especialidad/Proceso
          <NativeSelect
            value={especialidad}
            onChange={(event) => {
              setEspecialidad(event.target.value);
              setPage(0);
            }}
            className="w-40"
          >
            <option value="">Todas</option>
            {especialidadesQuery.data?.map((especialidadOption) => (
              <option key={especialidadOption} value={especialidadOption}>
                {especialidadOption}
              </option>
            ))}
          </NativeSelect>
        </label>
        <label className="flex items-center gap-2 text-sm text-muted-foreground">
          Magistrado
          <NativeSelect
            value={magistrado}
            onChange={(event) => {
              setMagistrado(event.target.value);
              setPage(0);
            }}
            className="w-40"
          >
            <option value="">Todos</option>
            {magistradosQuery.data?.map((magistradoOption) => (
              <option key={magistradoOption} value={magistradoOption}>
                {magistradoOption}
              </option>
            ))}
          </NativeSelect>
        </label>
```

- [ ] **Step 7: Correr el test de cascada y confirmar que pasa**

Run: `cd frontend && npm test -- --run DocumentsPage.test.tsx -t "scopes the Sección dropdown"`
Expected: PASS

- [ ] **Step 8: Correr toda la suite de frontend para descartar regresiones**

Run: `cd frontend && npm test -- --run`
Expected: todos los archivos en PASS, incluyendo `DocumentsPage.test.tsx` completo (los filtros nuevos no deben afectar ningún test existente, ya que todos pasan por `undefined` cuando su valor es `""`).

- [ ] **Step 9: Commit**

```bash
git add frontend/src/pages/DocumentsPage.tsx frontend/src/pages/DocumentsPage.test.tsx
git commit -m "feat: agrega filtros en cascada de Seccion, Especialidad y Magistrado a Documentos"
```

---

## Verificación final

Después de la Task 5, correr ambas suites completas una vez más para confirmar que no queda nada roto:

```bash
.venv/Scripts/pytest -v
cd frontend && npm test -- --run
```

Luego, opcionalmente, usar el skill `run-iurisync` para levantar la app y confirmar visualmente en el navegador que los tres filtros nuevos aparecen en Documentos, se acotan entre sí, y que filtrar por una combinación real (con los 1056 documentos de Consejo de Estado ya cargados en la base local) devuelve resultados correctos.
