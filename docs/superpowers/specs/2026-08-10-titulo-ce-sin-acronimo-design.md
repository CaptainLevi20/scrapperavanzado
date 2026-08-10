# Spec: Quitar el acrónimo del título (Consejo de Estado)

**Fecha:** 2026-08-10
**Fuente afectada:** `samai` — corp Consejo de Estado (`_CONSEJO_DE_ESTADO_CORP_CODE = "1100103"`)

## Problema

Hoy el título de cada documento de Consejo de Estado lleva pegado el acrónimo
de la clase de proceso entre paréntesis, tomado de la "tabla de equivalencia"
`_CLASE_ACRONIMOS` en `core/scrapers/families/samai.py`.

Ejemplos actuales:

- Sin número de caso: `25000-23-42-002-0202-00008-01(NRD)`
- Con número de caso: `25000-23-42-002-0202-00008-01(74604)(NRD)`

El usuario ya no quiere que ese acrónimo aparezca en el título.

## Objetivo

Que el título de Consejo de Estado **no muestre el acrónimo**:

- Sin número de caso: `25000-23-42-002-0202-00008-01`
- Con número de caso: `25000-23-42-002-0202-00008-01(74604)`

## Alcance (decidido con el usuario)

**Sí cambia:**

- El título de los documentos de Consejo de Estado (nuevos y los ya guardados).

**NO cambia:**

- La columna **"Especialidad/Proceso"** sigue mostrando el nombre legible
  ("Nulidad y restablecimiento del derecho"). La tabla `_CLASE_ACRONIMOS` se
  mantiene: se sigue usando internamente en `_especialidad_legible` para
  traducir la clase → acrónimo → nombre legible. No se borra ninguna tabla.
- El desarrollo del **número de caso** (`_complementar_titulo_con_numero`,
  `resolve_unverified_document`, `core/backfill_ce_titles.py`) se queda igual.
  El número no es el acrónimo; sigue apareciendo.
- Los **Tribunales Administrativos** (formato `T_{CÓDIGO}_...`) no se tocan.
- El frontend no se toca: solo muestra `title` y `especialidad` tal como
  llegan de la base de datos; no hace ningún parseo del acrónimo.

## Contexto técnico importante

El acrónimo no es solo cosmético. El sistema usa el título para **agrupar las
distintas actuaciones de un mismo expediente** (mostrar solo la más reciente,
`list_documents(collapse_case_families=True)` en `core/db/repository.py`). El
patrón que reconoce "esto es título de un caso de Consejo de Estado"
(`SAMAI_CASE_TITLE_PATTERN` / `SAMAI_CASE_TITLE_RAW_PATTERN` en
`core/utils.py`) **hoy exige** que el título termine en `(ACRÓNIMO)`.

Por eso, quitar el acrónimo obliga a ajustar también ese reconocimiento; de lo
contrario los expedientes de Consejo de Estado dejarían de agruparse.

## Diseño

### 1. Generación del título — `core/scrapers/families/samai.py`

`_normalizar_titulo` deja de anexar el acrónimo para Consejo de Estado:

```python
if corp_code == _CONSEJO_DE_ESTADO_CORP_CODE:
    return radicado
```

(Se elimina la consulta a `_CLASE_ACRONIMOS` dentro de `_normalizar_titulo`;
la rama de Tribunales Administrativos no cambia.)

`_especialidad_legible` y `_CLASE_ACRONIMOS` / `_ACRONIMO_A_NOMBRE` se
conservan sin cambios: siguen alimentando el campo `especialidad`.

`_complementar_titulo_con_numero` no requiere cambios: hoy produce
`{radicado}({numero}){sufijo_acronimo}`; como los títulos nuevos ya no traen
acrónimo, `sufijo_acronimo` queda vacío y el resultado es `{radicado}({numero})`,
que es exactamente lo deseado. `_TITULO_CE_RE` ya trata el grupo del acrónimo
como opcional, así que sigue funcionando.

### 2. Reconocimiento de "título de caso" — `core/utils.py`

Los patrones se vuelven **tolerantes a la transición**: reconocen tanto el
formato nuevo (sin acrónimo) como el viejo (con acrónimo), para que nada se
rompa entre el despliegue y la corrida de la limpieza.

```python
# Radicado, con un grupo de número opcional y un grupo de acrónimo opcional.
SAMAI_CASE_TITLE_PATTERN = re.compile(
    r"^\d{5}-\d{2}-\d{2}-\d{3}-\d{4}-\d{5}-\d{2}"
    r"(?:\(\d[^)]{0,29}\))?(?:\([A-Z][A-Z0-9]*\))?$"
)
SAMAI_CASE_TITLE_RAW_PATTERN = re.compile(
    r"^\d{23}(?:\(\d[^)]{0,29}\))?(?:\([A-Z][A-Z0-9]*\))?$"
)
```

Notas:

- El grupo de **número** empieza con dígito (`\d`), el de **acrónimo** con
  letra mayúscula (`[A-Z]`) — misma distinción que ya usaba el código.
- Ambos grupos son opcionales. Esto cubre los cuatro estados posibles del
  título: `{radicado}`, `{radicado}({numero})`, `{radicado}({ACRÓNIMO})`
  (viejo), y `{radicado}({numero})({ACRÓNIMO})` (viejo complementado).
- El estado final que queremos (`{radicado}` o `{radicado}({numero})`) matchea
  sin problema. Los formatos viejos siguen matcheando hasta que la limpieza
  los corrija.

### 3. Limpieza única de datos ya guardados

Nuevo módulo `core/backfill_ce_titles_sin_acronimo.py` (mismo patrón que
`core/backfill_ce_titles.py`). Recorre los documentos cuya fuente es
"Consejo de Estado" y quita el acrónimo final del título ya guardado.

Regla de limpieza (helper `_quitar_acronimo(title) -> str | None`):

- Si el título termina en un grupo `(...)` que empieza con **letra mayúscula**
  (el acrónimo), se elimina ese último grupo.
- Un grupo `(...)` que empieza con **dígito** (el número de caso) se conserva.
- Si el título no termina en acrónimo, se devuelve `None` (nada que hacer),
  de modo que la corrida sea idempotente (se puede correr varias veces).

Regex propuesto (ancla los dos formatos, con número opcional, y acrónimo final
obligatorio para que haya algo que quitar):

```python
_TITULO_CON_ACRONIMO_RE = re.compile(
    r"^(\d{5}-\d{2}-\d{2}-\d{3}-\d{4}-\d{5}-\d{2}(?:\(\d[^)]{0,29}\))?"
    r"|\d{23}(?:\(\d[^)]{0,29}\))?)"
    r"\([A-Z][A-Z0-9]*\)$"
)
```

El grupo 1 es el título sin el acrónimo → se guarda con
`repository.update_document_title`. Se envuelve cada actualización en
try/except con `db.rollback()` en caso de error, igual que el backfill actual.

`main()` imprime cuántos documentos se actualizaron.

### 4. Aplicación en producción

Ruta estándar del proyecto (Claude no tiene acceso directo a producción):

1. Fusionar el cambio → CI construye las imágenes en GHCR.
2. En el servidor de la oficina: `docker compose pull` + `up`.
3. Correr una sola vez la limpieza dentro del contenedor:
   `python -m core.backfill_ce_titles_sin_acronimo`

Tras la limpieza, títulos viejos y nuevos quedan homogéneos y la agrupación de
expedientes funciona sobre `{radicado}` / `{radicado}({numero})`.

## Pruebas

- **`tests/families/test_samai.py`**: actualizar las aserciones que hoy esperan
  el acrónimo en el título (`_normalizar_titulo` para Consejo de Estado ahora
  devuelve solo el radicado). Confirmar que Tribunales Administrativos no
  cambian y que `_especialidad_legible` sigue devolviendo el nombre legible.
- **`tests/test_core_utils.py`** (o donde vivan los tests de los patrones):
  confirmar que `is_samai_case_title` reconoce `{radicado}`,
  `{radicado}({numero})`, y todavía los formatos viejos con acrónimo.
- **`tests/test_repository.py`**: confirmar que la agrupación
  (`collapse_case_families`) sigue colapsando actuaciones de un mismo
  expediente con títulos sin acrónimo.
- **Nueva prueba del backfill**: `_quitar_acronimo` quita el acrónimo,
  conserva el número de caso, y es idempotente (segunda corrida = 0 cambios).

## Riesgos y mitigaciones

- **Transición (despliegue antes de la limpieza):** mitigado porque los
  patrones de `core/utils.py` reconocen ambos formatos; nada se rompe mientras
  se corre la limpieza.
- **Idempotencia de la limpieza:** el helper devuelve `None` cuando no hay
  acrónimo, así que correr el script dos veces no hace daño.
- **Colisión de títulos tras quitar el acrónimo:** el radicado (± número) es la
  clave de caso; distintas actuaciones del mismo expediente *deben* compartir
  título — ese es justamente el comportamiento buscado por la agrupación.
