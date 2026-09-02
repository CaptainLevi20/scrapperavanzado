# Descarga masiva de Decretos de Cali (Laboratorio)

## Problema

Hay que traer **todos** los decretos publicados en
`https://www.cali.gov.co/tic/publicaciones/104759/consulta-de-decretos/`
—~71.969 documentos, de 1974 a hoy— y dejarlos en disco organizados como
`DECRETOS/ALCACALI/{AÑO}/D_ALCACALI_{NUMERO}_{AÑO}.pdf`, listos para
entrar después por el intake normal (el mismo formato de nombre que
produce el Formateador: `D` de Decreto, `ALCACALI` como entidad fija de
este enlace, número del decreto, año).

No existe hoy ninguna herramienta para esto. El apartado Laboratorio ya
agrupa utilidades de lote internas (Renombrado, Reorganización); esta es
la tercera.

## Alcance

- **Carga única.** No hay modo "traer solo los nuevos" ni programación
  recurrente. Si en el futuro se necesita, es otro diseño.
- **Entidad fija.** Todo lo de este enlace es `ALCACALI`; no se detecta
  entidad por documento.
- **A disco, no al almacén de la app.** Escribe una carpeta local en la
  máquina donde corre el backend, igual que el Reorganizador escribe
  sobre `D:\LOTE 2`. No crea una Fuente ni usa el pipeline de Runs.
- **Herramienta interna.** Solo la usa el desarrollador/admin, en la
  máquina donde va a quedar el lote. Endpoints protegidos con
  `require_admin`.
- **Sin índice de metadatos.** Solo los PDF en su jerarquía de carpetas
  (decisión del usuario). La descripción, dependencia, etc. de cada
  decreto no se guardan.
- **Fuera de alcance:** renombrar/mover archivos ya existentes (eso lo
  hacen Renombrado y Reorganización), deduplicar contra otros lotes,
  validar el contenido del PDF más allá de "es un PDF no vacío".

## Hallazgos de la inspección del sitio (2026-09-02)

- La tabla vive en un iframe:
  `https://www.cali.gov.co/aplicaciones/boletin_decretos/`.
- Se alimenta de un único endpoint:
  `GET .../boletin_decretos/paginador.php?pag={N}` (y opcionalmente
  `numero`, `anno`, `descripcion`, `fecha1`, `fecha2`, `order`).
  Devuelve un fragmento HTML: una `<table>` con 10 filas + un paginador.
- **Los filtros no sirven vía petición suelta** (parecen guardarse en
  `$_SESSION` del lado del servidor). No importa: para "traer todo" se
  recorre `pag=1 … pag=7195` sin ningún filtro.
- Funciona **sin login ni cookies**. Confirmado con `curl` directo.
- La página 1 informa el total: `71969 registros en total` y
  `Pagina 1/7195`. El orden es **número ascendente, luego año**
  (el decreto `0001` aparece para 1974, 1975, 1976… en las primeras
  páginas; luego empieza el `0002`).
- Cada `<tr>` del `<tbody>` trae, por celda:
  1. TIPO (siempre `DECRETO`)
  2. NÚMERO (ej. `0001`)
  3. FECHA (`1996-01-02`)
  4. DESCRIPCIÓN
  5. NOTAS DE VIGENCIA (un enlace a `nota.php`, se ignora)
  6. AÑO (`1996`)
  7. DEPENDENCIA
  8. Botón **Descargar**: `<button ... onMouseUp="MM_openBrWindow(<id>,'<URL_DEL_PDF>','descargar',...)">`.
     La URL del PDF se extrae de ese `onMouseUp`.
- Dos formas de URL de PDF observadas:
  - `http://www.cali.gov.co/aplicaciones/boletin_publicaciones/../boletin_publicaciones/imagenes_documentos_decretos/<hash>.pdf`
    — la mayoría. Responde `301` a la versión `https://` y entrega el
    PDF (`%PDF-1.6`, ~50 KB la muestra). **Hay que seguir
    redirecciones.**
  - `ftp://ftp.cali.gov.co/DECRETOS/{año}/DECRETO{numero}{MES}{año}.pdf`
    — vista en un decreto de 1984 (1 de 10 filas de la página 1).
    **No se pudo probar** desde el entorno de diseño: el host FTP no
    respondió (posible bloqueo del entorno, o servidor caído). Se
    desconoce qué proporción del total usa FTP.
- El botón, además de abrir el PDF, hace un `POST paginador.php` con
  `{up: <id>}` (contador de descargas del sitio). **No se replica** —
  no aporta nada al objetivo y evita carga innecesaria al servidor.

## Arquitectura

Tercer tab en la página Laboratorio (`FormatterPage.tsx`), junto a
"Renombrado" y "Reorganización".

| Pieza | Archivo | Rol |
|---|---|---|
| Lógica pura | `core/cali_decretos.py` | Parsear una página de `paginador.php`, normalizar número/año, armar nombre y ruta, validar "es PDF". Sin red ni FastAPI. |
| Tarea en segundo plano | `worker/tasks.py` (nueva `descargar_decretos_cali_task`) | Recorre las páginas, baja los PDF en paralelo, mantiene el archivo de estado. |
| Router | `api/routers/cali_decretos.py` | `POST /cali-decretos/start`, `GET /cali-decretos/status`, `POST /cali-decretos/stop`. Protegido con `require_admin` a nivel de router. |
| Esquemas | `api/schemas.py` | `CaliDecretosStartRequest`, `CaliDecretosStopRequest`, `CaliDecretosEstado`. |
| Cliente API | `frontend/src/api/caliDecretos.ts` | `startCaliDecretos` / `getCaliDecretosStatus` / `stopCaliDecretos`, con `apiFetch`. |
| Panel | `frontend/src/pages/formatter/CaliDecretosPanel.tsx` | Campo de ruta + Iniciar/Detener + progreso. |
| Shell | `FormatterPage.tsx` | Agrega la tercera pestaña. |

### Por qué una tarea de Celery (y no un endpoint síncrono como el Reorganizador)

El Reorganizador puede ser síncrono porque su recorrido de disco tarda
~15 s. Acá son ~72.000 descargas de red: horas. No cabe en una petición
HTTP ni puede depender de que la pestaña siga abierta. Celery ya está en
el proyecto y es el mecanismo establecido para trabajo largo en segundo
plano. A diferencia de `scrape_source_task`, esta tarea **no toca la base
de datos**: su estado vive en un archivo JSON en la carpeta destino.

### Flujo

1. El admin escribe la carpeta destino (ej. `D:\DESCARGA CALI`) y pulsa
   **Iniciar**.
2. `POST /cali-decretos/start` valida que la carpeta exista, lee o crea
   `{destino}/_descarga_estado.json`, decide si es corrida nueva o
   reanudación, y encola `descargar_decretos_cali_task.delay(destino)`.
   Si ya hay una tarea viva para esa carpeta → `409`.
3. La tarea recorre `paginador.php` desde
   `ultima_pagina_completada + 1` (o desde 1). Por cada página: parsea
   ~10 filas y manda sus PDF a una tanda de 8 descargas en paralelo;
   al terminar la página, reescribe el archivo de estado.
4. El panel llama `GET /cali-decretos/status` cada ~3 s y muestra el
   progreso leyendo ese mismo archivo. La pestaña se puede cerrar; la
   tarea sigue.
5. **Detener** escribe `detener_solicitado: true` en el estado. La tarea
   revisa esa marca al terminar cada página (incluida la última) y antes
   de cada reintento de la pasada final, y corta limpio dejando
   `estado: "detenido"`. Toda escritura de la tarea pasa por un guardado
   que preserva la marca: nunca la pisa a `false` mientras estaba
   trabajando.
6. Si la tarea muere, volver a pulsar **Iniciar** retoma desde la última
   página guardada y reintenta la lista de fallidos.

## Recorrido del sitio y nombrado

### Recorrido de páginas

- URL: `https://www.cali.gov.co/aplicaciones/boletin_decretos/paginador.php?pag={N}`,
  con `User-Agent` de navegador, siguiendo redirecciones, timeout 30 s.
- De `pag=1` se leen `total_registros_sitio` y `total_paginas` y se
  guardan en el estado. Se recorre `N` desde
  `ultima_pagina_completada + 1` hasta `total_paginas`.
- Se parsea con BeautifulSoup (ya en el proyecto). Por cada `<tr>` del
  `<tbody>`: `numero` (celda 2), `fecha` (celda 3), `anio` (celda 6),
  `pdf_url` (regex sobre el `onMouseUp` del botón:
  `MM_openBrWindow\(\s*\d+\s*,\s*'([^']+)'`).
- Fila sin botón/URL → aviso `fila_sin_enlace` (con número y año) y se
  sigue.
- Página con error HTTP o HTML inesperado → 3 reintentos (2 s / 8 s /
  30 s); si igual falla, se anota la página en `fallidos`
  (`motivo: "pagina"`) y se sigue con la siguiente. No aborta todo.

### Estabilidad del recorrido

El orden es número ascendente y los decretos nuevos entran al final
(número más alto, año más reciente), así que recorrer de la página 1 a
la última es estable salvo, quizá, las últimas páginas si publican algo
mientras corre. "Saltar lo que ya existe en disco" cubre cualquier
corrimiento.

### Nombre de archivo

Patrón: `D_ALCACALI_{numero}_{anio}.pdf`.

- **Entidad:** siempre `ALCACALI`.
- **Número** (`normalizar_numero`):
  - Solo dígitos → cero-relleno a 4 (`1` → `0001`, `47` → `0047`); si ya
    trae 4 o más, se deja igual (`1234`, `12345`).
  - Con letras/guiones (`0010A`, `13 bis`) → mayúsculas y se conservan
    solo `[A-Z0-9-]`, los espacios internos pasan a `-`
    (`0010A`, `13-BIS`).
  - Vacío tras limpiar (`""`, `"—"`) → `None` → aviso `sin_numero` (año
    + URL); no se baja.
- **Año** (`resolver_anio`): la celda de año si son 4 dígitos; si no, el
  año de la fecha completa (celda 3); si tampoco → `None` → aviso
  `sin_anio`; no se baja.
- **Ruta destino:**
  `{destino}/DECRETOS/ALCACALI/{anio}/D_ALCACALI_{numero}_{anio}.pdf`.

### Números repetidos

Se mantiene en memoria el conjunto de `(numero, anio)` vistos **en el
recorrido actual**:

- Primera aparición → nombre normal.
- Segunda (o más) aparición del mismo `(numero, anio)` en otra fila →
  se guarda como `D_ALCACALI_{numero}_{anio}_2.pdf` (`_3`, `_4`…) y se
  registra un aviso `duplicado` (número, año, nombre guardado).
- Esto es distinto de "el archivo ya existe en disco de una corrida
  anterior": eso se salta en silencio (reanudación), no es un
  duplicado.
- El conjunto se reconstruye vacío al reanudar desde una página
  intermedia. Como los duplicados casi siempre son filas adyacentes
  (mismo número) y la reanudación arranca en un borde de página, el
  riesgo de partir un par de duplicados justo en ese borde es mínimo;
  en el peor caso el segundo se salta como "ya existe".

## Descarga a disco

### Paralelismo

- `ThreadPoolExecutor` con **8** workers (mismo patrón que
  `scrape_source_task` / `build_bulk_download_zip`).
- Se alimenta página por página: parsear página N → enviar sus ~10 PDF
  a la tanda → esperar a que terminen → actualizar estado → página
  N+1. Así el estado siempre refleja "hasta la página N, todo
  intentado".
- **Auto-bajada de velocidad:** si en una ventana corta se acumulan ≥ 5
  respuestas `429` o errores de conexión, la concurrencia baja a **3**
  por el resto de la corrida y se anota una vez
  (`concurrencia_actual` en el estado + aviso).

### Cada PDF

1. Si el archivo destino ya existe y pesa > 1 KB → **saltar**
   (`ya_existian += 1`). Esto es la reanudación.
2. Descargar a un temporal:
   - `http(s)://` → `requests`, siguiendo redirecciones, timeout 60 s,
     `User-Agent` de navegador.
   - `ftp://` → `ftplib` (modo pasivo, timeout 60 s).
3. **Validar** (`es_pdf_valido`): los primeros bytes son `%PDF` **y**
   tamaño > 1 KB. Si no (HTML de error, archivo vacío, HTML de
   redirección) → cuenta como fallo.
4. Si vale: mover el temporal a la ruta final, creando las carpetas que
   falten (`mkdir(parents=True, exist_ok=True)`).
5. **Reintentos por PDF:** ante fallo de red/timeout/validación, hasta 3
   intentos con espera 2 s → 8 s → 30 s. Si igual falla, entra a
   `fallidos` (número, año, URL, motivo, intentos).

### Pasada final de fallidos

Al terminar el recorrido de todas las páginas, la tarea hace **una
pasada más** sobre `fallidos` (mismos 3 reintentos c/u). Lo que
sobreviva queda en `fallidos`; volver a pulsar Iniciar los reintenta
otra vez.

### Enlaces `ftp://`

No se pudieron probar en diseño. Plan:

- La tarea **los intenta** con `ftplib`, mismos 3 reintentos.
- Los que fallen entran a `fallidos` con `motivo: "ftp-no-disponible"`,
  contados aparte en el resumen ("N por FTP no disponibles").
- Si el FTP está caído hoy, mañana se reintentan con Iniciar. Si el
  servidor real del backend sí llega al FTP (el entorno de diseño no es
  ese), funcionan directo.
- Si al correrlo se ve que son miles y el FTP no sirve, se decide un
  plan B aparte (los nombres FTP son muy regulares:
  `DECRETOS/{año}/DECRETO{núm}{MES}{año}.pdf`).

### Espacio en disco

Antes de la primera corrida (cuando aún no hay `_descarga_estado.json`),
el panel avisa que esto puede ocupar decenas o cientos de GB. No hay
chequeo duro (no se conoce el tamaño total de antemano); si una
escritura falla por disco lleno, ese PDF entra a `fallidos` como
cualquier otro error.

## Estado y reanudación

### `{destino}/_descarga_estado.json`

Única fuente de verdad del progreso. La tarea lo reescribe entero al
terminar cada página, con **escritura atómica** (escribe a `.tmp` y
`os.replace`).

```json
{
  "version": 1,
  "estado": "en_curso",
  "iniciado": "2026-09-02T14:30:00Z",
  "actualizado": "2026-09-02T15:10:22Z",
  "terminado": null,

  "total_registros_sitio": 71969,
  "total_paginas": 7195,
  "ultima_pagina_completada": 3120,

  "descargados": 30980,
  "ya_existian": 145,
  "duplicados": 12,
  "fallidos_count": 47,

  "detener_solicitado": false,
  "concurrencia_actual": 8,

  "avisos": [
    { "tipo": "duplicado", "numero": "0010", "anio": 1987, "guardado_como": "D_ALCACALI_0010_1987_2.pdf" },
    { "tipo": "sin_numero", "anio": 1991, "url": "http://..." }
  ],
  "fallidos": [
    { "numero": "0044", "anio": 1984, "url": "ftp://ftp.cali.gov.co/DECRETOS/1984/DECRETO0044ENERO1984.pdf", "motivo": "ftp-no-disponible", "intentos": 3 }
  ]
}
```

- **`estado`**: `en_curso` → `detenido` (lo paró el admin) →
  `terminado` (recorrió todo y ya hizo la pasada final) →
  `terminado_con_fallos` si al final `fallidos` no está vacío.
- **`avisos`** y **`fallidos`** se recortan a un máximo (1.000 cada
  una); los `*_count` siempre reflejan el total real. `fallidos`
  guarda las primeras 1.000 entradas reales (son las que el botón
  "Reintentar" puede reprocesar); si se superan, el panel avisa que la
  lista está recortada y que hay que reanudar por página para el
  resto.
- **`avisos` de tipo `duplicado` / `sin_numero` / `sin_anio` /
  `fila_sin_enlace` no se reintentan solos** (son decisiones o datos
  faltantes, no fallos de red): quedan para revisión manual.

### Tabla de reanudación (al pulsar Iniciar)

| Situación | Acción |
|---|---|
| No hay `_descarga_estado.json` | Empieza de cero, página 1. |
| `estado: en_curso` y `actualizado` hace < 5 min | `409` "ya hay una descarga en curso". |
| `estado: en_curso` pero `actualizado` hace > 5 min | Se asume tarea muerta: retoma desde la última página + reintenta `fallidos`. |
| `estado: detenido` / `terminado_con_fallos` | Retoma desde la última página + reintenta `fallidos`. |
| `estado: terminado` | Revisa que todo siga en disco; si no falta nada, termina enseguida. |

## Backend — detalle

### `core/cali_decretos.py` (lógica pura, sin red)

- `parse_pagina(html: str) -> PaginaParseada` — `filas`
  (`numero`, `fecha`, `anio`, `pdf_url`), `total_registros`,
  `total_paginas` (los dos últimos solo poblados desde `pag=1`).
- `normalizar_numero(texto: str) -> str | None`.
- `resolver_anio(celda_anio: str, fecha: str) -> int | None`.
- `ruta_destino(destino: Path, numero: str, anio: int, sufijo: int = 0) -> Path`.
- `es_pdf_valido(head_bytes: bytes, size: int) -> bool`.

### `worker/tasks.py` — `descargar_decretos_cali_task(destino: str)`

- `@celery_app.task(name="worker.descargar_decretos_cali_task")`.
- Sin base de datos. Estado = archivo JSON.
- Helpers privados: `_leer_estado` / `_escribir_estado_atomico` /
  `_descargar_un_pdf` (http con `requests`, ftp con `ftplib`,
  validación, 3 reintentos con backoff) / `_ajustar_concurrencia`.
- Respeta `detener_solicitado`: lo revisa al terminar cada página
  (incluida la última) y antes de cada reintento de la pasada final.
  `_guardar_estado` es la única vía de escritura de la tarea y preserva
  la marca puesta por `/stop`.
- Al final: pasada única sobre `fallidos` (interrumpible por
  `detener_solicitado`), luego fija `estado`.

### `api/routers/cali_decretos.py`

`APIRouter(dependencies=[Depends(require_admin)])`, registrado en
`api/main.py` con prefijo `/cali-decretos`.

| Endpoint | Entrada | Respuesta |
|---|---|---|
| `POST /cali-decretos/start` | `{ dest_path }` | `404` si la carpeta no existe. `409` si hay tarea viva (`estado: en_curso` y `actualizado` < 5 min) para esa carpeta. Si no: inicializa/actualiza el estado (marca reanudación si corresponde), `descargar_decretos_cali_task.delay(dest_path)`, devuelve el estado. |
| `GET /cali-decretos/status?dest_path=` | — | Contenido de `_descarga_estado.json`. `404` si no existe. |
| `POST /cali-decretos/stop` | `{ dest_path }` | Escribe `detener_solicitado: true`. Devuelve el estado. `404` si no hay estado. |

Esquemas en `api/schemas.py`: `CaliDecretosStartRequest { dest_path: str }`,
`CaliDecretosStopRequest { dest_path: str }`,
`CaliDecretosEstado` (espejo del JSON de arriba).

## Frontend — detalle

- `FormatterPage.tsx` — tercera pestaña
  `{ id: "cali-decretos", label: "Decretos Cali" }`.
- `frontend/src/api/caliDecretos.ts` — `startCaliDecretos(destPath)`,
  `getCaliDecretosStatus(destPath)`, `stopCaliDecretos(destPath)`.
- `frontend/src/pages/formatter/CaliDecretosPanel.tsx`:
  - Campo de ruta destino + botón **Iniciar** (etiqueta según estado:
    "Iniciar" / "Reanudar" / "Reintentar fallidos") + botón **Detener**
    (solo mientras `estado === "en_curso"`).
  - Al montar, si hay ruta, consulta `status`. Mientras
    `estado === "en_curso"`, *polling* cada 3 s (`setInterval` limpiado
    al desmontar).
  - Barra de progreso `ultima_pagina_completada / total_paginas`.
    Debajo: descargados / ya existían / duplicados / fallidos, con el
    desglose FTP vs otros.
  - Aviso de espacio en disco antes de la primera corrida.
  - Secciones plegables **"Fallidos (N)"** y **"Avisos (N)"** con las
    listas del estado (número, año, motivo, URL) + botón "Copiar lista".
  - Reutiliza `ErrorBanner`, `Button`, `Input` y los estilos de tabla
    existentes, igual que `ReorganizePanel`.

## Manejo de errores

- Carpeta destino inexistente → `404` "La ruta no existe o no es una
  carpeta".
- Usuario sin `is_admin` → `403` (igual que `require_admin` en
  `sources.py` / `reorganize.py`).
- Página de `paginador.php` que falla tras 3 reintentos → se anota en
  `fallidos` (`motivo: "pagina"`) y el recorrido sigue.
- PDF que falla tras 3 reintentos → `fallidos`, el resto sigue.
- Respuesta que no es un PDF válido → cuenta como fallo del PDF.
- Fallo de escritura en disco (permiso, disco lleno) → `fallidos` con
  el motivo, el resto sigue.
- La tarea nunca deja el estado en `en_curso` al terminar (éxito,
  fallo controlado o excepción inesperada): siempre pasa a un estado
  terminal (`terminado` / `terminado_con_fallos` / `detenido`).

## Pruebas

### `tests/test_core_cali_decretos.py` (lógica pura, HTML de ejemplo en el test)

- `parse_pagina` saca las 10 filas, la `pdf_url` del `onMouseUp`, y
  `total_paginas` / `total_registros` de la página 1.
- Fila sin botón de descarga → se omite de `filas`.
- `normalizar_numero`: `"1"` → `"0001"`, `"1234"` → `"1234"`,
  `"0010A"` → `"0010A"`, `"13 bis"` → `"13-BIS"`, `""` / `"—"` → `None`.
- `resolver_anio`: celda válida; celda vacía cayendo a la fecha; ambas
  inválidas → `None`.
- `ruta_destino` con y sin sufijo de duplicado.
- `es_pdf_valido`: `%PDF...` grande → sí; HTML → no; 200 bytes → no.

### `tests/test_worker_cali_decretos.py` (`requests` / `ftplib` / reloj mockeados, sobre `tmp_path`)

- Recorrido feliz de 2 páginas simuladas: baja los PDF, arma
  `DECRETOS/ALCACALI/{año}/`, escribe `_descarga_estado.json` con los
  conteos correctos y `estado: "terminado"`.
- Un PDF que falla 3 veces queda en `fallidos` y no aborta el resto.
- Un PDF cuyo destino ya existe → `ya_existian`, no se vuelve a bajar.
- Segundo `(numero, anio)` repetido → sufijo `_2` + aviso `duplicado`.
- Respuesta HTML (no PDF) → cuenta como fallo.
- `detener_solicitado: true` → corta al terminar la página en curso
  (aunque sea la última) y también si llega durante la pasada final;
  deja `estado: "detenido"` y no pisa la marca a `false`.
- Reanudar desde `ultima_pagina_completada` no re-recorre las páginas
  previas.

### `tests/test_api_cali_decretos.py`

- No-admin → `403` en los tres endpoints.
- `start` con carpeta inexistente → `404`.
- `start` con estado `en_curso` reciente → `409`.
- `status` sin archivo → `404`; con archivo → devuelve su contenido.
- `stop` escribe `detener_solicitado: true`.
- La tarea de Celery se mockea (`.delay`) — no baja nada real.

### `frontend/src/pages/formatter/CaliDecretosPanel.test.tsx` (MSW)

- Sin corrida previa: muestra campo de ruta + botón Iniciar; al
  iniciar, pinta el progreso de la respuesta simulada.
- `estado: en_curso`: hace polling, refleja el avance, se ve Detener.
- `estado: terminado_con_fallos`: muestra el resumen, la lista de
  fallidos plegable y el botón Reintentar.

### `frontend/src/pages/FormatterPage.test.tsx`

- Al hacer clic en la pestaña "Decretos Cali" se ve el panel.
