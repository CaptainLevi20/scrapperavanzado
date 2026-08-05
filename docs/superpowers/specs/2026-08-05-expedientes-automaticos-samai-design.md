# Expedientes automáticos entre tribunales (SAMAI) — Diseño

> Evolución de
> [`2026-07-29-vinculacion-casos-samai-design.md`](2026-07-29-vinculacion-casos-samai-design.md).
> Ese diseño resolvió **detectar** cuándo el mismo proceso reaparece en otra
> fuente y armó el flujo de sugerencias con confirmación humana. Este diseño
> **elimina el paso de confirmación** y arma los expedientes automáticamente.

## Contexto y motivación

El diseño original dejaba toda coincidencia como una **sugerencia pendiente**
que una persona debía confirmar. Ese paso existía por una incertidumbre
explícita: *"No hay certeza sobre si el radicado se mantiene idéntico entre
instancias o si cambia una parte."*

Esa incertidumbre ya se resolvió. Regla confirmada con el histórico real de
producción: un radicado tiene 23 dígitos, de los cuales los **primeros 21
identifican el proceso** y se mantienen idénticos durante toda su vida; los dos
últimos (posiciones 22-23) son la **instancia** y son los únicos que cambian
cuando el caso sube de un Tribunal Administrativo al Consejo de Estado (ver
`MIN_MATCH_DIGITS = 21` en `core/utils.py`). Con ese umbral, el emparejamiento
por radicado no produce falsos positivos: sobre los datos reales generó 30
coincidencias reales, todas del tipo "mismo proceso en otra instancia".

Como ya no hay incertidumbre que resolver, el paso de confirmación humana dejó
de aportar valor. El usuario necesita que **el expediente se arme de una vez**,
con su línea de tiempo, y que la sección se llame **"Expedientes"**.

## Decisiones (brainstorming 2026-08-05)

1. **Alcance:** "Expedientes" lista solo los procesos que cruzan **más de una
   fuente** (ej. Tribunal ↔ Consejo de Estado). Un proceso que solo vivió en un
   tribunal no forma expediente; sigue en Documentos.
2. **Control:** el expediente se arma solo, pero el usuario puede **quitar** una
   etapa que no corresponda; esa separación se **recuerda** para no volver a
   unirla automáticamente.
3. **Vinculación manual:** se **elimina** el formulario de unir radicados a mano
   (contradice la regla de los 21 dígitos).
4. **Enfoque:** reutilizar la maquinaria ya construida y validada (tablas
   `case_links`/`case_link_stages`, lógica de unión/fusión, línea de tiempo);
   solo cambia el "frente" del proceso.

## Alcance (v1)

Solo dentro de la familia **`samai`**. Solo expedientes que cruzan más de una
fuente. Fuera de alcance (YAGNI): expedientes de un solo tribunal, cruces con
otras familias, y **deshacer** una separación desde la interfaz.

## Modelo de datos

**Se conservan sin cambios:**

- `case_links` — el expediente en sí.
- `case_link_stages` — cada etapa: `(case_link_id, source_id, radicado)`, con
  `UNIQUE(source_id, radicado)`. Una etapa = una instancia (un radicado). Todas
  las actuaciones de esa instancia se agrupan bajo ella.

**Se agrega:**

- `case_link_separations` — instancias que una persona quitó a mano.
  Columnas: `id`, `source_id` (FK sources), `radicado` (String),
  `created_at`. `UNIQUE(source_id, radicado)`. El emparejador ignora cualquier
  instancia presente aquí.

**Se elimina:**

- `case_link_suggestions` — ya no hay sugerencias pendientes.

## Cómo se arman los expedientes

Reemplaza a `generate_case_link_suggestions*` en `core/db/repository.py`. La
nueva función (ej. `assemble_case_links_for_run` / `assemble_case_links`):

Después de que una corrida termina de guardar sus documentos (hook en
`worker/tasks.py::_finalize_run`) y en el backfill de migración, por cada
`(source_id, radicado)` **nuevo** de una fuente `samai`:

1. Se compara contra todos los grupos `samai` existentes de una **fuente
   distinta**.
2. Por cada coincidencia de al menos `MIN_MATCH_DIGITS` (21) dígitos iniciales,
   **siempre que ninguna de las dos instancias esté en
   `case_link_separations`**, se **unen directamente** con la lógica existente
   `_link_case_group(...)` — que crea el expediente, le agrega la etapa, o funde
   dos expedientes si ambos lados ya existían. Nunca crea una sugerencia
   pendiente.

Propiedades:

- **Idempotente:** `_link_case_group` no duplica etapas ni expedientes; correr
  el armado de nuevo no cambia nada si no hay documentos nuevos.
- **Alcance por corrida:** `assemble_case_links_for_run` solo mira los
  documentos que esa corrida insertó/tocó (vía `run_source_id`), igual que hoy.
- **Tolerante a fallos:** corre dentro de un `try/except` en `_finalize_run`; un
  fallo se registra en el log pero no impide que la corrida se marque como
  terminada.

## Separaciones (quitar una etapa)

Nueva operación en `repository` (ej. `separate_case_link_stage`):

1. Borra la fila de `case_link_stages` correspondiente a esa etapa.
2. Inserta `(source_id, radicado)` en `case_link_separations` (si no está ya).
3. Si el expediente queda con **menos de dos fuentes distintas**, se **disuelve**:
   se borran el `case_link` y sus etapas restantes. Los documentos **no se
   tocan** — solo dejan de estar agrupados como expediente.

El emparejador salta cualquier instancia en `case_link_separations`, así que una
etapa quitada **no se vuelve a unir** en corridas posteriores.

Como el emparejamiento por 21 dígitos casi nunca agrupa mal, esta es una válvula
de seguridad para datos erróneos (ej. un radicado mal capturado). En v1 no hay
"deshacer" la separación desde la interfaz.

## API

**Se agregan / cambian** (`api/routers/case_links.py`):

- `GET /case-links` — lista de expedientes. Por cada uno: fuentes involucradas,
  radicado(s), número de instancias (etapas), total de documentos y rango de
  fechas.
- `DELETE /case-links/{case_link_id}/stages/{stage_id}` — quitar una etapa
  (separación). Devuelve el expediente actualizado, o `204`/indicación de
  disolución si quedó con una sola fuente.
- `GET /case-links/{case_link_id}` — la línea de tiempo. **Se conserva.**

**Se retiran:**

- `GET /case-link-suggestions`, `POST /case-link-suggestions/{id}/confirm`,
  `POST /case-link-suggestions/{id}/dismiss`.
- `POST /case-links` (vinculación manual).

## Frontend

- **Menú y ruta:** "Casos por confirmar" → **"Expedientes"**; `/casos-por-confirmar`
  → `/expedientes`. La página deja de ser una bandeja de pendientes.
- **Lista de Expedientes** (`ExpedientesPage`, reemplaza a `CaseLinksPage`):
  tarjeta/fila por expediente con fuentes, radicado, número de instancias, total
  de documentos y rango de fechas; clic abre la línea de tiempo; estado vacío
  cuando no hay expedientes.
- **Línea de tiempo** (`CaseLinkDetailPage`, enriquecida):
  - Etapas en orden cronológico.
  - Cada documento (actuación) se **abre/descarga** con el mecanismo que ya usa
    Documentos (`GET /documents/{id}/download` y/o la vista previa existente).
  - Botón **"Quitar del expediente"** por etapa, con confirmación previa; al
    quitar, llama a la API de separación y refresca.
- **Nota en Documentos:** se simplifica. Ya no existe el estado "pendiente". Una
  sola nota — *"Parte de un expediente — también aparece en [fuentes] — Ver
  línea de tiempo"* — que aparece en cuanto el documento entra a un expediente.
  Se simplifica `get_case_link_status_for_documents` para devolver solo esa
  información (sin la rama de "pending").
- Se elimina el formulario de "vincular manualmente".

## Migración (una sola vez)

1. Correr el armado sobre los datos existentes (backfill reutilizado): las 29
   sugerencias pendientes actuales son cruces válidos → se arman como
   expedientes; el expediente ya confirmado (Atlántico) se conserva. Resultado
   esperado en desarrollo: **~30 expedientes**.
2. Eliminar la tabla `case_link_suggestions`.
3. `case_link_separations` arranca vacía.
4. En producción: correr la misma migración una vez al desplegar, igual que se
   hizo con el backfill de radicados.

## Pruebas

Pruebas primero; correr por archivo para evitar el bloqueo de la base de pruebas
al combinar muchos archivos en una sola corrida.

**Backend:**

- Armado automático: una corrida/backfill con un cruce de 21 dígitos entre
  fuentes crea el expediente + etapas de una vez, sin estado pendiente; una
  instancia nueva de un proceso ya existente se le suma.
- Separaciones: una instancia separada **no** se vuelve a unir en corridas
  posteriores.
- Quitar etapa: borra la etapa, registra la separación, y disuelve el expediente
  si queda con una sola fuente (sin tocar documentos).
- Lista de expedientes: resumen correcto (fuentes, instancias, documentos,
  fechas).
- Línea de tiempo: sigue mostrando las etapas con sus documentos.
- Nota en Documentos: solo la nota de "parte de un expediente".
- Migración: arma los expedientes a partir de los datos existentes.

**Frontend:**

- Página "Expedientes": lista y estado vacío.
- Línea de tiempo: abrir documentos y botón "Quitar del expediente".
- El menú muestra "Expedientes".
- Nota simplificada en Documentos.
