# Vinculación de casos entre tribunales (SAMAI)

## Problema

Un mismo proceso judicial puede pasar por más de un tribunal a lo largo de
su vida — por ejemplo, un Tribunal Administrativo departamental resuelve en
primera instancia y el Consejo de Estado resuelve la apelación. Hoy IURISYNC
guarda cada actuación como un documento independiente, sin ninguna forma de
saber que dos documentos capturados en fuentes distintas pertenecen al mismo
proceso.

Ya existe un mecanismo que agrupa actuaciones repetidas **dentro de la misma
fuente/tribunal** (mismo título exacto → se cuentan como "N actuaciones" del
mismo caso, `core/db/repository.py::list_documents` con
`collapse_case_families`). Este diseño resuelve el problema distinto de
**cruzar tribunales**: cuando el mismo proceso reaparece en otra fuente,
posiblemente con el radicado escrito de forma ligeramente distinta.

No hay certeza sobre si el radicado se mantiene idéntico entre instancias o
si cambia una parte (posiblemente el segmento final). Por eso el diseño no
apuesta a una regla exacta: genera sugerencias por similitud y siempre deja
la confirmación final a una persona.

## Alcance (v1)

Solo dentro de la familia **`samai`** (Consejo de Estado + Tribunales
Administrativos) — comparten el mismo formato de radicado y es el caso real
que motivó este trabajo. Cruces con otras familias (`rama_judicial`, etc.)
quedan fuera de este diseño; se podrían agregar después si se justifica.

## Datos

### `documents.radicado` (columna nueva)

`String`, nullable, indexada. Se llena en el momento de captura por el
scraper de `samai` (ya tiene el radicado disponible en crudo en
`_parse_row`, columna `tds[1]`) — normalizado a solo dígitos. No se agrega
como columna visible en la tabla de documentos de la interfaz: es un dato
interno, solo para emparejar y buscar.

### `case_links`

El "expediente" en sí.

| columna      | tipo      |
|--------------|-----------|
| id           | PK        |
| created_at   | timestamp |

### `case_link_stages`

Las etapas que componen un expediente: qué fuente (tribunal) + qué radicado
pertenece a él. Cualquier documento nuevo que llegue después con esa misma
combinación fuente+radicado (una nueva actuación en un tribunal que ya era
parte del expediente) queda automáticamente incluido, sin volver a pasar por
confirmación.

| columna      | tipo                          |
|--------------|-------------------------------|
| id           | PK                            |
| case_link_id | FK -> case_links               |
| source_id    | FK -> sources                  |
| radicado     | String                         |

Restricción: `unique(source_id, radicado)` — una combinación fuente+radicado
pertenece como máximo a un expediente.

### `case_link_suggestions`

La bandeja de sugerencias pendientes de revisar.

| columna         | tipo                                          |
|-----------------|------------------------------------------------|
| id              | PK                                              |
| source_id_a     | FK -> sources                                   |
| radicado_a      | String                                          |
| source_id_b     | FK -> sources                                   |
| radicado_b      | String                                          |
| status          | `pending` \| `confirmed` \| `dismissed`         |
| matched_digits  | Integer — largo del prefijo inicial que realmente coincide entre los dos radicados (puede ser mayor a 16 si coinciden más), para mostrarle contexto a quien revisa |
| created_at      | timestamp                                       |
| resolved_at     | timestamp, nullable                             |

Restricción: no se crea una sugerencia nueva si ya existe cualquier fila
(en cualquier estado) para el mismo par `(source_id_a, radicado_a,
source_id_b, radicado_b)` — así un descarte no se vuelve a sugerir, y una
confirmación no se duplica. El par se guarda siempre en un orden consistente
(ej. el `source_id` más chico va como lado "a") para que el mismo cruce no
genere dos sugerencias espejo (A~B y B~A).

## Cómo se generan las sugerencias

Después de que termina un run de una fuente `samai` (hook junto a
`finalize_run` en `worker/tasks.py`), por cada combinación fuente+radicado
nueva en ese run:

1. Se comparan los primeros ~16 dígitos de su radicado contra los de todas
   las demás combinaciones fuente+radicado ya existentes en la familia
   `samai`, excluyendo la misma fuente.
2. Cada coincidencia que no tenga ya una fila en `case_link_suggestions`
   genera una sugerencia `pending`.

El número exacto de dígitos a comparar (16) es un punto de partida, no una
regla probada — se puede ajustar más adelante con casos reales ya
confirmados por el equipo, sin cambiar el resto del diseño.

Esta búsqueda corre **después** de que el run ya guardó sus documentos. Si
falla, el error se registra pero el run queda igual de completo — nunca se
tumba un run por esto (mismo patrón que ya usa `generate_document_preview_pdf`
al fallar: se captura la excepción, se loggea, no se propaga).

## Confirmar, descartar, vincular manualmente

**Confirmar una sugerencia:** crea un `case_link` nuevo con sus dos etapas —
o, si alguno de los dos lados (fuente+radicado) ya pertenece a un
`case_link` existente (ej. una tercera instancia que se agrega después), le
suma la etapa nueva a ese mismo expediente en vez de crear uno aparte.
Marca la sugerencia como `confirmed`.

**Descartar:** marca la sugerencia como `dismissed`. Queda registrada para
que el generador de sugerencias no la vuelva a proponer.

**Vincular manualmente:** para los casos que el sistema no detectó solo.
Desde la bandeja, un botón aparte permite buscar dos combinaciones
fuente+radicado directamente y unirlas — mismo resultado que confirmar una
sugerencia, pero sin que haya existido una fila en `case_link_suggestions`.

Si al confirmar/descartar/vincular la sugerencia u otro dato ya no existe
(alguien más la resolvió mientras tanto), la API responde con un error claro
en vez de fallar en silencio o duplicar datos.

## Interfaz

**"Casos por confirmar" (pantalla nueva).** Lista las sugerencias
`pending`: fuente A + radicado + rango de fechas de sus documentos, fuente B
+ lo mismo, cuántos dígitos coincidieron (`matched_digits`, como contexto
para decidir), y dos botones — Confirmar / Descartar. Entrada en el menú
lateral con contador de pendientes (mismo patrón visual que ya existe para
documentos con revisión pendiente). Incluye el botón de vínculo manual.

**Línea de tiempo del expediente (pantalla nueva).** Al confirmar o vincular
manualmente, se puede entrar a ver el expediente completo: sus etapas en
orden por fecha, cada una con su tribunal y los documentos de esa etapa,
con enlace directo a cada uno.

**Ficha de un documento.** Si el documento pertenece a una sugerencia
pendiente, aparece una nota: "Posible caso relacionado, pendiente de
confirmar" con enlace a la bandeja. Si ya pertenece a un expediente
confirmado, aparece en su lugar: "Este caso también aparece en: {fuente}"
con enlace a la línea de tiempo.

## Datos existentes (backfill)

Script de una sola corrida (estilo `core/seed.py`) que, sobre los ~1,326
documentos de `samai` que ya existen:

1. Les llena `radicado` parseando el título con la misma lógica que ya usa
   `core/utils.py::is_samai_case_title` (extraer los dígitos antes del
   paréntesis).
2. Corre la misma búsqueda de coincidencias que correría después de un run,
   sobre todas las combinaciones fuente+radicado ya presentes.

Se documenta cómo correrlo (una vez por entorno — dev ahora, producción real
más adelante cuando exista).

## Pruebas

- Función de comparación de prefijos: casos que deben coincidir y casos que
  no, con radicados sintéticos.
- Repositorio: confirmar/descartar/vincular manualmente hacen lo correcto
  sobre `case_links`/`case_link_stages`/`case_link_suggestions`, incluyendo
  el caso de sumar una tercera etapa a un expediente ya existente.
- Un run de `samai` dispara la generación de sugerencias, y un fallo ahí no
  rompe el run.
- Endpoints de la API nuevos (listar bandeja, confirmar, descartar, vínculo
  manual, detalle del expediente).
- Script de backfill deja los datos existentes consistentes.
