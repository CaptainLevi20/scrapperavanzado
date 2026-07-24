# Rama Judicial — detalle de acción y agrupación por radicado — Diseño

Fecha: 2026-07-23

## Contexto y objetivo

Con la normalización de títulos ya implementada (`T_{CODIGO}_{radicado segmentado}`, ver `docs/superpowers/specs/2026-07-23-rama-judicial-title-normalization-design.md`), se descubrió que **111 de 697 documentos distintos (16%)** del piloto (Tribunal Superior de Bogotá, junio 2026) comparten título con al menos otro documento — porque un mismo radicado (caso/expediente) acumula varias actuaciones distintas (autos, sentencias) a lo largo del proceso, cada una un documento real distinto.

Este diseño agrega dos piezas complementarias:
1. Capturar una descripción legible de la acción (sin el juez) en el campo `detalle`, ya existente y hoy sin usar para esta familia.
2. Permitir ver todos los documentos de un mismo radicado con un click, reutilizando el buscador de título que ya existe en la página de Documentos — sin agrupación visual anidada ni cambios de esquema.

Explícitamente en alcance: los 33 tribunales superiores (misma condición de disparo que la normalización de título — 23 dígitos + `_` al inicio del nombre de archivo).

Explícitamente fuera de alcance:
- Otras fuentes (CNDJ, Corte Suprema, etc.) — no se tocan.
- Agrupación visual anidada/expandible en la tabla — se descartó por la complicación de orden (`list_documents` ordena por `f_public desc`, no por título; agrupar visualmente exigiría reordenar toda la tabla o una consulta aparte). Se opta por la alternativa simple: click en el título rellena el filtro de búsqueda existente.
- Parsear o "limpiar" el nombre del juez — se descarta por completo, no se guarda en ningún campo (ya decidido en el diseño de normalización de título).

## Parte 1 — Extracción de `detalle`

### Algoritmo

Dado el nombre de archivo sin extensión (`name_no_ext`, el mismo valor que ya recibe `_normalize_title`):

1. Si no calza con la misma condición de disparo que `_normalize_title` (no empieza con 23 dígitos + `_`), `detalle` queda `None` — sin cambios respecto a hoy.
2. Si calza, se toma todo lo que sigue después del radicado y el `_` (incluyendo un posible espacio extra, ej. `"11001310300220230031101_ DrZamudioAutoResuelevApelacion"`).
3. Si ese resto empieza con `Dr` o `Dra` seguido de una palabra en CamelCase (el apellido del juez, ej. `DraGonzalez`), esa porción se descarta — **el apellido del juez nunca queda en `detalle`**.
4. Lo que quede después (o el resto completo, si no había prefijo `Dr`/`Dra` — ver casos reales sin ese prefijo) se separa en palabras: se inserta un espacio antes de cada letra mayúscula que sigue a una minúscula, y los guiones bajos internos (ej. `AutoOrdenaRemitir_Cumplase`) se tratan también como separador de palabra.

### Casos reales verificados

| Nombre crudo (después del radicado) | `detalle` resultante |
|---|---|
| `DraGonzalezAutoAdmiteRecurso` | `Auto Admite Recurso` |
| `ValenzuelaSentenciaSegundaInstancia` (sin `Dr`/`Dra` — caso real sin ese prefijo) | `Valenzuela Sentencia Segunda Instancia` |
| `DrAtshanAutoOrdenaRemitir_Cumplase` | `Auto Ordena Remitir Cumplase` |
| ` DrZamudioAutoResuelevApelacion` (espacio extra real) | `Auto Resuelev Apelacion` (typo de la fuente, se respeta tal cual) |

No se corrige ortografía ni se completa texto — se pasa tal cual viene la fuente, solo se separan las palabras y se quita el juez.

### Dónde vive en el código

`core/scrapers/families/rama_judicial.py`: nueva función `_extract_detalle(name_no_ext: str) -> Optional[str]`, junto a `_normalize_title`. En `scrap()`, al construir cada `RawDocModel`, se agrega `detalle=_extract_detalle(name_no_ext)` (hoy ese parámetro no se pasa en absoluto, por lo que siempre es `None`).

## Parte 2 — Ver documentos del mismo radicado (click en título)

### Comportamiento

En `frontend/src/pages/DocumentsPage.tsx`, la celda de título (línea 286 hoy, `<td ... title={document.detalle ?? undefined}>{document.title}</td>`) se vuelve clicable:

- Al hacer click en el título de un documento, el filtro de texto "Título" (estado `title`, ya existente en el componente) se rellena con el título **exacto** de ese documento, y `page` vuelve a `0`.
- Esto reutiliza `fetchDocuments({ title: ... })` (ya implementado, búsqueda por substring vía `ilike` en el backend) sin ningún cambio de API ni de esquema — como los títulos normalizados son el formato fijo `T_{CODIGO}_{radicado}`, buscar por ese string exacto como substring solo puede calzar con ese mismo radicado, sin falsos positivos.
- El tooltip de `detalle` al pasar el mouse sobre el título (`title={document.detalle ?? undefined}`) ya funciona hoy sin cambios — en cuanto el backend empiece a poblar `detalle`, se ve automáticamente.

Este comportamiento es genérico (no depende de la familia del documento) — para fuentes donde los títulos ya son únicos, hacer click simplemente filtra a ese único documento, sin efecto práctico distinto al de escribir el título a mano en el buscador.

### Testing

- **Backend** (`tests/families/test_rama_judicial.py`):
  - `_extract_detalle`: un radicado con `Dr`/`Dra` + apellido + acción CamelCase produce la acción separada en palabras, sin el juez.
  - Un radicado sin prefijo `Dr`/`Dra` (caso real `ValenzuelaSentenciaSegundaInstancia`) separa todo el resto en palabras, incluyendo el apellido suelto.
  - Una acción con guión bajo interno (`AutoOrdenaRemitir_Cumplase`) también se separa correctamente.
  - Un nombre que no dispara la condición (23 dígitos + `_`) deja `detalle` en `None`.
  - `scrap()` end-to-end: un `RawDocModel` con radicado válido trae `detalle` poblado; uno sin radicado válido trae `detalle=None`.
- **Frontend** (`frontend/src/pages/DocumentsPage.test.tsx`):
  - Click en el título de una fila llama a `fetchDocuments` con el `title` exacto de esa fila (mock de la función, verificar el argumento) y resetea la página a 0.
  - El tooltip (`title` HTML attribute) del `<td>` sigue mostrando `document.detalle` sin cambios de comportamiento (regresión, ya cubierto si existe un test previo; si no existe, agregar uno mínimo).
