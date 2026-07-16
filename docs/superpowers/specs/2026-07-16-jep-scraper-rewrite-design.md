# Reescritura del scraper de JEP (searchadv) — Diseño

Fecha: 2026-07-16

## Contexto y objetivo

El scraper de JEP (`core/scrapers/families/jep.py`) usa hoy `GET https://relatoria.jep.gov.co/listarProvidecias`, un listado plano que trae **todos** los documentos de una sola vez (29,794 en total al momento de esta investigación) y que solo expone una fecha con precisión de **año** (`fecha: 2020`, sin mes ni día). Esto tiene dos consecuencias reales:

1. Un run pedido para un rango de fechas específico (ej. "2026-06-01 a 2026-06-29") en la práctica trae **todo el año** completo, porque el filtro interno solo compara años.
2. El "tipo" de documento (Auto, Sentencia, Resolución, etc.) no viene como campo — se adivina parseando el prefijo del nombre de archivo con una lista de reglas manuales (incluyendo un typo real de la fuente, "resolicion").

Investigando el sitio público de JEP (`relatoria.jep.gov.co`, una SPA de React) se encontró un endpoint distinto, ya usado por su propio buscador avanzado, que no tiene ninguna de estas dos limitaciones: `POST https://relatoria.jep.gov.co/searchadv`. No requiere credenciales (se probó explícitamente sin enviar ningún header de autenticación) y devuelve, por cada documento, una fecha de decisión completa (`fecha_documento`, AAAA-MM-DD), una fecha de publicación real y separada (`fecha_publicacion`), y un tipo de documento estructurado (`tipo_documento`) — sin necesidad de adivinar nada.

Este diseño reemplaza por completo la fuente de datos del scraper de JEP, en el mismo archivo y con el mismo `family_key` ("jep") — hoy no hay ningún documento de JEP guardado en la base, así que no hace falta ninguna migración de datos existentes.

## Arquitectura

### Endpoint

```
POST https://relatoria.jep.gov.co/searchadv
Content-Type: application/json

{
  "alguna_palabra": "", "todas_palabras": "", "frase_exacta": "", "ninguna_palabra": "",
  "anio": "<año, obligatorio>",
  "sala_seccion": "", "tipo_documento": "",
  "page": <número de página, 1-indexado>,
  "per_page": 200
}
```

- `anio` es obligatorio — con todos los campos vacíos (incluyendo `anio`) el endpoint devuelve `reponse: null` / total 0, no un listado completo. Por eso la iteración es siempre año por año, igual que ya hace `listarProvidecias` internamente hoy (aunque ahí no hace falta pedirlo, porque trae todo de una).
- Respuesta: `data["reponse"]["hits"]["total"]["value"]` (entero) y `data["reponse"]["hits"]["hits"]` (lista de resultados, cada uno con un objeto `_source`).
- Tamaño de respuesta proporcional a `per_page`: 100 documentos ≈ 3.4 MB (medido con datos reales de 2024, que tiene textos más largos que otros años). Un año completo con `per_page` muy alto (ej. 5000) puede pesar 150-200+ MB en una sola respuesta — por eso se pagina con `per_page=200` en vez de pedir todo de una vez.
- Sin credenciales: se probó explícitamente sin mandar ningún header de autenticación y funciona igual.

### Iteración

Por cada año que cubra el rango `[fini, ffin]` pedido (ej. un rango que cruce diciembre-enero implica pedir dos años), se pagina con `per_page=200` hasta que una página devuelva menos de 200 resultados (o se agote el total reportado). El filtrado preciso por fecha ocurre **después**, del lado del cliente:

1. Se piden todas las páginas del año.
2. Por cada documento, se descarta si `fecha_documento` cae fuera de `[fini, ffin]` — así el resultado final respeta el rango exacto pedido, aunque el servidor solo filtre por año.

`stop_event` se revisa entre cada página (no solo entre años) — el código actual no lo revisa en absoluto dentro de su único loop, así que esto es una mejora real de capacidad de cancelación, no solo paridad.

### Mapeo de campos (`_source` del hit → `RawDocModel`)

| `RawDocModel` | Campo de `_source` | Notas |
|---|---|---|
| `title` | `radicado_documento` | |
| `tipo` | `tipo_documento` | Campo directo — ya no se adivina por regex del nombre de archivo. Si viene vacío/ausente, se guarda como cadena vacía (mismo comportamiento que el código actual cuando no puede inferir el tipo). |
| `seccion` | `sala_seccion` | |
| `f_providencia` | `fecha_documento` | Ya viene en formato `AAAA-MM-DD`, no hace falta ancla al 1 de enero como con el endpoint actual. |
| `f_public` | `fecha_publicacion` | Viene como timestamp completo (`2021-01-27T05:00:00.000000Z`) — se recorta a los primeros 10 caracteres (`AAAA-MM-DD`) para cumplir el formato estricto que exige `worker/tasks.py::_parse_date`. Si está ausente, cae a `fecha_documento` (mismo patrón de fallback que ya usa Corte Constitucional entre `prov_f_public`/`prov_f_sentencia`). |
| `link.url` | `hipervinculo` (normalizado) | `hipervinculo` viene inconsistente: a veces con "/" inicial (ej. `/documentos/providencias/1/1/...`), a veces sin (ej. `documentos/providencias/6/1/...`) — se normaliza quitando cualquier "/" inicial y anteponiendo siempre `https://relatoria.jep.gov.co/` con un solo separador. |
| — (identificador de deduplicación/path) | `providencia_id` | Reemplaza al `id` que usa el código actual — mismo problema que ya resuelve hoy (el mismo `radicado` se reutiliza entre el Auto, su Salvamento/Aclaración de Voto y la Sentencia), pero con el campo correcto de la nueva fuente. |

`method` del link sigue siendo `"GET"` — no cambia el mecanismo de descarga, solo de dónde sale el listado.

## Manejo de errores

- **Error de red / status HTTP no-200**: se lanza una excepción con el código y el cuerpo de la respuesta (mismo patrón ya usado por Corte Constitucional y el JEP actual), capturada por el worker (`worker/tasks.py`), que marca el `run_source` como `failed`.
- **Respuesta no es JSON válido**: excepción con los primeros 500 caracteres del cuerpo recibido (mismo patrón que ya usa el JEP actual para este caso).
- **`reponse` es `null`**: se trata como "sin resultados para ese año" (lista vacía), no como error — puede pasar si `anio` quedara vacío por algún bug, pero no debería ocurrir en la práctica ya que siempre se manda un año real.
- **`fecha_documento` ausente en un documento**: se descarta ese documento — sin esa fecha no hay forma de saber si cae dentro del rango pedido, y es más seguro omitirlo que asumirlo dentro de rango.
- **`fecha_publicacion` ausente**: cae a `fecha_documento` (ver tabla de mapeo arriba).
- **`tipo_documento` ausente o vacío**: se guarda como cadena vacía.
- **`providencia_id` repetido** dentro de la misma corrida (se observó 1 caso repetido en una muestra real de 2,996 documentos de 2020): se deduplica con un set en memoria durante la corrida completa (mismo patrón que ya usa el código actual, con la clave correcta).

## Testing

- Un año con varios documentos: verifica el mapeo completo de campos (`title`, `tipo`, `seccion`, `f_public`, `f_providencia`, `link.url`, `save_path`).
- Filtrado preciso por fecha: un documento con `fecha_documento` dentro del rango pedido y otro fuera del rango (pero mismo año) — verifica que solo se conserva el que corresponde.
- Normalización de `hipervinculo`: un documento con "/" inicial y otro sin él — verifica que ambos arman la misma URL final.
- Paginación: una respuesta con más de una página (mock con `total` mayor a lo que trae la primera página) — verifica que se siguen pidiendo páginas hasta agotar el total.
- Deduplicación por `providencia_id` repetido dentro de la misma corrida.
- `fecha_publicacion` ausente cae a `fecha_documento`; documento con `fecha_documento` ausente se descarta.
- `stop_event` ya seteado antes de empezar corta inmediatamente (test ya existente, se mantiene).
- Rango de fechas que cruza dos años (ej. diciembre 2025 a enero 2026): verifica que se piden ambos años (`anio=2025` y `anio=2026`).

## Fuera de alcance

- No se investigan ni se usan los otros endpoints relacionados encontrados durante la exploración (`searchquery` de texto libre, `searchqueryfilter`) — `searchadv` cubre completamente la necesidad de listar por rango de fechas con metadata rica.
- No se agrega soporte de `on_progress` (el parámetro existe en la firma de `scrap()` pero ni el código actual de JEP ni el de Corte Constitucional lo usan realmente — no se introduce ese comportamiento aquí tampoco, se mantiene la paridad de la firma).
- No se cambia nada del mecanismo de descarga/conversión de archivos (`Downloader`, `WordConverter`) — los documentos siguen llegando como PDF o DOCX tal como ya lo maneja el pipeline existente (incluyendo la previsualización ya construida, que ya soporta ambos formatos).
