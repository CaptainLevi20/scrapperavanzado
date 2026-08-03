# Documentos: filtros anidados (Sección → Especialidad → Magistrado)

## Problema

El apartado "Documentos" ya muestra las columnas Sección, Especialidad/Proceso
y Magistrado en la tabla, pero no se pueden usar como filtro. El único filtro
en cascada que existe hoy es Fuente → Tipo (elegir una Fuente acota las
opciones de Tipo). El usuario quiere que Sección, Especialidad y Magistrado
también sean filtrables, en cascada, encadenados después de Tipo.

Se confirmó en la base de datos que existe una jerarquía real de datos: cada
Sección de Consejo de Estado tiene su propio conjunto de Especialidades (ej.
"SECCION CUARTA" solo tiene 5 especialidades distintas, "SECCION PRIMERA"
tiene 13, sin solapamiento total) — la cascada refleja una relación genuina,
no solo una decisión de UI.

## Alcance

- Orden de cascada: **Fuente → Tipo → Sección → Especialidad → Magistrado**.
  Cada filtro acota las opciones de los siguientes, igual que Fuente ya acota
  Tipo hoy.
- Tres endpoints nuevos de opciones (`/documents/secciones`,
  `/documents/especialidades`, `/documents/magistrados`), siguiendo
  exactamente el patrón de `/documents/tipos` +
  `list_distinct_document_tipos`.
- `GET /documents` y `repository.list_documents` ganan los parámetros
  `seccion`, `especialidad`, `magistrado`.
- Frontend: tres `NativeSelect` nuevos en `DocumentsPage.tsx`, mismo
  comportamiento de reseteo en cascada que ya tiene Tipo.

Fuera de alcance: cambiar el filtro de Tipo existente, agregar lógica de
combinación AND/OR o filtros guardados (el usuario confirmó que "filtros
anidados" se refiere solo a cascada por campo), y filtrar por Fecha
providencia (no fue pedido).

## Backend

En `core/db/repository.py`, junto a `list_distinct_document_tipos`, tres
funciones nuevas que replican su forma, cada una recibiendo como filtro
opcional todo lo que la precede en la cascada:

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

`list_documents` gana los mismos tres campos como parámetros opcionales, cada
uno un `WHERE Document.campo == valor` agregado junto a los filtros
existentes (mismo lugar/estilo que el `if tipo is not None` ya presente).

En `api/routers/documents.py`, junto a `get_document_tipos`:

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

`get_documents` (el endpoint `GET /documents`) gana `seccion`, `especialidad`,
`magistrado` como query params opcionales y los pasa tal cual a
`repository.list_documents`.

## Frontend

En `frontend/src/api/documents.ts`: tres funciones nuevas
(`fetchDocumentSecciones`, `fetchDocumentEspecialidades`,
`fetchDocumentMagistrados`), mismo estilo que `fetchDocumentTipos`. El tipo de
parámetros de `fetchDocuments` gana `seccion?`, `especialidad?`,
`magistrado?`.

En `DocumentsPage.tsx`:

- Estado nuevo: `seccion`, `especialidad`, `magistrado` (todos `string`,
  `""` = "Todos"), cada uno con su `NativeSelect` agregado en la barra de
  filtros, en el orden Fuente → Tipo → Sección → Especialidad → Magistrado.
- Tres `useQuery` nuevos (`seccionesQuery`, `especialidadesQuery`,
  `magistradosQuery`), cada uno con `queryKey` y llamada scoped a los
  filtros de nivel superior ya elegidos — el mismo patrón que `tiposQuery`
  ya usa con `sourceId`:
  - `seccionesQuery` depende de `sourceId`, `tipo`.
  - `especialidadesQuery` depende de `sourceId`, `tipo`, `seccion`.
  - `magistradosQuery` depende de `sourceId`, `tipo`, `seccion`,
    `especialidad`.
- Tres `useEffect` nuevos, uno por campo, que limpian el valor si ya no
  aparece en las opciones recién cargadas — mismo patrón que el `useEffect`
  existente en líneas 102-106 para `tipo`.
- `documentsQuery`: `seccion`, `especialidad`, `magistrado` se agregan al
  `queryKey` y a los parámetros pasados a `fetchDocuments`. Cambiar
  cualquiera de los tres resetea `page` a 0, igual que los demás filtros.

No se toca el layout de la tabla — las tres columnas ya existen, solo se
vuelven filtrables. No se toca `openCaseDialog` ni la lógica de agrupamiento
de expedientes (usan `title_exact`, no estos campos).

## Pruebas

- `tests/test_repository.py`: un test por función nueva
  (`list_distinct_document_secciones/especialidades/magistrados`) verificando
  que el scoping por los filtros superiores funciona (ej. pedir
  especialidades con una `seccion` distinta devuelve un conjunto distinto),
  siguiendo el estilo de los tests existentes para `list_distinct_document_tipos`.
- `tests/test_api_documents.py`: un test por endpoint nuevo
  (`/documents/secciones`, `/documents/especialidades`,
  `/documents/magistrados`) y una extensión del test existente de
  `GET /documents` cubriendo el filtrado por `seccion`, `especialidad` y
  `magistrado`.
- `frontend/src/pages/DocumentsPage.test.tsx`: un test de cascada — cambiar
  Sección resetea Especialidad si el valor elegido ya no está en las nuevas
  opciones, espejo del test ya existente (si existe) para el reseteo de Tipo
  al cambiar Fuente.
