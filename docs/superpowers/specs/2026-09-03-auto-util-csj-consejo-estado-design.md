# Auto-"útil" para CSJ y Consejo de Estado

**Fecha:** 2026-09-03
**Tipo:** cambio acotado (bounded)

## Qué cambió

Los documentos de la CSJ y del Consejo de Estado entran marcados como `useful`
automáticamente (nuevo o republicado), igual que ya pasaba con la Corte
Constitucional. Las demás fuentes siguen entrando como `pending`.

El mecanismo ya existía: una fuente con
`family_params = {"auto_review_status": "useful"}` hace que
`worker.scrape_source_task` inserte sus documentos con `review_status="useful"`
en vez de `"pending"` (líneas ~509 y ~521 de `worker/tasks.py`, para alta y
republicación respectivamente). El key es metadata de orquestación: no se pasa
al constructor del scraper (`worker/tasks.py:318`).

## Alcance

- **CSJ** (`family_key="corte_suprema"`, fuente `"CSJ"`): toda la fuente.
- **Consejo de Estado** (`family_key="samai"`, fuente `"Consejo de Estado"`):
  solo esa fuente. Los 27 Tribunales Administrativos de la misma familia
  siguen en `pending` (revisión manual).

## Cambios

### 1. `core/seed.py` — entornos nuevos

- CSJ: `family_params={}` → `{"auto_review_status": "useful"}`.
- En el loop de `SAMAI_CORPS`: se agrega `auto_review_status: "useful"` a
  `family_params` solo cuando `corp_name == "Consejo de Estado"`, conservando
  `corp_code`/`corp_name`.

### 2. Migración `07ba6cc26b17` — config de las fuentes en entornos existentes

`create_source_if_missing` no actualiza filas ya creadas, así que una migración
de datos (mismo patrón que `d071af46dc25`) aplica el cambio a dev y prod:

```sql
UPDATE sources
SET family_params = family_params || '{"auto_review_status": "useful"}'::jsonb
WHERE name IN ('CSJ', 'Consejo de Estado');
```

El `||` de JSONB fusiona la clave sin borrar `corp_code`/`corp_name`. La
bajada (`downgrade`) hace `family_params - 'auto_review_status'`. El deploy ya
corre `alembic upgrade head`, así que se aplica solo.

### 3. Migración `7509921b8e2b` — backfill de los documentos ya guardados

Encadenada tras `07ba6cc26b17`. Marca como `useful` los documentos ya
guardados de CSJ y Consejo de Estado que **no** lo estén — tanto `pending`
como `not_useful` (la política es "todo lo de esas cortes es útil", sin
excepciones), fijando `reviewed_at = now()`:

```sql
UPDATE documents d
SET review_status = 'useful', reviewed_at = now()
FROM sources s
WHERE s.id = d.source_id
  AND s.name IN ('CSJ', 'Consejo de Estado')
  AND d.review_status <> 'useful';
```

Idempotente (el `<> 'useful'` la vuelve no-op en corridas siguientes). El
`downgrade` es no-op a propósito: no se guarda el estado previo de cada fila,
así que volver a `pending` en masa borraría decisiones manuales.

## Interacción con la propagación de "útil" a las actuaciones

Consejo de Estado es "familia con actuaciones". Si todos sus documentos entran
`useful`, cada grupo de actuaciones queda uniforme, así que la propagación al
marcar y `heredar_review_status_de_actuaciones_existentes` son no-ops. Marcar
una actuación `not_useful` sigue arrastrando a todo el caso (comportamiento
buscado). Consistente.

## Cómo aplicar en producción

Solo `alembic upgrade head` (el deploy ya lo corre): la migración
`07ba6cc26b17` pone el `auto_review_status` en las dos fuentes y `7509921b8e2b`
marca el histórico. No hay script manual.

## Pruebas

- `tests/test_seed.py` — CSJ y Consejo de Estado quedan con
  `auto_review_status == "useful"`; los Tribunales Administrativos no.
- `tests/test_tasks.py` (preexistentes) — el worker aplica `auto_review_status`
  en alta y en republicación, y no lo pasa al scraper.
