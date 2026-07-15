# Conversión RTF/DOC/DOCX → PDF para previsualización — Diseño

Fecha: 2026-07-15

## Contexto y objetivo

El previsualizador de documentos (agregado antes en esta misma sesión) solo puede mostrar PDFs inline — cualquier otro `content_type` cae en el mensaje "vista previa no disponible" con un botón de descarga. Corte Constitucional publica sus providencias en `.rtf`, que los navegadores no pueden renderizar nativamente, así que hoy ningún documento de esa fuente (132 documentos reales verificados) tiene previsualización.

Este diseño agrega conversión a PDF **solo para previsualizar**, generada bajo demanda la primera vez que alguien abre el modal para un documento no-PDF convertible. La descarga sigue sirviendo siempre el archivo original — nunca el PDF convertido.

Explícitamente en alcance:
- Conversión RTF/DOC/DOCX → PDF usando Word vía COM automation (el `WordConverter` que ya existe en `core/downloader.py`, hoy usado para convertir en la dirección contraria — PDF/DOC → RTF — en la familia SAMAI).
- Generación **bajo demanda**: nada se convierte durante el scraping/run; la primera vez que se pide la previsualización de un documento convertible sin PDF cacheado, se genera y se guarda para siempre.
- El mecanismo es **por tipo de contenido, no por fuente** — cualquier documento de cualquier familia con `content_type` RTF/DOC/DOCX puede beneficiarse; Corte Constitucional es el primer caso real que lo ejercita.
- La descarga (`GET /documents/{id}/download`) no cambia en absoluto — siempre sirve el archivo original tal como se guardó durante el scraping.

Explícitamente fuera de alcance:
- Conversión durante el run/scraping (eager, en el momento de la descarga original).
- Conversión de tipos que Word no puede abrir razonablemente (ej. imágenes, texto plano) — esos siguen cayendo en el mensaje de "no disponible" existente, sin cambios.
- Invalidar o regenerar un PDF de preview ya cacheado (no hay flujo de "recrear la preview"; si algo sale mal una vez, el usuario reintenta y se genera de nuevo porque el fallo no llegó a guardar `preview_storage_key`).
- Soporte para convertir en un entorno sin Word/Windows — la conversión seguirá dependiendo de la misma automatización COM que ya usa el resto del proyecto; si falla por esa razón, cae en el mismo camino de error que cualquier otro fallo de conversión.

## Arquitectura

### Modelo de datos

Nueva columna nullable en `documents`:

**`preview_storage_key`** (string, nullable) — cuando tiene valor, apunta a la clave en MinIO del PDF ya generado para previsualización. Cuando es `NULL`, todavía no se generó (o el documento no es de un tipo convertible). No se toca `content_type` ni `storage_key` — esos siguen describiendo el archivo original descargado, usado siempre por `/download`.

### Backend

**Nueva tarea de Celery**, `generate_document_preview_pdf(document_id: int)` (en `worker/tasks.py` o un módulo nuevo junto a él):
1. Busca el documento por id; si no existe o ya tiene `preview_storage_key`, no hace nada (idempotente).
2. Descarga el archivo original desde MinIO (`storage_bucket`/`storage_key`) a un directorio temporal.
3. Convierte a PDF reutilizando `WordConverter.convert(path, "pdf")` — el mismo mecanismo COM que ya usa `Downloader._convert()`, agregando la rama para `target_format == "pdf"` que hoy no existe (el diccionario `_WORD_FORMATS` ya incluye `"pdf": 17`, solo falta la rama en `Downloader._convert`/exponer un método reutilizable para la tarea).
4. Sube el PDF resultante a MinIO bajo una clave derivada de `storage_key` (mismo path, extensión `.pdf`).
5. Actualiza `documents.preview_storage_key` con la nueva clave.
6. Si cualquier paso falla, la tarea termina en error (sin guardar `preview_storage_key`) — el próximo intento de previsualización simplemente la vuelve a encolar.

**Nuevo endpoint**, `GET /documents/{document_id}/preview` (mismo router `documents.py`, mismo requisito de sesión que `/download`):
- Si `content_type == "application/pdf"` → redirige a la URL firmada del archivo original (idéntico a `/download` hoy).
- Si `content_type` es RTF/DOC/DOCX y `preview_storage_key` ya existe → redirige a la URL firmada de `preview_storage_key` (sin tocar Celery).
- Si `content_type` es RTF/DOC/DOCX y `preview_storage_key` es `NULL` → encola `generate_document_preview_pdf.delay(document_id)` y espera el resultado con `.get(timeout=30)`; si termina bien, redirige a la URL firmada recién creada; si se agota el tiempo, responde `504` con detalle `"La vista previa está tardando más de lo esperado, intenta de nuevo"`; si la tarea señala error, responde `502` con detalle `"No se pudo generar la vista previa"`.
- Cualquier otro `content_type` → `404` con detalle `"Vista previa no disponible para este tipo de archivo"`.

### Frontend

`DocumentPreviewDialog` cambia en dos puntos, sin tocar el resto de su lógica (auto-avance, Anterior/Siguiente, marcar Útil/No útil):
- Amplía qué se considera "previsualizable": antes solo `content_type === "application/pdf"`; ahora también `application/rtf`, `application/msword`, y `application/vnd.openxmlformats-officedocument.wordprocessingml.document`.
- Para esos tipos, `fetchDocumentBlob`-equivalente pasa a pedir `/documents/{id}/preview` en vez de `/documents/{id}/download`. El botón "Descargar" del fallback (para tipos verdaderamente no soportados) y el botón "Descargar" de la fila en `DocumentsPage` siguen usando `/download` sin cambios.
- Los estados de carga/error existentes (`Cargando…`, `ErrorBanner` con "Reintentar") ya cubren la espera de la conversión bajo demanda y sus posibles fallos (504/502) sin necesitar UI nueva — un 504/502 cae en la misma rama `blobQuery.isError` que ya existe.

## Manejo de errores

- Timeout esperando la tarea de conversión (ej. el worker está ocupado con un run grande, procesa una tarea a la vez) → `504`, mensaje claro, el usuario reintenta con el botón ya existente.
- Fallo de conversión (Word no pudo abrir el archivo, archivo corrupto, COM no disponible) → `502`, mismo camino de reintento.
- Tipo de archivo no convertible → `404`, mismo mensaje de "vista previa no disponible" que ya existe hoy para cualquier tipo no soportado.
- `/download` no depende de nada de este mecanismo — sigue funcionando igual aunque la conversión de preview falle repetidamente para un documento.

## Testing

- **Backend — endpoint `/preview`**: PDF nativo (redirige directo, sin tocar Celery); RTF con `preview_storage_key` ya cacheado (redirige directo, sin encolar tarea); RTF sin preview (encola la tarea — mockeada en el test para no depender de Word real —, verifica que se guardó `preview_storage_key`, redirige a la nueva URL); timeout esperando la tarea (`504`); fallo de conversión (`502`); tipo no convertible (`404`).
- **Backend — tarea `generate_document_preview_pdf`**: en aislamiento, mockeando `WordConverter` y el cliente S3 (mismo patrón que ya usan los tests existentes de `core/downloader.py`) — conversión exitosa actualiza `preview_storage_key`; documento inexistente o ya con preview no hace nada; fallo de conversión no deja `preview_storage_key` con un valor inválido.
- **Frontend — `DocumentPreviewDialog`**: un documento RTF ahora intenta previsualizarse (llama a `/preview`, no a `/download`) y renderiza el iframe cuando la respuesta es exitosa; un documento de un tipo verdaderamente no soportado sigue cayendo en el fallback de "no disponible"; un error del endpoint `/preview` (502/504) muestra el mismo `ErrorBanner` con reintento ya cubierto por los tests existentes de manejo de errores del blob.
