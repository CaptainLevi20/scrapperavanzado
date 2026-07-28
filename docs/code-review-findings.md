# Hallazgos de revisión de código — IURISYNC

Este documento es el resultado de una **revisión completa del código** del repositorio tal como está hoy en la rama `master` (backend FastAPI + Celery + Postgres, y frontend React/Vite). Se revisó leyendo el código fuente línea por línea — no se ejecutó el sistema ni se hicieron pruebas en vivo, así que **no es una lista exhaustiva de todos los errores posibles**: es la lista de problemas que se pudieron confirmar directamente en el código actual. Cada hallazgo trae primero una explicación en lenguaje sencillo (qué pasa en la práctica, para quien administra el producto) y luego el detalle técnico con archivo y línea exacta, para que un desarrollador pueda ir directo a arreglarlo. Están **ordenados por impacto real**: primero lo que causa pérdida de información o fallas silenciosas en producción, luego seguridad, luego errores de comportamiento, y al final lo menor. Las casillas `- [ ]` sirven para llevar el control de qué ya se corrigió.

**Resumen:** 35 hallazgos — 9 críticos, 5 de seguridad, 10 de correctitud, 11 menores.

---

## Crítico — pérdida de datos o fallas silenciosas en producción

### - [x] 1. La recolección automática diaria busca documentos del día que apenas empieza, así que casi nunca encuentra nada

**En pocas palabras:** el proceso automático corre todos los días a la 1:00 de la mañana (hora Colombia) y le pide a cada fuente "dame los documentos publicados HOY". A esa hora todavía no se ha publicado nada del día, y al día siguiente vuelve a pedir solo el nuevo día — nunca vuelve a mirar el día anterior. Resultado: los documentos que las cortes publican durante la jornada nunca son recogidos por la automatización, y solo aparecen si alguien lanza una corrida manual a mano.

**Detalle técnico:**
- `worker/beat_schedule.py:13` — `repository.create_run(db, triggered_by="scheduled", fini=None, ffin=None)` crea el run sin rango de fechas.
- `worker/tasks.py:120-121` — `fini = _default_date_str(run.fini)` / `ffin = _default_date_str(run.ffin)`, y `_default_date_str` (`worker/tasks.py:34-37`) devuelve `datetime.now(timezone.utc)` cuando el valor es `None`. Es decir, `fini == ffin == hoy`.
- `worker/beat_schedule.py:23` — `crontab(hour=6, minute=0)` con `celery_app.conf.update(timezone="UTC")` (`worker/celery_app.py:13`) = 01:00 hora Colombia (UTC‑5).
- Todas las familias con filtro de fecha preciso (`corte_suprema`, `jep`, `samai`, `rama_judicial`, `cndj`, `adres`, `anh`) filtran estrictamente al rango `[hoy, hoy]`, así que a la 1 AM el conjunto está prácticamente vacío. Nada vuelve a mirar ese día después.
- Arreglo esperado: que el run programado use una ventana retrospectiva (p. ej. `fini = hoy - N días`, `ffin = hoy`) en vez de depender del default de `_default_date_str`.

### - [x] 2. Corte Constitucional: la corrida diaria automática siempre devuelve cero documentos, sin reportar ningún error

**En pocas palabras:** el buscador de la Corte Constitucional nunca se consulta cuando el rango de fechas es de un solo día — que es exactamente lo que produce la corrida automática de cada día. El sistema reporta la fuente como "completada" con 0 documentos, como si de verdad no hubiera nada publicado.

**Detalle técnico:**
- `core/scrapers/families/constitucional.py:63` — `while fecha_local < fecha_final_global:`. Con `fini == ffin` la condición es falsa desde el primer momento y el cuerpo del ciclo nunca se ejecuta; `scrap()` retorna `[]` sin lanzar excepción.
- El worker (`worker/tasks.py:122`) recibe una lista vacía, no entra a ningún ciclo de descarga, y marca el `RunSource` como `"completed"` con `docs_new=0` (`worker/tasks.py:216-224`).
- Debe ser `<=` (o el rango debe ampliarse antes de entrar al ciclo).

### - [x] 3. Los contenedores de producción no traen instalado LibreOffice, así que la vista previa de documentos falla siempre

**En pocas palabras:** para mostrar la vista previa de un documento que no es PDF, el sistema necesita un programa (LibreOffice) que convierta el archivo. Ese programa nunca se instaló dentro de las imágenes que se despliegan en el servidor, así que en producción la vista previa de todo lo que no sea PDF nativo devuelve un error. Corte Constitucional y SAMAI se guardan en RTF, así que esto afecta a la mayoría del archivo.

**Detalle técnico:**
- `Dockerfile` — las tres etapas (`api`, `worker`, `beat`) parten de `python:3.14-slim` e instalan únicamente `requirements.txt` con pip. No hay ningún `apt-get install libreoffice` ni equivalente.
- `core/downloader.py:42-49` — `_find_soffice()` hace `shutil.which("soffice")` y, si falla, prueba `_SOFFICE_FALLBACK_PATHS`, que son rutas **de Windows** (`C:\Program Files\LibreOffice\...`). En el contenedor Linux ambas fallan y lanza `FileNotFoundError`.
- Cadena de fallo: `api/routers/documents.py:204` llama `generate_document_preview_pdf.delay(...)` → `worker/tasks.py:282` `convert_to_pdf_via_libreoffice(local_path)` → `_find_soffice()` explota → el endpoint responde 502 "No se pudo generar la vista previa" (`api/routers/documents.py:209-211`).
- `docs/guia-despliegue-sistemas.md` tampoco menciona instalar LibreOffice en el host.

### - [x] 4. SAMAI: la conversión a RTF nunca funciona en el servidor y el archivo se guarda sin convertir, en silencio

**En pocas palabras:** los documentos de SAMAI (Consejo de Estado y Tribunales Administrativos) deberían guardarse convertidos a RTF. La conversión usa una función que solo existe en Windows, así que en el servidor Linux siempre falla; el plan B que se dispara está mal escrito (le pasa un documento de Word a una herramienta que solo lee PDF) y también falla; y el código entonces devuelve el archivo original sin decir nada. El documento queda guardado en un formato distinto al esperado y además sin vista previa (ver hallazgo 3).

**Detalle técnico (original):**
- `core/scrapers/families/samai.py:296` — `convert_to="rtf_word"` en cada `RawDocModel`.
- `core/downloader.py:176-185` — la rama `rtf_word` intenta `self._word_converter.convert(path, "rtf")`, que hace `import win32com.client` (`core/downloader.py:133`). `pywin32` está declarado en `requirements.txt` como `pywin32>=306; platform_system == "Windows"`, o sea que en Linux no está instalado y el import falla siempre.
- `core/downloader.py:182` — el fallback es `_pdf_to_rtf_fallback(path)`, pero `path` es el archivo **original de Word** (`.doc`/`.docx`), no un PDF. `_pdf_to_rtf_fallback` (`core/downloader.py:104-107`) construye un `PdfReader(str(input_path))`, que lanza excepción con un archivo que no es PDF.
- `core/downloader.py:184-185` — se registra un `logging.warning` y se retorna `path` sin convertir. Como `converted == temp_path`, el bloque de `core/downloader.py:281-285` no se ejecuta: `storage_key` conserva la extensión original y `converted_format` queda en `None`. No se registra ningún `RunError` ni se incrementa `docs_errors`.

**Cómo se resolvió (decisión de negocio, no un parche del bug):** se confirmó con el usuario que **ningún** documento debe convertirse de formato al guardarse — todas las fuentes deben guardar el archivo tal como lo entrega el sitio de origen; la única conversión que debe existir en el sistema es la de vista previa (RTF/DOC/DOCX → PDF bajo demanda, hallazgo 3). En vez de arreglar la conversión rota, se eliminó por completo el mecanismo de conversión al guardar:
- `core/scrapers/families/samai.py` — se quitó `convert_to="rtf_word"`; SAMAI ahora se guarda igual que las demás fuentes, en su formato original.
- `core/models.py` — se eliminó el campo `convert_to` de `RawDocModel` (ya no lo usa ninguna fuente).
- `core/downloader.py` — se eliminaron `WordConverter` (dependía de Word/Windows), `_pdf_to_rtf_fallback`, `_WORD_FORMATS` y la rama de conversión dentro de `download()`. `convert_to_pdf_via_libreoffice` (la de vista previa) queda intacta.
- `requirements.txt` — se quitó `pywin32`, que ya no lo usa nada.
- `worker/tasks.py` — se simplificó `_download_and_upload_one` (ya no hay recursos de Word que cerrar).

### - [x] 5. El tablero muestra una corrida como "completada" aunque alguna fuente haya fallado

**En pocas palabras:** cuando una de las 75 fuentes falla, la corrida completa igual se marca como "completada" con todo en verde. Nadie se entera de que faltan documentos salvo que entre al detalle de la corrida y revise fuente por fuente.

**Detalle técnico:**
- `worker/tasks.py:258-263` — `_finalize_run()` hace `repository.set_run_status(db, run_id, "completed", ...)` de forma incondicional, sin consultar `repository.list_run_sources(db, run_id)` para ver si alguno quedó en `"failed"`.
- El estado `"failed"` sí se escribe a nivel de fuente (`worker/tasks.py:124-126`), pero nunca se propaga al `Run`.
- `frontend/src/pages/RunsPage.tsx:201` y `RunDetailPage.tsx:62` renderizan ese estado tal cual, así que la interfaz refleja el dato incorrecto.

**Cómo se resolvió:**
- `worker/tasks.py` — `_finalize_run()` ahora consulta `list_run_sources` antes de cerrar la corrida: si alguna fuente quedó `"failed"`, el `Run` se marca `"failed"`; si no, `"completed"` como antes.
- `frontend/src/lib/runStatus.ts` (nuevo) — helper `isTerminalRunStatus()` compartido para tratar `"completed"` y `"failed"` como los dos estados finales de una corrida.
- `frontend/src/pages/RunsPage.tsx` y `RunDetailPage.tsx` — el filtro de estado, el sondeo automático (antes solo paraba en `"completed"`, así que una corrida fallida habría quedado consultando al servidor para siempre — el mismo síntoma descrito en el hallazgo 34) y el botón "Cancelar run" ahora usan ese helper. Se agregó la opción "Fallido" al filtro de la lista de runs.
- `StatusBadge` ya tenía listo el estilo rojo para `"failed"`; no hizo falta tocarlo.

### - [x] 6. Si falla la base de datos a mitad de una fuente, esa fuente queda marcada "en curso" para siempre y la corrida nunca termina

**En pocas palabras:** el código protege la parte de "ir a buscar al sitio web", pero no protege la parte de "guardar en la base de datos". Si guardar falla, la tarea muere sin dejar rastro: la fuente queda congelada en "en curso" indefinidamente, y como el paso final de la corrida solo se dispara si todas las tareas terminaron bien, la corrida completa queda colgada. La pantalla se queda refrescando cada 4 segundos eternamente.

**Detalle técnico:**
- `worker/tasks.py:118-127` — la llamada a `scraper.scrap(...)` sí está envuelta en `try/except` que marca `"failed"`.
- `worker/tasks.py:189-214` — el ciclo que llama `repository.insert_document(...)` y `repository.archive_and_replace_document(...)` **no tiene ningún manejo de excepciones**. Una `IntegrityError`, `OperationalError` o desconexión de Postgres propaga hacia arriba.
- `worker/tasks.py:99-226` — el `try` externo solo tiene `finally: db.close()`, sin `except`, así que la excepción sale de la tarea. `set_run_source_status(..., "completed", ...)` (`worker/tasks.py:216`) nunca se ejecuta y el `RunSource` queda en `"running"` (escrito en `worker/tasks.py:116`).
- `worker/tasks.py:250` — `chord((scrape_source_task.s(rsid) for rsid in run_source_ids), finalize_run.s(run_id)).apply_async()` no declara `link_error`, así que ante una tarea fallida el callback `finalize_run` no se ejecuta y el `Run` queda en `"running"` permanentemente.
- Consecuencia en UI: `frontend/src/pages/RunDetailPage.tsx:30` y `frontend/src/pages/RunsPage.tsx:136-140` reencuestan cada 4 s mientras el estado no sea `"completed"` — o sea, para siempre.

**Cómo se resolvió:**
- `worker/tasks.py` — cada escritura a la base de datos (`insert_document`/`archive_and_replace_document`) ahora está protegida individualmente: si falla, se hace `db.rollback()`, se registra como un `RunError` (igual que un error de descarga) y se sigue con el resto de los documentos, en vez de morir ahí mismo.
- Además se agregó una red de seguridad alrededor de todo el bloque de procesamiento: cualquier error inesperado que no sea uno de los ya manejados por documento también deja la fuente en `"failed"` con su `error_message`, nunca colgada en `"running"`.
- Como la tarea ya no revienta sin capturar la excepción, el `chord` sí llega a disparar `finalize_run` con normalidad — no hizo falta tocar el `chord(...)` en sí. La combinación con el hallazgo 5 (que ahora propaga `"failed"` al `Run`) y con el sondeo de la interfaz (que ya para en `"failed"`, no solo en `"completed"`) cierra el ciclo completo: la corrida ya no se queda pegada.
- Límite conocido y aceptado: si la base de datos está totalmente caída desde el arranque mismo de la tarea (antes de marcar la fuente `"en curso"`), no hay forma de registrar ningún estado — porque registrar el error también requiere la base de datos. Ese escenario de caída total es un problema de infraestructura más amplio, no algo que se pueda resolver a este nivel.

### - [x] 7. SAMAI y Corte Suprema se tragan cualquier error del sitio remoto y reportan "completado, 0 documentos"

**En pocas palabras:** si el sitio de SAMAI o el de la Corte Suprema está caído, responde mal o cambia su estructura, el sistema no lo reporta como falla: devuelve una lista vacía (o parcial) y la corrida sale en verde. Un día entero de documentos puede perderse sin que aparezca ninguna alerta en el tablero.

**Detalle técnico:**
- `core/scrapers/families/samai.py:94-99` — `scrap()` envuelve todo `self._scrap_corp(...)` en `except Exception as e: ... return []`. El `on_progress` que recibe el mensaje de error es `None` en producción, porque `worker/tasks.py:122` invoca `scraper.scrap(fini=fini, ffin=ffin)` sin pasar `on_progress`. El error se pierde por completo.
- `core/scrapers/families/samai.py:195-198` y `259-262` — mismo patrón por sección y por fecha: se capturan y descartan.
- `core/scrapers/families/corte_suprema.py:314-319` — el `except Exception` que envuelve todo el ciclo de paginación hace `print(...)` y `stop = True`, y luego `scrap()` retorna los `docs` acumulados hasta ese punto (`core/scrapers/families/corte_suprema.py:321`). Un 500 del servidor a mitad de la paginación produce un resultado parcial que el worker trata como éxito.
- En ambos casos, `worker/tasks.py:216-224` marca `"completed"` porque `scrap()` retornó normalmente. No se crea ningún `RunError` (`repository.add_run_error` solo se llama para errores de descarga individual, `worker/tasks.py:181-183`).

**Cómo se resolvió:** el mecanismo `on_progress` ya existía en **todas** las fuentes (no solo SAMAI/Corte Suprema) precisamente para esto, pero nunca se conectaba a nada — cada mensaje de error que un scraper generaba se perdía en el aire. En vez de reescribir cada fuente, se conectó ese mecanismo ya existente:
- `worker/tasks.py` — se agregó `_ScrapProgressCollector`, un colector con lock (porque SAMAI llama `on_progress` desde su propio grupo de hilos internos, no solo desde el hilo principal) que ahora sí se le pasa a `scraper.scrap(...)`. Todo mensaje se registra en el log; los que traen la palabra "Error" (la convención que ya usaban todas las fuentes) se guardan como `RunError` y suman a `docs_errors` una vez termina `scrap()`.
- `core/scrapers/families/corte_suprema.py` — sus dos `print(...)` (el único de los dos scrapers que no llamaba `on_progress` en absoluto) se cambiaron por `on_progress(...)`, así sus fallas de paginación/servidor también quedan visibles.
- El source sigue en `"completed"` cuando recuperó documentos parciales (no se descarta el trabajo bueno por un error puntual), pero ahora el conteo de `docs_errors` en el tablero deja de estar en cero cuando algo sí falló — la misma señal visible que ya existe para errores de descarga individuales.
- Efecto colateral positivo: como el mismo mecanismo `on_progress` ya lo usan ANE, ADR, ADRES y ANH para sus propios errores recuperados, esas cuatro fuentes también ganan visibilidad real, no solo SAMAI y Corte Suprema.

### - [x] 8. Dos procesos que corran al mismo tiempo sobre un documento republicado pueden pisarse y perder el historial de versiones

**En pocas palabras:** cuando una corte vuelve a publicar un documento que ya teníamos, el sistema guarda una copia de la versión anterior antes de reemplazarla. Si dos corridas tocan el mismo documento al mismo tiempo, ambas leen el mismo estado inicial y la última en escribir borra el trabajo de la primera — se puede quedar una versión archivada apuntando a un archivo que ya no es el correcto. Además, si el documento fue borrado entre medias, el proceso revienta en vez de saltárselo.

**Detalle técnico:**
- `core/db/repository.py:214` — `document = db.get(Document, document_id)` sin verificación de `None`. Si el documento fue eliminado, la línea 216 (`document_id=document.id`) lanza `AttributeError`, que por el hallazgo 6 mata la tarea entera.
- `core/db/repository.py:214-238` — es un read‑modify‑write plano: se lee el `Document`, se crea el `DocumentVersion` con los valores leídos, se sobreescriben los campos y se hace `db.commit()`. No hay `with_for_update()`, ni control de versión optimista, ni restricción única que impida dos archivados simultáneos.
- El disparador real: `worker/tasks.py:211-213` se ejecuta desde varias tareas Celery concurrentes (una por `RunSource`), y `worker/tasks.py:152` lanza hasta 6 hilos por tarea. Dos runs solapados sobre la misma fuente entran aquí en paralelo.

**Cómo se resolvió:**
- `core/db/repository.py` — `archive_and_replace_document()` ahora lee el documento con `SELECT ... FOR UPDATE` (bloqueo a nivel de fila): si dos reemplazos concurrentes del mismo documento chocan, el segundo espera a que el primero termine de escribir y confirmar, en vez de leer el mismo estado viejo y pisarlo. Así el segundo reemplazo siempre archiva correctamente lo que el primero acababa de guardar.
- Si el documento ya no existe (fue borrado entre medias), ahora lanza un error claro y específico (`ValueError: "El documento X ya no existe (fue eliminado)"`) en vez del `AttributeError` críptico de antes — y como el hallazgo 6 ya protege cada escritura individual, este error ya no mata la tarea completa: queda registrado como un error de ese documento puntual y la fuente sigue con el resto.

Verificado con una prueba real contra Postgres (dos hilos, dos sesiones de base de datos separadas) que confirma que el segundo reemplazo efectivamente **espera** a que el primero confirme antes de continuar, en vez de correr en paralelo sin control.

### - [x] 9. El botón "Cancelar run" prácticamente no cancela nada, y la corrida cancelada igual se reporta como "completada"

**En pocas palabras:** cancelar una corrida solo tiene efecto durante los primeros segundos, mientras se está armando la lista de documentos. Una vez que empiezan las descargas —que es la parte larga— la cancelación se ignora por completo y todo sigue corriendo hasta el final. Y al terminar, la corrida cancelada aparece como "completada" en el historial, sin ninguna marca de que se pidió cancelarla.

**Detalle técnico:**
- `worker/tasks.py:138` — `if repository.is_cancel_requested(db, run.id): break` es la **única** verificación, y está dentro del ciclo de enumeración de metadatos (`worker/tasks.py:137-150`).
- `worker/tasks.py:152-214` — el `ThreadPoolExecutor` que hace las descargas, conversiones y subidas no consulta `cancel_requested` en ningún punto. `Downloader.download` sí acepta un `stop_event` (`core/downloader.py:220`, `268`), pero `_download_and_upload_one` (`worker/tasks.py:60`) nunca se lo pasa.
- Ninguna otra tarea de la corrida ya encolada se revoca: `worker/tasks.py:250` no guarda los ids de las tareas del `chord` en ninguna parte.
- No existe un estado `"cancelled"`: `worker/tasks.py:261` escribe `"completed"` sin mirar `run.cancel_requested`.

**Cómo se resolvió:**
- Se agregó el estado `"cancelled"` de verdad, tanto para cada fuente (`RunSource.status`) como para la corrida completa (`Run.status`), y se conectó en tres puntos donde antes se ignoraba la cancelación:
  1. **Antes de empezar** — si la corrida ya estaba cancelada cuando le toca el turno a una fuente (pudo haber estado esperando en la cola detrás de otras), esa fuente ya ni siquiera consulta el sitio remoto: se marca `"cancelled"` de inmediato.
  2. **Mientras arma la lista** — como antes, pero ahora si se cancela ahí queda marcada `"cancelled"`, no `"completada"` como si nada hubiera pasado.
  3. **Durante las descargas** (la parte que antes ignoraba la cancelación por completo) — un hilo liviano en segundo plano revisa cada 2 segundos si se pidió cancelar; en cuanto lo detecta, interrumpe las descargas que están en curso en ese momento (usando el `stop_event` que `Downloader.download` ya sabía recibir, pero que nunca se le pasaba) y deja de iniciar descargas nuevas.
- Los documentos que ya se habían guardado antes de la cancelación **se conservan** — cancelar no descarta trabajo bueno, solo detiene lo que falta.
- `worker/tasks.py` (`_finalize_run`) — si se pidió cancelar la corrida, el `Run` completo se reporta `"cancelled"`, sin importar cómo haya quedado cada fuente individualmente.
- Frontend (`StatusBadge`, `runStatus.ts`, filtro de `RunsPage`) — se agregó el color y la etiqueta "Cancelado", y el estado se suma a los que ya detienen el sondeo automático y esconden el botón "Cancelar run".
- **Lo que se dejó fuera, a propósito:** no se implementó la revocación real de tareas de Celery ya encoladas (`chord(...).apply_async()` sigue sin guardar los ids de tarea). En vez de eso, cada tarea se revisa a sí misma apenas empieza (punto 1 de arriba), así que una tarea todavía en cola para una fuente que no ha empezado termina casi inmediatamente en vez de hacer todo el trabajo — el efecto práctico es casi el mismo, sin la complejidad y fragilidad de manejar revocación real del broker.

Verificado con pruebas reales (hilos + Postgres, no solo mocks) que confirman que una descarga que ya estaba en curso se interrumpe de verdad cuando se cancela a mitad de camino, no solo que las descargas que aún no empezaban se saltan.

---

## Seguridad

### - [x] 10. Cambiar la contraseña no cierra las sesiones abiertas en otros dispositivos

**En pocas palabras:** si alguien se roba la sesión de un usuario (por ejemplo, desde un computador compartido), cambiar la contraseña no lo saca. El intruso sigue dentro hasta 30 días. Cambiar la contraseña es justamente lo que uno hace cuando sospecha que le robaron el acceso, así que es el momento en que más importa.

**Detalle técnico:**
- `api/routers/auth.py:64-72` — `change_password()` verifica la contraseña actual y llama `repository.update_user_password(db, user.id, ...)`. No hay ninguna llamada que borre filas de `sessions` para ese `user_id`.
- `core/db/repository.py:493-498` — el único borrador de sesiones es `delete_session(db, token_hash)`, que borra **una sola** sesión por su token; no existe una función tipo `delete_sessions_for_user(user_id)`.
- Las sesiones viven 30 días y se renuevan con cada request: `core/db/repository.py:452` `SESSION_TTL = timedelta(days=30)` y `core/db/repository.py:485-490` `touch_session()` reextiende `expires_at` en cada llamada autenticada (invocada desde `api/deps.py:22`). Un token robado que se siga usando **nunca expira**.

**Cómo se resolvió:**
- `core/db/repository.py` — nueva función `delete_sessions_for_user(db, user_id, except_token_hash=None)` que borra todas las sesiones de un usuario de una vez (con la opción de conservar una específica).
- `api/routers/auth.py` — `change_password()` ahora, justo después de guardar la nueva contraseña, borra todas las demás sesiones de ese usuario — la sesión desde la que se hizo el cambio se conserva (para que cambiar tu propia contraseña no te saque a ti también), pero cualquier otra sesión (la robada, o cualquier otro dispositivo) queda invalidada de inmediato.

Probado con un flujo real de dos sesiones (dos tokens distintos para el mismo usuario, como si fueran dos dispositivos): tras cambiar la contraseña desde una, la otra deja de funcionar en la siguiente petición, y la que hizo el cambio sigue funcionando.

### - [x] 11. Desactivar un usuario no lo saca del sistema: sigue trabajando con la sesión que ya tenía

**En pocas palabras:** el sistema tiene una marca de "usuario activo/inactivo" que se respeta al iniciar sesión, pero no se vuelve a mirar después. Si se desactiva a alguien (por ejemplo, porque salió de la empresa), su sesión abierta sigue funcionando normalmente hasta que expire sola.

**Detalle técnico:**
- `api/routers/auth.py:46` — el login sí valida: `if user is None or not user.active or not verify_password(...)`.
- `api/deps.py:12-23` — `require_session()` valida el token contra la tabla `sessions` y luego hace `return db.get(User, session.user_id)` **sin comprobar `user.active`**. Todas las rutas protegidas dependen de esta función (`api/routers/documents.py:29`, `runs.py:11`, `sources.py:12`, `bulk_downloads.py:11`).
- Peor aún por el hallazgo 10: `touch_session` renueva el TTL en cada request, así que la sesión de un usuario desactivado que siga usando el sistema jamás caduca.

**Cómo se resolvió:**
- `api/deps.py` — `require_session()` ahora revisa `user.active` (y que el usuario todavía exista) **antes** de dejar pasar la petición, y antes de renovar el TTL de la sesión — así que un usuario desactivado queda bloqueado en la siguientísima petición que haga, no en su próximo intento de iniciar sesión, y su sesión ya no se sigue renovando sola.
- De paso queda cerrado el caso relacionado del hallazgo 21 en este mismo archivo: si el usuario fue borrado (no solo desactivado), ahora también se rechaza la sesión con un mensaje claro en vez de que el `None` se propague y explote más adelante en otra parte del código.
- Nota: hoy no existe ningún botón ni endpoint en el sistema para desactivar a un usuario — solo se puede hacer manualmente en la base de datos. Este arreglo es para cuando esa función exista (o para quien la desactive a mano); la función `delete_sessions_for_user` del hallazgo 10 ya queda lista para que, el día que se agregue un botón de "desactivar usuario", también cierre sus sesiones activas de una vez.

Probado con una sesión real: funciona normal, se desactiva el usuario directamente en la base de datos (como se haría hoy, a falta de un botón para hacerlo), y la siguiente petición con el mismo token queda rechazada de inmediato.

### - [x] 12. El código de invitación para crear cuentas viene con un valor por defecto público ("changeme")

**En pocas palabras:** para crear una cuenta hay que escribir un código de invitación. Si ese código no se configura explícitamente en el servidor, el sistema usa uno por defecto que está escrito en el código fuente del proyecto: `changeme`. Cualquiera que llegue a la dirección del sitio y sepa ese valor podría crearse una cuenta con acceso completo.

**Detalle técnico:**
- `core/config.py:22` — `registration_code: str = "changeme"`. `Settings` (pydantic‑settings) usa este valor si `REGISTRATION_CODE` no está en el entorno ni en `.env`.
- `api/routers/auth.py:33-34` — `if payload.invite_code != settings.registration_code: raise HTTPException(401, ...)` es la única barrera del endpoint público `POST /auth/register`.
- `.env.example` también trae `REGISTRATION_CODE=changeme`; `.env.production.example` sí exige cambiarlo, pero nada en el arranque valida que el valor no siga siendo el default. Recomendación: que la aplicación se niegue a arrancar (o que `/auth/register` responda 403) si `registration_code == "changeme"`.
- Extras del mismo endpoint que conviene atender juntos: no hay límite de intentos (`api/routers/auth.py:30`), la comparación del código no es de tiempo constante, y `RegisterRequest.username` (`api/schemas.py:161`) no tiene longitud mínima ni normalización.

**Cómo se resolvió (los 4 puntos juntos, como sugería el hallazgo):**
- `api/routers/auth.py` — `/auth/register` ahora responde **403** de inmediato si el código sigue siendo `"changeme"`, en vez de aceptarlo como si fuera un código real. Se eligió bloquear solo el registro (no negar el arranque de toda la aplicación) para no arriesgar tumbar el resto del sistema si esto no estuviera bien configurado en producción.
- Se agregó un límite de **5 intentos cada 5 minutos** por dirección IP sobre `/auth/register` (nuevo módulo `core/rate_limit.py`, en memoria — no necesita infraestructura adicional porque el servidor corre como un solo proceso).
- La comparación del código de invitación ahora usa `secrets.compare_digest` (tiempo constante), para que un atacante no pueda deducir el código letra por letra midiendo cuánto tarda en responder cada intento.
- `api/schemas.py` — `RegisterRequest.username` ahora exige mínimo 3 caracteres y le quita los espacios sobrantes al principio/final (así `"  ana  "` y `"ana"` no terminan siendo usuarios distintos).

**Importante para ti:** en este computador de desarrollo, el archivo `.env` no tiene configurado `REGISTRATION_CODE` — así que, con este arreglo, crear una cuenta nueva **localmente** va a fallar con "registro deshabilitado" hasta que se le ponga un valor real (algo que no sea `changeme`) en ese archivo. No lo cambié yo mismo porque es un archivo de configuración/credenciales; avísame si quieres que le ponga un valor.

Probado con pruebas automáticas para los 4 puntos: registro bloqueado con el código por defecto, límite de intentos que efectivamente corta al sexto intento, nombre de usuario corto/solo-espacios rechazado, y espacios sobrantes recortados correctamente.

### - [x] 13. El nombre de archivo que manda el sitio remoto se usa tal cual para armar la ruta de almacenamiento, sin limpiarlo

**En pocas palabras:** cuando se descarga un documento, el nombre del archivo lo decide el servidor de la corte o la entidad — no nosotros. Ese nombre se pega directamente en la ruta donde se guarda el documento, sin quitarle caracteres peligrosos como barras. Un sitio mal configurado (o manipulado) puede hacer que los archivos se guarden en carpetas inesperadas, o que dos documentos distintos terminen escribiéndose encima del mismo nombre y uno de los dos se pierda.

**Detalle técnico:**
- `core/utils.py:29-53` — `extract_filename()` extrae el nombre de la cabecera `Content-Disposition` con `re.search(r'filename="?([^"]+)"?', disposition)` y lo devuelve **sin sanitizar**: `/`, `\`, `:`, `*`, `?` y espacios sobreviven. La rama de respaldo (`core/utils.py:46-53`) puede caer en `opt_title` — el título raspado de la página, texto arbitrario del sitio remoto.
- `core/downloader.py:212-218` — `_resolve_storage_key()` interpola ese valor directo: `doc.save_path.replace("(filename)", filename["filename"])`, o `storage_path(doc.source, doc.f_public, doc.tipo, ...)` (`core/utils.py:56-57`, que es un simple `"/".join`). Ninguna capa valida el resultado.
- Familias afectadas: `adr.py:118`, `adres.py:88`, `ane.py:150`, `anh.py:103` usan la plantilla `"(filename)(extension)"`. (Las demás familias sí sanitizan su propio título con un `_INVALID_PATH_CHARS`, p. ej. `corte_suprema.py:274`, `samai.py:52`, `rama_judicial.py:404` — pero eso no cubre `(filename)`.)
- Dónde se convierte en riesgo de sistema de archivos: `worker/tasks.py:325` `local_path = downloads_dir / document.storage_key` une la clave a una ruta local real, y `worker/tasks.py:347` `zf.write(local_path, arcname=storage_key)` la escribe como ruta dentro del ZIP que se entrega al usuario final. Hoy la fuga fuera del directorio está bloqueada de forma **accidental** (el truncado de `core/utils.py:35`, ver hallazgo 16, corta cualquier nombre que empiece con `..`), no por diseño; el efecto reproducible sin trucos es la creación de subcarpetas no previstas y la colisión/sobreescritura de claves.
- Arreglo esperado: normalizar el nombre a un único segmento seguro (quitar `/`, `\`, `..`, caracteres de control y rutas absolutas) antes de construir `storage_key`, y validar la clave otra vez antes de usarla como ruta local en `build_bulk_download_zip`.

**Cómo se resolvió (los dos pasos que pedía el "arreglo esperado"):**
- `core/utils.py` — `extract_filename()` ahora limpia tanto el nombre como la extensión que manda el sitio remoto antes de devolverlos: quita `/`, `\`, caracteres de control y puntos/espacios sobrantes al principio o final (así un nombre que sea solo `".."` no sobrevive). Si después de limpiar no queda nada útil, usa `"documento"` como respaldo en vez de dejar la clave vacía. Esto protege a **todas** las fuentes por igual, no solo a las 4 que usan la plantilla `(filename)(extension)`, porque `extract_filename()` es el único punto por el que pasa cualquier nombre que venga del servidor remoto.
- Nueva función `is_safe_storage_key()` que valida que una clave no tenga segmentos `..`, no sea una ruta absoluta y no esté vacía. Se usa en **dos** lugares, como pedía el hallazgo:
  1. `core/downloader.py` — justo después de construir la clave de almacenamiento, antes de guardar nada. Si no es segura, se rechaza ese documento puntual (que gracias al hallazgo 6 ya no tumba el resto de la corrida).
  2. `worker/tasks.py` (`build_bulk_download_zip`) — se vuelve a validar cada clave justo antes de usarla como ruta local y como nombre dentro del ZIP, por si un documento antiguo (guardado con una versión del código anterior a este arreglo) todavía tuviera una clave insegura en la base de datos.

Probado con nombres de archivo maliciosos de verdad (`../../etc/passwd.pdf`, nombres con barras invertidas y caracteres de control, una plantilla de guardado que intenta escapar la carpeta de almacenamiento) y confirmando que cada capa los rechaza o los limpia según corresponda.

### - [x] 14. Un usuario que acaba de volver a entrar puede ser expulsado por la respuesta tardía de una petición vieja

**En pocas palabras:** si a alguien se le vence la sesión, vuelve a entrar, y justo llega la respuesta rezagada de una petición que se había hecho con la sesión vieja, el sistema lo saca de nuevo y lo manda al login — aunque acabe de autenticarse correctamente. En una pestaña con varias tablas cargando al tiempo esto se puede repetir.

**Detalle técnico:**
- `frontend/src/api/client.ts:47` — `const token = getStoredToken()` captura el token al iniciar la petición.
- `frontend/src/api/client.ts:58-68` — al recibir un 401, hace `clearStoredToken()` y `unauthorizedHandler?.()` sin comparar el token capturado contra el que hay **ahora** en `localStorage`. Si en el intervalo se ejecutó `login()` (`frontend/src/auth/AuthContext.tsx:52-56` → `setStoredToken(newToken)`), el token nuevo y válido se borra.
- `frontend/src/auth/AuthContext.tsx:21-24` — el handler registrado hace `setToken(null)`, lo que dispara la redirección de `frontend/src/auth/ProtectedRoute.tsx:7`.
- Arreglo esperado: en `client.ts:58`, condicionar la limpieza a `getStoredToken() === token`.

**Cómo se resolvió:** exactamente como decía el "arreglo esperado" — `frontend/src/api/client.ts` ahora, antes de borrar la sesión y avisar, comprueba que el token guardado en este momento sea el mismo con el que se envió esa petición. La petición individual que llegó tarde sigue fallando igual (no se pretende que un 401 real desaparezca), pero ya no le apaga la sesión nueva y válida a nadie.

Probado simulando exactamente la carrera: una petición que "tarda" en responder con 401, mientras en el medio se guarda un token nuevo (como si el usuario hubiera vuelto a iniciar sesión) — la sesión nueva sobrevive y no se dispara la salida al login.

---

## Correctitud

### - [x] 15. Las búsquedas por título pueden devolver resultados equivocados sin avisar

**En pocas palabras:** el buscador de títulos trata algunos caracteres del texto que escribe el usuario como comodines en vez de como letras normales. Los títulos de Rama Judicial están llenos de guiones bajos (`T_BTA_11001_...`), así que buscar un radicado puede traer documentos que no corresponden y el usuario no tiene forma de notarlo.

**Detalle técnico:**
- `core/db/repository.py:301` — `stmt = stmt.where(Document.title.ilike(f"%{title_contains}%"))`. No se escapan los metacaracteres de `LIKE` (`%` y `_`) ni se pasa el parámetro `escape=` que soporta SQLAlchemy.
- El texto llega sin filtrar desde el buscador de la interfaz: `frontend/src/pages/DocumentsPage.tsx:185-188` → `api/routers/documents.py:58` (`title`) → `api/routers/documents.py:79` (`title_contains=title`).
- Los títulos de Rama Judicial se generan con guiones bajos por diseño: `core/scrapers/families/rama_judicial.py:137-138` produce `T_{codigo}_{n[0:5]}_{n[5:7]}_...`. En `LIKE`, cada `_` casa con cualquier carácter.

**Cómo se resolvió:** `core/db/repository.py` — se agregó una función que escapa `%`, `_` y el propio carácter de escape antes de armar el patrón de búsqueda, y se usa el parámetro `escape=` de SQLAlchemy para que la base de datos los trate como texto literal, no como comodines. Ahora buscar `"T_BTA"` solo encuentra títulos que de verdad tienen ese guion bajo ahí, no cualquier título con algún carácter en esa posición.

Probado con un radicado real de Rama Judicial (lleno de guiones bajos) contra un título "señuelo" de la misma longitud pero sin guiones bajos reales — antes del arreglo, el señuelo también aparecía en los resultados; después, ya no. También probado con `%` literal en el texto de búsqueda.

### - [x] 16. El nombre con el que se guarda un archivo se corta mal cuando tiene más de un punto

**En pocas palabras:** al guardar un documento, el sistema separa mal el nombre de la extensión cuando el nombre trae varios puntos. Un archivo llamado `Sentencia.T-123.2024.pdf` se guarda como `Sentencia.pdf`, perdiendo la parte que lo identifica — y dos documentos distintos pueden terminar con exactamente el mismo nombre y sobreescribirse.

**Detalle técnico:**
- `core/utils.py:34-35` — la extensión se toma del **último** punto (`filename.split(".")[-1]`) pero el nombre base se toma hasta el **primer** punto (`filename.split(".")[0]`). Los dos criterios son incompatibles.
- Ejemplo verificable: `"Sentencia.T-123.2024.pdf"` → `{"filename": "Sentencia", "extension": ".pdf"}`. Toda la parte discriminante se pierde.
- Consecuencia aguas abajo: `core/downloader.py:215-218` usa ese `filename` para armar `storage_key`; dos documentos de la misma fuente/fecha/tipo colapsan en la misma clave y `core/storage.py:37` (`client.upload_file`) sobreescribe el objeto anterior en el almacenamiento.
- Comparar con la rama alternativa `core/utils.py:49` que sí usa `rpartition(".")` (criterio correcto) — la inconsistencia está solo en la rama de `Content-Disposition`.

**Cómo se resolvió:** `core/utils.py` (`extract_filename`) — la rama de `Content-Disposition` ahora usa `rpartition(".")` igual que la rama de respaldo, así que el nombre base se toma como "todo lo que hay antes del **último** punto" (el mismo criterio que ya se usa para la extensión), en vez de mezclar "hasta el primer punto" con "desde el último". `"Sentencia.T-123.2024.pdf"` ahora se guarda correctamente como `Sentencia.T-123.2024.pdf`, no como `Sentencia.pdf`.

Nota: este cambio comparte el archivo con el arreglo del hallazgo 13 (limpieza de nombres); ya estaba tocando esa función y era el lugar correcto para corregir ambas cosas juntas.

Probado con el ejemplo exacto del hallazgo (`Sentencia.T-123.2024.pdf`) confirmando que ahora conserva la parte discriminante completa.

### - [x] 17. Los listados aceptan cualquier cantidad pedida, incluso valores absurdos o negativos

**En pocas palabras:** las pantallas de listado piden "dame 50 registros a partir del número N". Nada valida esos números, así que una petición manipulada (o un error) puede pedir un millón de registros de golpe —lo que tumba o congela el servidor— o un número negativo, que hace que la base de datos responda con un error 500.

**Detalle técnico:** ninguno de estos parámetros usa `Query(..., ge=..., le=...)` de FastAPI ni valida el rango a mano:
- `api/routers/documents.py:65-66` — `limit: int = 50, offset: int = 0` (endpoint `/documents`, el más pesado porque incluye el conteo total).
- `api/routers/runs.py:24-25` — `limit: int = 100, offset: int = 0`.
- `api/routers/sources.py:35-36` — `limit: int = 100, offset: int = 0`.
- `api/routers/bulk_downloads.py:22` — `limit: int = 50, offset: int = 0`.
- Todos llegan tal cual a `.limit(limit).offset(offset)` en `core/db/repository.py:45`, `92`, `176`, `344`. Postgres rechaza `LIMIT`/`OFFSET` negativos con error, que se convierte en 500 sin mensaje útil.

**Cómo se resolvió:** se agregó exactamente la validación que pedía el hallazgo (`Query(..., ge=..., le=...)`) a los 4 endpoints, cada uno manteniendo su valor por defecto actual:
- `/documents` y `/bulk-downloads`: `limit` entre 1 y 200.
- `/runs` y `/sources`: `limit` entre 1 y 500.
- `offset` en los 4: nunca negativo.
- Confirmé que ninguna pantalla del sistema pide hoy más de 100 registros de una vez, así que este límite no afecta el uso normal — solo bloquea valores fuera de lo razonable.

Ahora una petición fuera de rango responde con un error 422 claro y estándar de FastAPI, en vez de un 500 genérico de la base de datos (o, peor, de verdad intentar traer un millón de filas).

Probado con offsets negativos, límites en cero, negativos, y absurdamente grandes (un millón) contra los 4 endpoints — todos responden 422 en vez de fallar feo o ejecutarse.

### - [x] 18. Contar cuántos documentos hay obliga a cargar todos los documentos en memoria en cada consulta

**En pocas palabras:** cada vez que se abre o filtra la pantalla de Documentos, el sistema trae de la base de datos **todos** los documentos que coinciden solo para poder decir "Total: 12.345", y después vuelve a consultar los 50 de la página. A medida que el archivo crezca, esa pantalla se va a poner cada vez más lenta hasta volverse inusable.

**Detalle técnico:**
- `core/db/repository.py:343` — `total = len(list(db.scalars(stmt).all()))`. Materializa cada objeto `Document` que casa con los filtros (incluyendo el `EXISTS` correlacionado de `collapse_rama_judicial_cases`, `core/db/repository.py:322-341`) en la sesión de SQLAlchemy, solo para contarlos.
- `core/db/repository.py:344-345` — inmediatamente después se vuelve a ejecutar la misma consulta con `.limit().offset()`.
- Se invoca en **cada** carga de `/documents` (`api/routers/documents.py:69`), y la interfaz la dispara con cada tecleo del buscador (`frontend/src/pages/DocumentsPage.tsx:109`, el `title` está en la `queryKey`).
- Debería ser `db.scalar(select(func.count()).select_from(stmt.subquery()))`.

**Cómo se resolvió:** exactamente como sugería el hallazgo — `core/db/repository.py` ahora cuenta con `db.scalar(select(func.count()).select_from(stmt.subquery()))`, que le pide a la base de datos que cuente las filas ella misma, sin traer cada documento completo hasta el servidor solo para contarlo. Todos los filtros (incluida la lógica especial de Rama Judicial) siguen aplicándose igual, porque el conteo usa la misma consulta filtrada, solo que envuelta para contar en vez de traer datos.

Probado con las mismas pruebas que ya cubrían todos los filtros y la lógica de colapso de Rama Judicial (todas siguen dando el mismo resultado), más una prueba nueva que confirma que el total refleja **todas** las coincidencias aunque la página visible solo muestre unas pocas.

### - [x] 19. Si dos servicios arrancan al mismo tiempo, la carga inicial de fuentes puede reventar

**En pocas palabras:** el paso que crea las 75 fuentes de la primera vez primero pregunta "¿ya existe?" y después la crea. Si dos procesos hacen eso simultáneamente, los dos preguntan antes de que ninguno haya creado nada, los dos intentan crear la misma fuente, y el segundo falla con un error de base de datos.

**Detalle técnico:**
- `core/seed.py:33-36` — `existing_families = {f.key for f in repository.list_source_families(db)}` y después `repository.create_source_family(...)` para las que faltan.
- `core/seed.py:38` y `40-89` — mismo patrón con `existing_sources = {s.name for s in repository.list_sources(db, limit=10_000)}` seguido de `repository.create_source(...)`.
- `core/db/repository.py:17-22` (`create_source_family`) y `core/db/repository.py:53-58` (`create_source`) hacen `db.add(...)` + `db.commit()` sin `ON CONFLICT DO NOTHING` (a diferencia de `insert_document`, `core/db/repository.py:201`, que sí lo usa).
- El fallo es real y no silencioso: `sources.name` tiene restricción única (`core/db/models.py:37`, `alembic/versions/4bffcba11b73_initial_schema.py` → `sa.UniqueConstraint('name')`) y `source_families.key` es llave primaria, así que la segunda inserción lanza `IntegrityError` y el comando de arranque falla a medias, dejando el catálogo incompleto.
- El escenario ocurre si se ejecuta `python -m core.seed` (`docs/guia-despliegue-sistemas.md:82`) más de una vez en paralelo, o si en el futuro se llama el seed desde el arranque de la API con varios workers de uvicorn.

**Cómo se resolvió:** siguiendo el mismo patrón que ya usa `insert_document` para este exacto problema — `core/db/repository.py` tiene dos funciones nuevas, `create_source_family_if_missing` y `create_source_if_missing`, que insertan con `ON CONFLICT DO NOTHING`. `core/seed.py` ya no pregunta "¿existe?" antes de crear: simplemente intenta insertar cada fuente y familia, y si ya existe, la base de datos ignora esa inserción en silencio en vez de fallar. Esto elimina la ventana de tiempo entre "preguntar" y "crear" donde ocurría la carrera.

Nota: dejé intactas las funciones `create_source`/`create_source_family` que usa el panel para crear una fuente nueva a mano — ahí sí tiene sentido que un nombre duplicado se reporte como error, porque es una acción explícita de una persona, no un proceso de arranque automático.

Probado con una carrera real: 4 hilos con conexiones de base de datos separadas ejecutando la carga inicial exactamente al mismo tiempo — antes esto habría hecho que algunos de los 4 fallaran con un error de base de datos; ahora los 4 terminan sin error y el catálogo queda completo (75 fuentes, 10 familias), sin duplicados.

### - [x] 20. Al corregir a mano el año de un documento en el organizador de archivos, el archivo se copia a la carpeta del año viejo

**En pocas palabras:** en la herramienta que renombra y organiza carpetas de documentos, si el sistema detecta mal el año y el usuario lo corrige manualmente, el nombre nuevo del archivo sí queda con el año corregido — pero el archivo se copia igual dentro de la carpeta del año anterior. Queda archivado en el lugar equivocado.

**Detalle técnico:**
- `frontend/src/lib/formatter/analyze.ts:243-255` — `applyCorrections()` construye la entrada nueva con `{ ...entry, detectedYear: parsePositiveInt(correction.year), detectedNumber: parsePositiveInt(correction.number) }` (líneas 247‑251). El campo `yearFolder` se arrastra sin modificar desde el spread.
- `frontend/src/lib/formatter/copy.ts:26-28` — el destino se elige con `entry.yearFolder ? await outputRoot.getDirectoryHandle(entry.yearFolder, { create: true }) : outputRoot`.
- El nombre final sí usa el valor corregido: `frontend/src/lib/formatter/analyze.ts:123-126` (`computeFinalName` → `buildFileName(config, entry.detectedNumber, entry.detectedYear, ...)`).
- Afecta ambos modos: en el modo plano `yearFolder` se derivó de `detectedYear` (`analyze.ts:93`) y en el modo con subcarpetas es el nombre original de la carpeta (`analyze.ts:51`).

**Cómo se resolvió:** `applyCorrections()` ahora recalcula `yearFolder` cuando el año corregido es realmente distinto del que se había detectado antes. Con cuidado de no romper el caso más común (corregir solo el número, dejando el año tal como ya estaba): ahí `yearFolder` se conserva exactamente igual (por ejemplo `"ACUERDOS 1962"`, con su texto original), y solo cambia a un valor limpio como `"1963"` cuando el año en sí se corrige de verdad.

Mientras probaba esto encontré (con una prueba existente) que mi primer intento del arreglo rompía el caso de "solo corregir el número" — lo ajusté para que compare contra el año que tenía la entrada *antes* de la corrección, no simplemente "si hay una corrección, recalcular siempre".

Probado con: una corrección de año real que mueve el archivo a la carpeta nueva correcta (de punta a punta, incluyendo la copia real del archivo), una corrección de solo número que conserva la carpeta original tal cual, y una corrección que borra el año (queda sin carpeta y vuelve a pedir revisión).

### - [x] 21. Varias funciones de base de datos asumen que el registro existe y revientan con error 500 si no

**En pocas palabras:** varias operaciones internas dan por sentado que el registro que van a modificar todavía existe. Si fue borrado o el identificador es incorrecto, en vez de responder "no encontrado" el sistema devuelve un error genérico 500 — y en el caso del worker, mata la tarea (ver hallazgo 6).

**Detalle técnico:** todos estos hacen `db.get(...)` y usan el resultado sin comprobar `None`:
- `core/db/repository.py:103-104` — `set_run_status()`; alcanzable desde `worker/tasks.py:236` y `worker/tasks.py:261`.
- `core/db/repository.py:145-146` — `set_run_source_status()`; `worker/tasks.py:116`, `124`, `216`.
- `core/db/repository.py:183-185` — `set_bulk_download_status()`; `worker/tasks.py:302`, `308`, `335`, `352`, `362`.
- `core/db/repository.py:214` — `archive_and_replace_document()` (también citado en el hallazgo 8).
- `core/db/repository.py:486-489` — `touch_session()`; se ejecuta en **cada** petición autenticada desde `api/deps.py:22`.
- `core/db/repository.py:502-504` — `update_user_password()`; `api/routers/auth.py:72`.
- `core/db/repository.py:508-510` — `touch_user_last_login()`; `api/routers/auth.py:49`.
- Relacionado: `api/deps.py:23` — `return db.get(User, session.user_id)` puede devolver `None` si el usuario fue borrado pero su sesión no; el `None` se propaga a todas las rutas como si fuera un usuario válido, y explota en `api/routers/auth.py:70` (`user.password_hash`).

**Cómo se resolvió:** `archive_and_replace_document()` ya había quedado resuelta con el hallazgo 8, y `api/deps.py` ya había quedado resuelto con el hallazgo 11 (ambos de pasada, porque tocaban exactamente este mismo código). Para las 5 funciones restantes (`set_run_status`, `set_run_source_status`, `set_bulk_download_status`, `touch_session`, `update_user_password`, `touch_user_last_login` — 6 en total contando `touch_user_last_login`) agregué la misma verificación que ya usaban de ejemplo otras funciones del archivo (como `update_document_review_status`): si el registro no existe, la función simplemente no hace nada en vez de reventar. Revisé también el resto de usos de `db.get(...)` en el archivo para confirmar que no quedaba ninguno más sin esa protección.

Probado confirmando que las 6 funciones ya no lanzan ningún error cuando se les pasa un identificador que no existe.

### - [x] 22. Corte Suprema: el filtro por fecha usa una zona horaria distinta a la de Colombia, así que la ventana de un día está corrida

**En pocas palabras:** al pedir los documentos de un día específico de la Corte Suprema, el sistema compara contra la hora universal, no contra la hora de Colombia. En la práctica eso significa que se pierden los documentos publicados después de las 7 de la noche de ese día, y en cambio se incluyen los de después de las 7 de la noche del día anterior.

**Detalle técnico:**
- `core/scrapers/families/corte_suprema.py:203-204` — `fecha_inicio` y `fecha_fin` se construyen con `datetime.fromisoformat(fini).date()` a partir de cadenas `YYYY-MM-DD` que no llevan zona horaria.
- `core/scrapers/families/corte_suprema.py:239` — `fecha_obj = datetime.fromisoformat(item["fechaCreacion"].replace("Z", "+00:00"))`, es decir un instante en **UTC**.
- `core/scrapers/families/corte_suprema.py:241-245` — se comparan `fecha_obj.date()` (fecha en UTC) contra `fecha_fin`/`fecha_inicio` (fechas pensadas como calendario local). Colombia es UTC‑5, así que la ventana efectiva está corrida 5 horas: un documento creado 20:00 COT del día D queda con fecha UTC D+1 y se descarta con `continue`.
- El mismo desfase alimenta el corte anticipado de paginación en la línea 244 (`stop = True`).
- Debería convertirse `fecha_obj` a la zona horaria de Colombia antes de tomar `.date()`, o construir el rango como instantes UTC.

**Cómo se resolvió:** exactamente como decía el "arreglo esperado" — `core/scrapers/families/corte_suprema.py` ahora convierte `fecha_obj` a la hora de Colombia (`.astimezone(...)`) antes de comparar la fecha, en vez de comparar directamente el día UTC contra el día que pidió el usuario. Usé una zona horaria fija UTC‑5 (no la zona horaria "America/Bogota" del sistema) porque Colombia no tiene horario de verano desde 1993 — el desfase nunca cambia, así que un valor fijo es igual de correcto y no depende de que el servidor tenga instalada la base de datos de zonas horarias.

Efecto colateral bueno: la fecha que se guarda con cada documento (`f_public`) también queda calculada en hora de Colombia ahora, no en UTC — así que la fecha que ve el usuario en el tablero también es la fecha real en que se publicó, no un día antes o después por el desfase.

Probado con dos casos que antes se comportaban mal en sentidos opuestos: un documento publicado a las 8pm hora Colombia (que en UTC ya es el día siguiente) ahora sí se encuentra al pedir el día correcto; y un documento publicado ya entrada la noche pero que en Colombia sigue siendo el mismo día no se incluye de más por error de sobre-corrección.

### - [x] 23. Un documento que aparece dos veces en el mismo barrido sube dos archivos al almacenamiento pero solo se registra uno

**En pocas palabras:** si una fuente lista el mismo documento dos veces en la misma pasada, el sistema lo descarga y lo sube dos veces al almacenamiento, pero en la base de datos solo queda uno. El segundo archivo queda huérfano ocupando espacio para siempre, y el contador de "documentos nuevos" del tablero queda inflado.

**Detalle técnico:**
- `worker/tasks.py:137-150` — el ciclo de enumeración agrega a `pending` cualquier `doc` cuyo `doc_id` no esté aún **en la base de datos**, pero no verifica duplicados dentro de la misma lista `docs`.
- `worker/tasks.py:153-156` y `170-174` — ambas ocurrencias se descargan y se suben (`core/storage.py:37`) antes de tocar la base de datos.
- `worker/tasks.py:191-207` — `repository.insert_document(...)` usa `on_conflict_do_nothing(index_elements=["doc_id"])` (`core/db/repository.py:201`), así que la segunda inserción no hace nada.
- `worker/tasks.py:208` — `docs_new += 1` se ejecuta igual, sin mirar si `insert_document` realmente insertó (la función sí devuelve el `Document`, `core/db/repository.py:204`, pero el resultado se descarta).
- Las familias que sí deduplican por su cuenta (`corte_suprema.py:265-270`, `jep.py:203-206`, `rama_judicial.py:388-401`, `cndj.py:144`) lo hacen porque conocen su fuente; el worker no tiene protección genérica.

**Cómo se resolvió (los dos problemas, no solo uno):**
- `worker/tasks.py` — el ciclo que arma la lista de documentos a procesar ahora recuerda qué `doc_id` ya vio en esta misma pasada; si el mismo documento aparece dos veces, la segunda aparición se descarta ahí mismo, **antes** de descargar nada — así que ya no se sube un archivo huérfano al almacenamiento por duplicado.
- `core/db/repository.py` — nueva función `insert_document_reporting_whether_created()` que sí distingue "acabo de crear esta fila" de "ya existía, no hice nada" (usando `RETURNING` sobre el `INSERT ... ON CONFLICT DO NOTHING`). El worker la usa para solo sumar al contador de "documentos nuevos" cuando de verdad se insertó algo — esto cubre además un caso más raro que la deduplicación por sí sola no alcanza a cubrir: dos corridas distintas tocando la misma fuente al mismo tiempo y compitiendo por el mismo documento.
- La función original `insert_document()` (usada en decenas de pruebas y en otras partes del código) se dejó exactamente igual — el cambio es aditivo, no se tocó su comportamiento.

Probado con un documento que aparece dos veces en la misma pasada: confirmé que solo se descarga una vez (no dos), que solo queda un registro en la base de datos, y que el contador de "documentos nuevos" refleja exactamente 1, no 2.

### - [x] 24. Pedir las versiones de un documento que no existe responde "ninguna" en vez de "no encontrado"

**En pocas palabras:** consultar el historial de versiones de un documento inexistente devuelve una lista vacía, como si el documento existiera pero nunca hubiera sido reemplazado. Es un detalle, pero hace difícil distinguir "no hay versiones" de "ese documento no existe".

**Detalle técnico:**
- `api/routers/documents.py:134-136` — `get_document_versions()` llama directo `repository.list_document_versions(db, document_id)` sin verificar antes que el documento exista (a diferencia de `api/routers/documents.py:127-131`, `154-159`, `162-167`, `170-176`, que sí devuelven 404).
- `core/db/repository.py:241-247` filtra por `DocumentVersion.document_id == document_id` y devuelve `[]`.

**Cómo se resolvió:** `api/routers/documents.py` — `get_document_versions()` ahora hace la misma verificación que ya hacen las otras rutas vecinas de este mismo archivo: si el documento no existe, responde 404 "Documento no encontrado" en vez de una lista vacía.

Probado confirmando el 404 para un documento inexistente, sin afectar el caso legítimo de "documento real que todavía no tiene ninguna versión archivada" (ese sigue respondiendo 200 con lista vacía, como corresponde).

---

## Menor

### - [x] 25. Las tablas muestran "no hay resultados" durante un instante antes de terminar de cargar

**En pocas palabras:** al abrir cualquier listado, aparece por un momento el mensaje "no hay documentos / no hay runs / no hay fuentes" antes de que lleguen los datos. Da la impresión momentánea de que el sistema está vacío.

**Detalle técnico:** todas estas condiciones evalúan `data?.length ?? 0 === 0`, que es verdadero mientras `data` es `undefined` (cargando); ninguna consulta `isLoading` / `isPending`:
- `frontend/src/pages/DocumentsPage.tsx:387`
- `frontend/src/pages/RunsPage.tsx:211`
- `frontend/src/pages/SourcesPage.tsx:129`
- `frontend/src/pages/BulkDownloadsPage.tsx:90`
- `frontend/src/pages/RunDetailPage.tsx:112`

**Cómo se resolvió:** se agregó `!consulta.isLoading &&` delante de cada una de las 5 condiciones — el mensaje de "no hay nada" solo aparece una vez que la primera consulta realmente terminó, no mientras todavía está en camino.

Probado en las 5 pantallas con una respuesta del servidor deliberadamente retrasada: confirmé que el mensaje de "vacío" no aparece mientras se espera la respuesta, y sí aparece correctamente una vez que la respuesta llega vacía de verdad.

### - [x] 26. Abrir rápido dos casos seguidos puede mostrar el contenido del caso equivocado

**En pocas palabras:** al hacer clic en un caso de Rama Judicial se abre una ventana con todas sus actuaciones. Si se hace clic en un caso y enseguida en otro, la ventana puede terminar mostrando las actuaciones del primero, porque no hay control de cuál respuesta llegó de última.

**Detalle técnico:**
- `frontend/src/pages/DocumentsPage.tsx:134-146` — `openCaseDialog()` hace `await fetchDocuments({...})` y luego `setCaseDocuments(chronological)` sin token de cancelación ni verificación de que sea la petición más reciente. Es una llamada suelta, no un `useQuery`, así que React Query no la deduplica ni la descarta.
- Los dos llamadores (`frontend/src/pages/DocumentsPage.tsx:154` y `166`) son manejadores `async` de eventos sin `try/catch`: si `fetchDocuments` falla (red caída, 500), se genera un rechazo de promesa no manejado y la interfaz no muestra nada — el clic simplemente parece no hacer nada.

**Cómo se resolvió (los dos problemas):**
- `openCaseDialog()` ahora lleva un contador que se incrementa en cada clic; al volver la respuesta, si ya se hizo un clic más reciente en otro caso, esa respuesta vieja se descarta en silencio en vez de sobreescribir lo que el usuario ya está viendo.
- Se agregó `try/catch`: si la petición falla, se muestra un mensaje de error visible en vez de que el clic no haga nada.

Probado con la carrera exacta que describe el hallazgo: clic en el caso A (respuesta lenta) seguido de inmediato por clic en el caso B (respuesta rápida) — confirmé que la ventana muestra el caso B, y que la respuesta tardía del caso A no la sobreescribe cuando por fin llega. También probé que una petición fallida muestra un mensaje de error en vez de no hacer nada.

### - [x] 27. Algunos botones de descarga no muestran ningún mensaje cuando la descarga falla

**En pocas palabras:** hay dos botones de descarga que, si fallan, no muestran ningún error. Para el usuario el botón simplemente "no hace nada" y no hay forma de saber por qué.

**Detalle técnico:**
- `frontend/src/pages/BulkDownloadsPage.tsx:26-29` — `handleDownload()` hace `await fetchBulkDownloadUrl(id)` y `await downloadFromUrl(...)` sin `try/catch`. El endpoint puede responder 404 legítimamente (`api/routers/bulk_downloads.py:29-30`, cuando el ZIP ya no está disponible), y `downloadFromUrl` lanza si la URL firmada expiró (`frontend/src/api/documents.ts:156-158`). El componente no tiene ningún estado de error.
- `frontend/src/components/DocumentPreviewDialog.tsx:314-317` — el botón "Descargar" del caso "vista previa no disponible" llama `downloadDocumentFile(...)` directamente en el `onClick`, sin envolver. Contrasta con `handleDownloadRtf`/`handleDownloadPdf`/`handleDownloadOther`/`handleDownloadVersion` (`DocumentPreviewDialog.tsx:176-212`), que sí capturan y muestran `downloadError`.

**Cómo se resolvió:**
- `frontend/src/pages/BulkDownloadsPage.tsx` — `handleDownload()` ahora captura el error y muestra un mensaje visible en vez de fallar en silencio.
- `frontend/src/components/DocumentPreviewDialog.tsx` — el botón suelto ahora reutiliza `handleDownloadOther` (el mismo manejador con `try/catch` que ya usan los demás botones de descarga de este diálogo), en vez de llamar la descarga directo en el `onClick`.

Probado en ambos casos con una descarga que falla: confirmé que aparece un mensaje de error visible en vez de que el botón simplemente no haga nada.

### - [x] 28. El botón "Siguiente" de las tablas se desactiva mirando la página actual, no el total

**En pocas palabras:** en algunos listados el botón de página siguiente se habilita o deshabilita comparando cuántas filas trajo la página actual, no cuántas hay en total — así que puede quedar habilitado en la última página y llevar a una pantalla vacía.

**Detalle técnico:**
- `frontend/src/pages/DocumentsPage.tsx:448` — `disabled={(documentsQuery.data?.items.length ?? 0) < PAGE_SIZE}`, aunque el endpoint sí devuelve `total` (`api/schemas.py:153-157`) y la página ya lo muestra en la línea 437.
- `frontend/src/pages/RunsPage.tsx:221` y `frontend/src/pages/SourcesPage.tsx:144` — mismo patrón; en estos dos casos el backend ni siquiera devuelve un total (`api/routers/runs.py:21` y `api/routers/sources.py:30` retornan listas planas).

**Cómo se resolvió (dos enfoques distintos, según lo que cada endpoint tenía disponible):**
- `DocumentsPage.tsx` — como el backend ya manda `total`, el botón ahora compara la página actual contra ese total real, en vez de mirar cuántas filas trajo la página.
- `RunsPage.tsx` y `SourcesPage.tsx` — como esos dos endpoints no devuelven ningún total (y agregarlo hubiera significado cambiar el contrato de la API en varios lugares), se usó una técnica distinta que no requiere tocar el backend para nada: la pantalla pide una fila de más de las que realmente muestra (51 en vez de 50, por ejemplo). Si esa fila extra llega, es porque hay más — se activa "Siguiente" y esa fila de más nunca se muestra. Si no llega, es porque ya se vio todo.

Probado en las 3 pantallas con el caso exacto que describe el hallazgo (una última página que llega "llena" pero en realidad no tiene nada más después) — confirmé que "Siguiente" queda correctamente deshabilitado, y que sigue habilitado cuando de verdad hay más para ver.

### - [x] 29. La tarea de recolección declara reintentos automáticos que nunca se usan

**En pocas palabras:** la configuración dice "reintenta hasta 2 veces si algo falla", pero el código nunca solicita el reintento, así que esa configuración no hace nada.

**Detalle técnico:**
- `worker/tasks.py:96` — `@celery_app.task(name="worker.scrape_source_task", bind=True, max_retries=2, default_retry_delay=30)`.
- En todo el cuerpo de `scrape_source_task` (`worker/tasks.py:97-226`) no hay ninguna llamada a `self.retry(...)`; `self` solo existe por el `bind=True`. Es configuración muerta que da una falsa sensación de resiliencia.

**Cómo se resolvió (y por qué no de la forma "obvia"):** intenté primero conectar el reintento de verdad (`self.retry(...)` cuando falla `scraper.scrap()`), ya que varias fuentes (Corte Suprema, SAMAI) sí tienen fallos temporales conocidos del sitio remoto que un reintento automático ayudaría a superar sin intervención manual. Al probarlo con el resto de la batería de pruebas, encontré que Celery maneja los reintentos de forma distinta según cómo se invoque la tarea — funciona distinto si se llama directo (como hacen la mayoría de las pruebas de este proyecto) que si se despacha por la cola real, y en las pruebas que combinan `chord` con el modo de pruebas "eager" el reintento se escapaba sin control y tumbaba la tarea en vez de reintentarla. Confirmarlo bien habría requerido levantar un worker de Celery real contra Redis, algo que no era razonable para arreglar un hallazgo "Menor".

Dado ese riesgo real (y ya evité algo parecido en los hallazgos 6 y 9, por la misma razón), la decisión fue **quitar la configuración muerta** en vez de dejarla a medias o forzar algo no verificado: se eliminaron `bind=True`, `max_retries=2` y `default_retry_delay=30` del decorador, y el parámetro `self` (que solo existía por el `bind=True`) de la función. El comportamiento actual —fallar y marcar la fuente como `"failed"` de inmediato— es el mismo de siempre, ahora sin la promesa falsa de que ya reintenta solo.

Confirmé con toda la batería de pruebas que el comportamiento no cambió (una fuente que falla sigue marcándose `"failed"` igual que antes).

### - [x] 30. Las descargas masivas dejan de funcionar si algún día se cambia el nombre del depósito de archivos

**En pocas palabras:** los ZIP de descarga masiva no guardan en qué depósito quedaron; se asume que siempre está el que está configurado hoy. Si esa configuración cambia, los ZIP viejos dejan de poder descargarse.

**Detalle técnico:**
- `worker/tasks.py:349-350` — `upload_file(zip_path, zip_key, content_type="application/zip")` usa el bucket por defecto de `core/storage.py:33` (`settings.s3_bucket`), y solo se persiste `zip_storage_key` (`worker/tasks.py:358`); el modelo `BulkDownload` (`core/db/models.py:82-93`) no tiene columna de bucket, a diferencia de `Document.storage_bucket` (`core/db/models.py:112`).
- `api/routers/bulk_downloads.py:32-35` reconoce el supuesto en un comentario y firma la URL contra `get_settings().s3_bucket`.

**Cómo se resolvió:** exactamente el mismo patrón que ya usa `Document.storage_bucket` para este mismo problema:
- Migración de base de datos nueva que agrega la columna `storage_bucket` a `bulk_downloads` (opcional, para no romper las filas que ya existían antes de este cambio).
- `worker/tasks.py` — ahora sí toma el bucket que `upload_file(...)` devuelve de verdad (antes se descartaba) y lo guarda junto con la clave del ZIP.
- `api/routers/bulk_downloads.py` — al firmar el enlace de descarga, usa el bucket guardado en la fila; solo si una fila antigua no tiene ninguno guardado (porque se creó antes de este arreglo), usa el valor por defecto actual como respaldo.

Probado con una descarga masiva real de punta a punta (confirmando que el bucket queda guardado tal cual lo devolvió la subida), y con las dos situaciones del enlace de descarga: una fila con su propio bucket guardado (debe usar ese, no el actual) y una fila sin bucket guardado (debe usar el actual como respaldo). También verifiqué que la migración de base de datos aplica y se puede deshacer sin problemas.

### - [ ] 31. La fuente CNDJ vuelve a recorrer todo su catálogo completo en cada corrida

**En pocas palabras:** para traer los documentos de un solo día, esta fuente consulta magistrado por magistrado el catálogo entero (unos 20.000 documentos) y luego pide el detalle de cada candidato uno por uno. Es muy lento y castiga innecesariamente al sitio de la entidad en cada corrida diaria.

**Detalle técnico:**
- `core/scrapers/families/cndj.py:90-145` — un `POST` de búsqueda + un `GET` de resultados **por cada magistrado** de la lista, acumulando todo en `all_rows` sin ningún filtro de fecha del lado del servidor.
- `core/scrapers/families/cndj.py:155-188` — luego un `POST` de detalle por cada fila que sobrevive el pre‑filtro por año (`cndj.py:161`), con `timeout=30` cada uno, en serie.
- El filtro real por fecha ocurre recién en `core/scrapers/families/cndj.py:205-206`, después de haber hecho todo el trabajo de red.

**Por qué se dejó pendiente (a propósito, no olvidado):** este caso es distinto a los demás — el problema de fondo no está en nuestro código, sino en una limitación real del buscador del sitio de CNDJ: solo permite buscar "por magistrado" (o por año de radicación del caso), y **no ofrece ninguna forma de pedir "documentos publicados entre estas dos fechas"**, que es justo lo que la fuente necesita. Por eso el código actual trae todo y filtra después — no es un descuido, es la única manera de conseguir el dato correcto con lo que el sitio ofrece.

Evalué dos atajos y los descarté por el mismo motivo en ambos casos: no hay forma de probarlos contra el sitio real de CNDJ desde este entorno, y un error ahí no se nota como una falla — se nota como documentos que dejan de aparecer, en silencio, semanas o meses después:
1. **Usar el filtro "año de radicación" del sitio para pedir menos de entrada.** Riesgo: el año en que se radica un caso no siempre coincide con el año en que se publica la decisión (a veces meses o incluso un año después, según el propio código ya documenta con el margen de holgura de 90 días) — confiar en ese filtro podría perder documentos reales.
2. **Descargar los detalles en paralelo** (como ya hacen otras fuentes) para que sea más rápido. Riesgo: esta fuente reutiliza una sola sesión con un token de seguridad que se va renovando paso a paso durante las búsquedas; compartir esa sesión entre varios hilos a la vez podría romper esa renovación de forma intermitente y difícil de detectar.

Se lo planteé directamente al usuario, y decidimos dejarlo documentado sin tocar el código por ahora, en vez de forzar un arreglo sin poder comprobar que sea seguro.

### - [x] 32. Dos fuentes tienen un tope fijo de páginas: si crecen, los documentos extra se pierden en silencio

**En pocas palabras:** dos fuentes dejan de leer después de 60 páginas de resultados. Si algún día publican más que eso en un rango de fechas, el resto simplemente no se recoge y nadie se entera.

**Detalle técnico:**
- `core/scrapers/families/adres.py:27` — `_MAX_PAGINAS_POR_CATEGORIA = 60`, aplicado en el `while queue and paginas < _MAX_PAGINAS_POR_CATEGORIA` de `adres.py:119`; al agotarse simplemente se sale del ciclo sin señal.
- `core/scrapers/families/anh.py:26` — `_MAX_PAGINAS = 60`, aplicado en `for pagina in range(1, _MAX_PAGINAS + 1)` (`anh.py:51`).
- En ambos casos convendría al menos registrar un `RunError` cuando se alcanza el tope.

**Cómo se resolvió:** ambas fuentes ahora detectan cuándo se quedan sin páginas por recorrer y avisan en vez de quedarse calladas.
- `core/scrapers/families/anh.py` — se agregó una cláusula `else` al ciclo `for pagina in range(1, _MAX_PAGINAS + 1)` que solo se ejecuta cuando el ciclo agota las 60 páginas sin haber encontrado antes una condición natural de parada (última página real, sin más resultados, etc.). En ese caso llama a `on_progress(...)` con un mensaje que contiene la palabra "Error", el mismo mecanismo introducido en el hallazgo 7 (`_ScrapProgressCollector` en `worker/tasks.py`), así que el aviso queda registrado como un `RunError` visible en la corrida.
- `core/scrapers/families/adres.py` — como esta fuente procesa tres categorías por separado (Resoluciones, Circulares, Acuerdos), se agregó una verificación después de cada ciclo `while queue and paginas < _MAX_PAGINAS_POR_CATEGORIA`: si se llegó al tope de 60 páginas y todavía quedaban páginas pendientes en la cola, se reporta un `on_progress` de error indicando en qué categoría ocurrió.
- **Pruebas:** se agregó una prueba automática por cada fuente que simula un sitio con más de 60 páginas de resultados disponibles y confirma que (a) el scraper se detiene exactamente en la página 60 y (b) se emite el aviso de error correspondiente. Las 11 pruebas de `tests/families/test_anh.py` y `tests/families/test_adres.py` pasan, igual que las 362 pruebas de todo el proyecto (`pytest --ignore=tests/test_migrations.py`), sin ninguna falla nueva.

### - [x] 33. Los scrapers escriben sus errores con `print` en vez del sistema de registro

**En pocas palabras:** varios mensajes de error se imprimen en la consola en lugar de guardarse en el registro de la aplicación, lo que hace difícil rastrear qué pasó cuando se revisan los logs del servidor.

**Detalle técnico:**
- `core/scrapers/families/corte_suprema.py:177`, `309`, `318`; `core/scrapers/families/rama_judicial.py:365`, `396-399`.
- El resto del proyecto sí usa `logging` (`worker/tasks.py:17`, `core/downloader.py:180`), así que estos mensajes quedan fuera del formato y del nivel configurados y no llegan a `docker compose logs` con la misma estructura.

**Cómo se resolvió:** se reemplazaron los `print(...)` que quedaban en ambos archivos por el sistema de registro (`logging`) que ya usa el resto del proyecto, con el mismo patrón que `worker/tasks.py` (`logger = logging.getLogger(__name__)`, mensajes a nivel `WARNING`).
- `core/scrapers/families/corte_suprema.py` — el aviso de "no se pudo leer la primera página del archivo para recuperar el título" ahora se registra con `logger.warning(...)`.
- `core/scrapers/families/rama_judicial.py` — los avisos de "error procesando fila" (una fila de la lista con datos inesperados) y "el archivo cambió de tamaño entre listados" ahora también se registran con `logger.warning(...)`.
- Se confirmó que no queda ningún `print(...)` restante en la carpeta `core/`.
- **Pruebas:** se agregaron/ampliaron pruebas automáticas que provocan cada una de estas tres situaciones y verifican, usando el mecanismo estándar de captura de registros de Python (`caplog`), que el aviso efectivamente pasa por el sistema de registro (y no por una simple impresión en consola invisible para los logs del servidor). Las 57 pruebas de `tests/families/test_corte_suprema.py` y `tests/families/test_rama_judicial.py` pasan, igual que las 363 pruebas de todo el proyecto (`pytest --ignore=tests/test_migrations.py`), sin ninguna falla nueva.

### - [x] 34. La pantalla de corridas sigue consultando al servidor indefinidamente si una corrida queda colgada

**En pocas palabras:** mientras una corrida no esté "completada", la pantalla pregunta al servidor cada 4 segundos. Si una corrida se queda pegada (ver hallazgo 6), esa consulta no para nunca mientras la pestaña esté abierta.

**Detalle técnico:**
- `frontend/src/pages/RunsPage.tsx:136-140` — `refetchInterval` devuelve `POLL_INTERVAL_MS` mientras exista algún run con `status !== "completed"`, sin tope de intentos ni de tiempo.
- `frontend/src/pages/RunDetailPage.tsx:30` y `37-42` — mismo patrón para el detalle.
- Como `Run.status` nunca toma el valor `"failed"` (`worker/tasks.py` solo escribe `"running"` y `"completed"`), no hay ningún estado terminal que corte la encuesta ante una falla.

**Cómo se resolvió:** la parte de "nunca hay un estado 'fallido'" ya había quedado resuelta como efecto de arreglos anteriores en esta misma revisión (hallazgos 6 y 9): el sistema ahora sí puede marcar una corrida como `"failed"` o `"cancelled"`, y la pantalla ya dejaba de consultar en esos casos. Quedaba pendiente el caso más difícil: una corrida que se cuelga de verdad porque el proceso que la procesa muere de golpe (por ejemplo, si el contenedor se reinicia o se queda sin memoria a mitad de camino) — en ese caso nunca llega a escribirse ningún estado final, ni "completado" ni "fallido", y antes de este arreglo la pantalla habría seguido preguntando cada 4 segundos para siempre mientras la pestaña estuviera abierta.
- Se agregó un límite de tiempo: si una corrida lleva más de 30 minutos sin llegar a un estado final, la pantalla deja de consultar automáticamente y en su lugar muestra un aviso ("Puede haberse quedado colgado") con un botón para revisar manualmente su estado más reciente. Treinta minutos es bastante más de lo que tarda cualquier corrida real observada hasta ahora en este proyecto.
- Se aplicó tanto en la lista de corridas (`RunsPage.tsx`) como en el detalle de una corrida (`RunDetailPage.tsx`).
- De paso, se corrigió el tipo de datos del frontend que describe los estados posibles de una corrida (`RunStatus`), que todavía no incluía `"failed"` ni `"cancelled"` aunque el sistema ya podía usarlos desde hallazgos anteriores.
- **Pruebas:** se agregaron pruebas automáticas que simulan una corrida atascada (creada hace más de 30 minutos y todavía "en curso") y confirman que la pantalla deja de consultar al servidor y muestra el aviso correspondiente, además de pruebas unitarias de la nueva regla de corte por antigüedad. Las 241 pruebas de todo el frontend pasan (`npx vitest run`), igual que la verificación de tipos (`npx tsc -b`), sin ninguna falla nueva.

### - [x] 35. La descarga masiva arma el ZIP completo en el disco del servidor, sin límite de tamaño

**En pocas palabras:** para generar la descarga masiva, el sistema baja al servidor **todos** los documentos marcados como útiles, los guarda en disco y luego los comprime. No hay ningún tope: a medida que el archivo crezca, esto puede llenar el disco del servidor.

**Detalle técnico:**
- `worker/tasks.py:306` — `documents = repository.list_useful_documents(db)` trae todas las filas con `review_status == "useful"` (`core/db/repository.py:190-192`), sin paginar ni limitar.
- `worker/tasks.py:317-350` — se descargan uno por uno a `tempfile.TemporaryDirectory` y luego se escribe el ZIP en el mismo directorio temporal, es decir el pico de disco es aproximadamente **dos veces** el tamaño total del conjunto.
- No hay verificación previa de espacio disponible ni límite configurable de documentos o bytes.

**Cómo se resolvió:** dos cambios en `worker/tasks.py`, complementarios entre sí:
1. **Se redujo el pico de uso de disco a casi la mitad.** Antes se bajaban primero todos los documentos y solo al final se armaba el ZIP con todos ellos ya en disco (documentos + ZIP = casi el doble del tamaño real). Ahora cada documento se agrega al ZIP apenas se termina de descargar y su copia temporal se borra de inmediato — así, en cualquier momento, el disco solo tiene el ZIP que se va armando más, como mucho, el archivo individual que se está bajando en ese instante (no todo el lote junto).
2. **Se agregó una revisión de espacio disponible antes de empezar.** El sistema ya guarda el tamaño de cada documento cuando se descarga por primera vez; con ese dato, ahora calcula cuánto espacio necesitaría esta descarga masiva y lo compara con el espacio libre real del servidor **antes** de bajar un solo archivo. Si no alcanza, la descarga se marca como fallida de inmediato con un mensaje claro ("no hay espacio suficiente..."), en vez de ir llenando el disco a ciegas hasta que algo revienta a la mitad. (Para documentos guardados por versiones antiguas del sistema que no tienen ese dato registrado, la revisión simplemente se salta en vez de arriesgarse a bloquear una descarga válida por falta de información — no se agregó un límite fijo de cantidad de documentos porque el verdadero riesgo es el espacio en disco, no la cantidad de archivos.)
- **Pruebas:** se agregaron pruebas automáticas que confirman (a) que las copias temporales de cada documento se van borrando una por una a medida que se agregan al ZIP, en vez de acumularse todas hasta el final; (b) que una descarga masiva se rechaza de inmediato, sin descargar nada, cuando no hay espacio suficiente calculado de antemano; y (c) que esa revisión se salta sin bloquear la descarga cuando algún documento no tiene su tamaño registrado. Las 366 pruebas de todo el proyecto (`pytest --ignore=tests/test_migrations.py`) pasan, sin ninguna falla nueva.
