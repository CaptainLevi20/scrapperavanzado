# Complementar el título de Consejo de Estado con el número entre paréntesis de la primera página

## Contexto

La fuente **Consejo de Estado** (familia `samai`, `core/scrapers/families/samai.py`) arma hoy el título de cada documento así:

```
{radicado}({sigla_de_clase})
```

Ejemplo: `25000-23-37-000-2021-00423-01(NRD)`.

Ese formato está bien y no cambia. Pero al revisar el contenido real de los documentos (primera página del PDF), se encontró que algunos — no todos — traen junto al radicado un número adicional entre paréntesis que no aparece en la tabla de resultados de SAMAI, solo dentro del propio documento:

```
Radicación  25000-23-37-000-2021-00423-01 (30146)
```

Se validó contra 16 documentos reales descargados: el patrón aparece tal cual (radicado + espacio + número entre paréntesis) en un **subconjunto pequeño** de los casos (1 de 16 en la muestra) — no es un dato que la fuente entregue siempre. Cuando aparece, debe añadirse al título final, entre el radicado y la sigla:

(Nota post-implementación: la muestra de 16 subestimó tanto la frecuencia como la variedad real. Al correr el backfill contra los 1,056 documentos existentes aparecieron **428** (40.5%) — bastante más que la muestra inicial. Detectado por el usuario revisando documentos reales después del primer backfill, en dos rondas de corrección:
1. El número no siempre son solo dígitos: también aparece como "3104-2023" (número-año) y "74.604" (con punto de miles), y en un caso apareció "(principal)" — que no es un número de caso sino la indicación de "cuaderno principal" y se descarta.
2. El radicado dentro del PDF no siempre usa guion como separador — a veces aparece con espacios ("11001 03 25 000 2025 00135 00"), mismos dígitos exactos que el de la tabla SAMAI.

Ambas corregidas en la misma rama antes de mergear — ver `_numero_extra_desde_texto` en `core/scrapers/families/samai.py`.

Aparte, se encontraron 7 documentos (~1%) donde el radicado dentro del PDF tiene dígitos genuinamente distintos a los de la tabla SAMAI (no solo el separador) — posible typo del propio sitio, o en 2 de los 7 podría tratarse de una actuación real distinta. Por decisión explícita del usuario, estos se dejan sin el número extra: el riesgo de pegar mal un dato no vale la pena para un 1% de los casos.

Tercera corrección (2026-08-04): el punto de miles del número (ej. "74.604") se quita del título final — queda "74604", no "74.604". `_numero_extra_desde_texto` ya no lo incluye al extraerlo. Los 76 documentos que el backfill ya había complementado con el punto (antes de esta corrección) se arreglan con la nueva función `backfill_quitar_puntos` en `core/backfill_ce_titles.py`, que solo corrige el texto ya guardado — no vuelve a descargar el PDF.)

```
25000-23-37-000-2021-00423-01(30146)(NRD)
66001-23-33-000-2017-00141-01(3104-2023)(NRD)
```

## Alcance

- Aplica **solo** a la fuente Consejo de Estado (`corp_code == "1100103"`), no a los 27 Tribunales Administrativos que comparte la misma clase `ScrapTribunales`.
- Aplica hacia adelante (documentos que se descarguen desde ahora) **y** a los 1,056 documentos de Consejo de Estado ya guardados en la base de datos, mediante un script de una sola corrida.
- No se toca el formato de título de Tribunales Administrativos.
- No se re-evalúa el título en descargas futuras de un documento que ya existe (republicaciones) — ver "Fuera de alcance" más abajo.

## Mecanismo (reutiliza infraestructura existente)

El proyecto ya tiene un mecanismo para esto exacto: la bandera `title_unverified` en `RawDocModel` y el hook `BaseScrapper.resolve_unverified_document(doc, local_path, content_type)`, que el worker llama justo después de descargar un documento, con el archivo aún en disco (`worker/tasks.py:93-96`). `core/scrapers/families/corte_suprema.py` ya usa este mismo mecanismo para recuperar el título real desde la primera página del PDF cuando la metadata no alcanza.

Se reutiliza tal cual, sin cambiar el hook ni el modelo:

1. En `_parse_row`, cuando `corp_code == _CONSEJO_DE_ESTADO_CORP_CODE`, el `RawDocModel` se construye con `title_unverified=True`.
2. `ScrapTribunales` implementa `resolve_unverified_document`:
   - Extrae el texto de la primera página del PDF descargado (`pypdf`, ya es dependencia del proyecto — usado igual en `corte_suprema.py`).
   - Recupera el radicado a partir del propio `doc.title` (que en este punto es `{radicado}` o `{radicado}({sigla})` — se separa con una expresión regular).
   - Busca en el texto el patrón `{radicado}\s*\((\d+)\)`.
   - Si lo encuentra, reconstruye el título insertando `({número})` entre el radicado y la sigla (o al final si no hay sigla).
   - Si no lo encuentra, o falla la lectura del PDF (documento escaneado sin capa de texto, error de lectura), el título se deja exactamente como está — nunca lanza error hacia el worker.
3. Si `title_unverified` es `False` (todo lo que no sea Consejo de Estado), el hook nunca se invoca — sin cambio de comportamiento para Tribunales Administrativos.

## Backfill de los 1,056 documentos existentes

Nuevo script `core/backfill_ce_titles.py`, siguiendo el patrón de scripts de una sola corrida usado en otros backfills de este proyecto (SessionLocal directo, idempotente, ejecutable con `python -m`):

- Recorre los documentos cuya fuente es `Consejo de Estado`.
- Para cada uno, descarga el PDF ya guardado en MinIO (`core/storage.py::download_file`, sin volver a golpear el sitio de SAMAI).
- Reutiliza la misma función de extracción/regex que `samai.py`.
- Si encuentra el número **y el título actual todavía no lo tiene** (chequeo de idempotencia: el título ya no debe tener un grupo numérico entre paréntesis justo después del radicado), actualiza el título vía `repository.update_document_title`.
- Se puede correr más de una vez sin duplicar ni dañar nada.
- Se ejecuta manualmente una vez contra la base de datos real después de implementar: `.venv/Scripts/python -m core.backfill_ce_titles`.

## Fuera de alcance

- Un documento que ya existe en la base y vuelve a listarse (chequeo de republicación, `checks_for_republication=True` en esta familia) **no** actualiza su título aunque `resolve_unverified_document` se ejecute de nuevo — `archive_and_replace_document` (la función que persiste ese caso) no incluye `title` entre los campos que actualiza. Esto ya es el comportamiento actual del sistema para cualquier campo de metadata en una republicación, no algo que este cambio introduzca ni corrija. Si en el futuro se necesita que una republicación también actualice el título, es un cambio aparte.
- No se agrega este número a los Tribunales Administrativos.
- No se busca el número en páginas distintas a la primera.

## Interacción con el agrupado de casos (detectada en revisión, ya corregida)

`core/utils.py::SAMAI_CASE_TITLE_PATTERN` es el patrón que usa el sistema para reconocer "este título es un caso de Consejo de Estado" y así agrupar sus actuaciones y mostrar el badge de "N actuaciones" (`core/db/repository.py::collapse_case_families`, `api/routers/documents.py::case_document_count`). Un título complementado tiene un grupo de paréntesis adicional (`{radicado}({número})({sigla})`), así que ese patrón tuvo que ampliarse para seguir reconociéndolo — y para no confundir un radicado sin sigla conocida que solo trae el número (`{radicado}({número})`, sin sigla real) con un caso genuino. Esto se corrigió como parte de esta misma implementación (no es un cambio aparte) porque afecta directamente a los 217 documentos que el backfill complementó.

## Pruebas

`tests/families/test_samai.py`:
- Título se complementa cuando el patrón aparece en la primera página.
- Título se deja igual cuando el patrón no aparece.
- Título se deja igual cuando la lectura del PDF falla (excepción controlada).
- El radicado aparece en el texto pero sin paréntesis después (no debe confundirse con una coincidencia).
- Caso sin sigla de clase (radicado sin `(SIGLA)`) también se complementa correctamente.
- Un Tribunal Administrativo nunca dispara `resolve_unverified_document` (title_unverified sigue en `False`).

`tests/test_backfill_ce_titles.py` (nuevo):
- Documento con el patrón en su PDF se actualiza.
- Documento sin el patrón no se toca.
- Correr el backfill dos veces seguidas no duplica el número en el título.

## Archivos

**Modificados:**
- `core/scrapers/families/samai.py` (extracción + hook `resolve_unverified_document` + `title_unverified=True` para Consejo de Estado)
- `tests/families/test_samai.py`

**Nuevos:**
- `core/backfill_ce_titles.py`
- `tests/test_backfill_ce_titles.py`
