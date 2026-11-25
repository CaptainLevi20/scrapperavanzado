# Fuente Cámara de Comercio de Barranquilla — diseño

**Fecha:** 2026-11-23
**Entidad:** Cámara de Comercio de Barranquilla — Centro de Conciliación y
Arbitraje (`cc_barranquilla`, sigla `CCBAR`)
**Estado:** pendiente de aprobación del administrador. No se programa nada
hasta que se apruebe.

> **Ojo con "CCB":** la carpeta se llama "LAUDOS CENTRO DE CONCILIACIÓN Y
> ARBITRAJE **CCB**" y la propia Cámara de Barranquilla se abrevia "CCB" en
> su sitio. Pero en IURISYNC `ccb` / `CCB` ya es la **Cámara de Comercio de
> Bogotá** (`2026-10-26-fuente-ccb-design.md`). Por eso se propone la clave
> de familia `cc_barranquilla` (como `cc_armenia`) y la sigla `CCBAR`,
> decidida por el administrador el 2026-11-25 (pregunta 1).

> **El enlace que dio el usuario no sirve para el scraper.** La URL
> `…/_layouts/15/onedrive.aspx?id=…` **exige iniciar sesión** con una cuenta
> de Microsoft de la Cámara (302 → `Authenticate.aspx` →
> `login.microsoftonline.com`). Es la dirección a la que llega el navegador
> *después* de abrir el enlace público. El enlace público real está en
> `https://www.camarabaq.org.co/centro-de-conciliacion-y-arbitraje/`, en la
> tarjeta **"Laudos Arbitrales"**:
>
> `https://camarabquilla-my.sharepoint.com/:f:/g/personal/naltamar_camarabaq_org_co/EtYmeJ4NR1dHv54S0g4JT54BsqsrOfoDFjcYOdtNF_sHMA?e=goH5U0`
>
> Ese enlace es **anónimo** ("cualquier persona con el vínculo"): no pide
> usuario ni contraseña. Con él la fuente es viable sin saltar ninguna
> protección.

## Objetivo

Familia de scraper nueva `cc_barranquilla` con una sección:

| Sección | Origen | tipo asignado | prefijo de título |
|---|---|---|---|
| Laudos | Carpeta OneDrive compartida (enlace de la tarjeta "Laudos Arbitrales") | `Laudo arbitral` | `LA` |

Cada laudo (PDF) entra como un `RawDocModel`. Familia **plana**: sin
actuaciones, sin anexos, sin `family_params`. Igual que en Bogotá, los laudos
de **arbitraje social** (2 hoy) entran con el mismo tipo.

## Construcción del sitio

- La carpeta es el **OneDrive personal de una funcionaria** del Centro
  (`naltamar@camarabaq.org.co`), en SharePoint Online
  (`camarabquilla-my.sharepoint.com`). TLS válido. Sin WAF ni captcha.
- Estructura: una subcarpeta por año (`2014` … `2026`, 13 carpetas), cada una
  con los PDF directamente dentro. Sin más niveles. (`Forms` es interna de
  SharePoint y se ignora.)
- **Acceso anónimo:** `GET` al enlace compartido → `302` →
  `onedrive.aspx?id=…` (200) y deja una cookie de sesión anónima **`FedAuth`**
  (sin fecha de vencimiento: de sesión). Con esa cookie en la misma
  `requests.Session()` funcionan:

  | Para qué | Petición |
  |---|---|
  | Listar una carpeta | `GET {sitio}/_api/web/GetFolderByServerRelativePath(decodedurl='<ruta>')?$expand=Folders,Files` con `Accept: application/json;odata=nometadata` |
  | Descargar un archivo | `GET {sitio}/_layouts/15/download.aspx?UniqueId=<guid>` → `200`, `application/pdf`, `Content-Length`, `Content-Disposition` con el nombre real |
  | `HEAD` de un archivo | igual, `200` con `Content-Length` |

  `{sitio}` = `https://camarabquilla-my.sharepoint.com/personal/naltamar_camarabaq_org_co`;
  ruta raíz = `/personal/naltamar_camarabaq_org_co/Documents/LAUDOS CENTRO DE CONCILIACIÓN Y ARBITRAJE CCB`.
  También funciona la API Graph de enlaces (`/_api/v2.0/shares/u!<base64>/driveItem/children`),
  pero se prefiere la REST clásica (una familia, un estilo).
- Cada archivo trae: `Name`, `Length`, `TimeCreated`, `TimeLastModified`,
  `UniqueId` (GUID estable aunque se renombre o mueva), `ServerRelativeUrl`.
- **Sin la cookie nada funciona** (probado): la API, `download.aspx` y la
  API `shares/…/content` responden `401` o redirigen al login. Ver
  "Descarga" — esto obliga a un cambio pequeño fuera de la familia.
- Corrida completa de listado: 1 petición al enlace + 14 a carpetas, **~3 s**.
- Para no depender de un enlace fijo en el código, el scraper lee primero la
  página del Centro y toma el `href` `…sharepoint.com/:f:/…` de la tarjeta
  "Laudos Arbitrales"; si no lo encuentra, usa el enlace conocido y avisa.

### Descarga (cambio en `core/downloader.py`)

> **Se sale de la regla de oro** ("solo la familia"): se señala para que el
> administrador lo apruebe (pregunta 2).

El worker descarga con un `requests.get` sin cookies, y no hay ninguna URL de
este OneDrive que baje el PDF sin la cookie `FedAuth`. Propuesta, con el mismo
patrón que el método `jwt_indirect` de SAMAI:

```python
link = {
    "url": "{sitio}/_layouts/15/download.aspx?UniqueId=<guid>",
    "method": "sharepoint_compartido",
    "compartido": "<enlace :f: de la carpeta>",
}
```

El descargador, para ese método: abre una `Session`, hace `GET` a
`link["compartido"]` (obtiene `FedAuth`) y luego `GET` en streaming a
`link["url"]`. Unas 10 líneas + su prueba en `tests/test_downloader.py`.
Sirve también para cualquier otra entidad que comparta carpetas de OneDrive /
SharePoint (DPS usa enlaces **por archivo**, que no lo necesitan).

- `doc_id` sale de `link["url"]` (+ fecha): el `UniqueId` no cambia si la
  Cámara renombra o mueve el archivo, así que no se duplica por eso.
- **Republicación:** `checks_for_republication = False` (como `ccb`). El
  `HEAD` sin cookie de `check_remote_content_length` llega al login, y un
  laudo no se reemplaza.
- Tamaño: 71 PDF, **≈ 266 MB** en total, mediana 1,3 MB, el mayor 32,5 MB.
  Cabe en `MAX_DOWNLOAD_MB`.
- Todos son `.pdf`. Unos ~5 de 9 revisados son escaneos sin texto.

## Fechas y filtro

La fecha del laudo **solo está en el nombre del archivo** (la API no tiene
otra; `TimeCreated` es la fecha de subida y 47 de 71 dicen `2022-10-19`, una
migración masiva). Formatos que aparecen hoy:

| Formato del prefijo | Casos | Ejemplo |
|---|---|---|
| `AAAA-MM-DD` (con espacios sueltos o día de 1 cifra) | 58 | `2020-09- 11 LAUDO…`, `2018-02-6 Laudo…` |
| `DDMMAAAA` | 5 | `18062026 Laudo Arbitral…` |
| `AAAAMMDD` | 3 | `20240515 LAUDO ARBITRAL…` |
| `DD-MM-AAAA` | 1 | `24-08-2023 Laudo Arbitral…` |
| `AAAA-DD-MM` (mes > 12 → se invierte) | 1 | `2015-26-06 LAUDO…` → 26-06-2015 |
| Ilegible (`2018-09-2018`) | 1 | → año y mes legibles: `2018-09-01` + aviso |
| Sin fecha | 2 | `LAUDO ARBITRAL CONSORCIO DESARROLLO ESCOLAR…` (carpeta 2021), `LAUDO ARBITRAL INVERSIONES AVANADE…` (carpeta 2025) |

- **Sin fecha:** se propone `<año de la carpeta>-01-01` + aviso (como ICBF),
  pregunta 4. No se usa `TimeCreated` (para el de 2021 diría 2022-10-19).
- **Carpeta y año no cuadran** (`2019-08-08 … PICON` está en la carpeta
  2018): manda la fecha del nombre; aviso.
- `f_public = f_providencia` = fecha del laudo. Filtro `fini <= fecha <= ffin`.
- **Piso:** propuesta: todo lo que hay (desde **2014**, son 3 más que desde
  2015). Pregunta 3.
- **Retraso de carga:** los laudos se suben 2-3 semanas después
  (31-08-2026 → subido 18-09; 23-06 → 09-07). Como listar todo cuesta ~3 s,
  la corrida diaria **recorre todo siempre**:
  `scheduled_min_lookback_days = 10_000` (como Armenia).
- **Alerta de salud:** la Cámara sube 1-10 laudos al año (2025: uno solo).
  La alerta de "fuente que puede estar fallando" va a salir seguido; en
  Armenia se aceptó. Pregunta 6.

## Número y nombre canónico

El nombre de archivo **no trae radicado**: solo fecha y partes
(`… LAUDO ARBITRAL INVERSIONES DOS OCEANOS SAS Vs ALIMENTOS PIPO.pdf`).
Algunos PDF con texto citan un radicado (`BAQ-AR-017-14`), pero la mitad son
escaneos: no se puede sacar de forma fiable.

Propuesta (pregunta 5):

- **Título:** `LA_CCBAR_{MMDD}_{año}` — la fecha (mes y día) hace de número,
  manteniendo la forma `{PREFIJO}_{SIGLA}_{número}_{año}`. Ej.:
  `LA_CCBAR_0831_2026`. Hoy no hay dos laudos con la misma fecha; si llega a
  pasar, el segundo lleva `_2` y aviso.
- Sin fecha (2 casos): `LA_CCBAR_SF{n}_{año}` y `title_unverified=True`.
- `detalle` = las partes, tomadas del nombre sin el prefijo de fecha ni la
  palabra "LAUDO ARBITRAL" (`INVERSIONES DOS OCEANOS SAS Vs ALIMENTOS PIPO`).
- Alternativa: el título descriptivo de respaldo de Bogotá
  (`_titulo_respaldo`): legible pero largo y sin la forma común.
- `save_path = storage_path(_SOURCE, fecha, "Laudo arbitral", f"{title}(extension)")`.

## Casos raros del sitio

| Caso | Qué se hace |
|---|---|
| `LUDO ARBITRAL H3 ARQUITECTURA…` (errata) | Es un laudo; no se filtra por la palabra "LAUDO" (todo lo de la carpeta es laudo). |
| `Audiencia de Laudo y Laudo Arbitral PH HOLDING…` | Un solo PDF; entra como laudo. |
| Archivo que no es PDF / Word | Lo rechaza la verificación del descargador; hoy no hay. |
| Fecha `AAAA-DD-MM`, ilegible, sin fecha, carpeta de otro año | Ver "Fechas". |
| El enlace de la página desaparece o cambia | Se usa el conocido y se avisa; si falla, error de la corrida. |

## Volumen esperado

| 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 | Total |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 3 | 7 | 3 | 7 | 7 | 5 | 10 | 5 | 4 | 8 | 8 | 1 | 3 | **71** |

(por carpeta). Corrida completa: 71 PDF, ≈ 266 MB, 2-4 min. Corrida diaria:
15 peticiones de listado y casi siempre 0 descargas.

## Riesgos

- **Es el OneDrive personal de una funcionaria.** Si ella deja la Cámara, su
  OneDrive se borra (o se reasigna) y el enlace muere; la Cámara también
  puede quitar el permiso "cualquier persona con el vínculo" en cualquier
  momento. Lo detecta la alerta de salud / el error de la corrida. Conviene
  sugerir a la Cámara una biblioteca institucional (pregunta 7).
- Microsoft cambia de vez en cuando el flujo de los enlaces anónimos
  (cookies). Si deja de funcionar, se revisa; no se intenta iniciar sesión.

## Fuera de alcance (v1)

- Conciliaciones, amigable composición, insolvencia / recuperación
  empresarial (PRES), listas de árbitros, tarifas, reglamentos.
- Sacar el radicado del texto del PDF (mitad escaneados).

## Integración

**Archivos nuevos:** `core/scrapers/families/cc_barranquilla.py`
(`@register_family("cc_barranquilla")`), `tests/families/test_cc_barranquilla.py`.

**Archivos que se tocan:** `core/scrapers/families/__init__.py`,
`core/seed.py` (`_SOURCE = "Cámara de Comercio de Barranquilla"`,
`family_params={}`), `tests/test_seed.py` (conteos), ficha en
`docs/guia-despliegue-sistemas.md`, y **`core/downloader.py` +
`tests/test_downloader.py`** (método `sharepoint_compartido`, pregunta 2).

Sin migración Alembic. En producción: `python -m core.seed` una vez.

## Pruebas

`tests/families/test_cc_barranquilla.py`, con `responses` y JSON real de la
API REST:

1. Fecha del nombre: cada formato de la tabla, `AAAA-DD-MM`, `2018-09-2018`
   → `2018-09-01` + aviso, sin fecha → `<año carpeta>-01-01` + aviso.
2. Título: `LA_CCBAR_0831_2026`; misma fecha dos veces → `_2`; sin fecha →
   `SF{n}` y `title_unverified`. `detalle` = partes.
3. Toma del enlace `:f:` de la página del Centro; sin enlace → el conocido +
   aviso.
4. Recorrido: raíz → carpetas de año → archivos; `Forms` ignorada; `link`
   con `method`, `url` (`download.aspx?UniqueId=…`) y `compartido`.
5. Filtro por fecha y piso; `scheduled_min_lookback_days == 10_000`;
   `checks_for_republication is False`.
6. `stop_event`, `limit`, carpeta que falla (aviso y sigue), listado vacío.
7. Descargador: método `sharepoint_compartido` hace la petición al enlace y
   luego al archivo con la misma sesión (cookie simulada).

## Preguntas para el usuario / administrador

1. **Clave y sigla:** **Respondida (administrador, 2026-11-25):** sigla **`CCBAR`**. Clave
   `cc_barranquilla` sin objeción. Bogotá pasa a `CCBOG` (cambio aparte en
   la familia `ccb`, ya en producción).
2. **Cambio en el descargador:** ¿se aprueba el método `sharepoint_compartido`
   en `core/downloader.py`? Sin él no se pueden bajar los PDF.
3. **Piso:** ¿todo desde 2014 (propuesto, 71 laudos) o desde 2015 (68)?
4. **Laudos sin fecha** (2): ¿`<año de la carpeta>-01-01` con aviso?
5. **Título sin radicado:** ¿`LA_CCBAR_{MMDD}_{año}` (propuesto) o el
   título descriptivo con las partes, como el respaldo de Bogotá?
6. **Alerta de salud:** ¿se acepta que salga seguido (1-10 laudos al año),
   como en Armenia, o se sube `alerta_margen_dias`?
7. **¿Se le pide a la Cámara** que publique los laudos en una biblioteca
   institucional en vez del OneDrive personal de una funcionaria?

## Plan de implementación (cuando se apruebe)

1. Prueba + método `sharepoint_compartido` en `core/downloader.py`.
2. Prueba + lector de fecha y título desde el nombre (casos 1-2).
3. Prueba + recorrido de carpetas con JSON real y enlace de la página
   (casos 3-4).
4. Prueba + `scrap()` con el sitio simulado (casos 5-6).
5. Import en `families/__init__.py`, seed y `tests/test_seed.py`.
6. Corrida real local completa y segunda corrida sin descargas nuevas.
7. Ficha en `docs/guia-despliegue-sistemas.md`.
