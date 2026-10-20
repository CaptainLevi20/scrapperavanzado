# Guía para integrar una fuente nueva

Esta guía explica, paso a paso, cómo se agrega a IURISYNC una fuente nueva
(una entidad cuyo sitio web publica resoluciones, circulares, conceptos,
sentencias, etc.). Está pensada para alguien que llega al proyecto y tiene que
atender su primera solicitud de fuente.

> **Regla de oro:** una fuente nueva se trata como una **familia** nueva:
> un archivo de scraper propio, sus pruebas, su registro en el seed y su
> ficha en la guía de despliegue. Nada más del sistema debería necesitar
> cambios. Si parece que sí, detente y coméntalo antes de seguir.

La guía sirve igual si trabajas solo o con un asistente de IA (Claude Code u
otro). En el anexo final hay recomendaciones para el segundo caso.

---

## 0. Antes de empezar (primer día)

**Pide al administrador del proyecto:**

- Acceso al repositorio en GitHub (`CaptainLevi20/scrapperavanzado`).
- El código de invitación para registrarte en la aplicación local
  (`REGISTRATION_CODE`; en local puedes poner el que quieras en tu `.env`).

**Instala en tu equipo:** Python 3.14, Node.js (para el frontend), Docker
Desktop y Git.

**Levanta el entorno local** siguiendo el `README.md` (sección *Setup local* y
*Correr los servicios*). Para el frontend: `cd frontend`, `npm install`,
`npm run dev`. Necesitas cuatro cosas corriendo a la vez: Docker
(Postgres/Redis/MinIO), la API, el worker de Celery y el frontend.

**Comprueba que funciona** antes de tocar código: entra al frontend, lanza una
corrida manual de una fuente pequeña ya existente (por ejemplo,
Supervigilancia, que tarda menos de un minuto) y verifica que aparecen los
documentos y que puedes descargar uno.

**Lee primero** (en este orden): `core/scrapers/base.py`, una familia sencilla
completa (`core/scrapers/families/supervigilancia.py`) y su prueba
(`tests/families/test_supervigilancia.py`).

### Quién decide qué

Salvo que se acuerde otra cosa, **todas las aprobaciones las da el
administrador del proyecto**:

| Momento | Qué se le lleva |
|---|---|
| Al terminar la investigación (paso 2) | Si la fuente es viable, o si está bloqueada y se pausa. |
| Al terminar el diseño (paso 3) | El diseño, para aprobarlo antes de programar. |
| Antes de abrir el PR (paso 8) | Aviso de que va a abrirse, con el resultado de la corrida real. |
| Para desplegar (paso 9) | Solicitud de despliegue una vez hecho el merge. |

Ante cualquier duda que cambie lo que se entrega al usuario final (qué
secciones, cómo se nombran, qué se deja fuera), **pregunta en vez de
suponer**.

---

## 1. Panorama: cómo encaja una fuente

```
Sitio web de la entidad
        │  (el scraper lo recorre)
        ▼
core/scrapers/families/<familia>.py   ← lo que tú escribes
        │  devuelve una lista de RawDocModel (un elemento por documento)
        ▼
worker/tasks.py  (Celery)             ← ya existe: descarga, deduplica,
        │                                nombra y guarda
        ▼
PostgreSQL (metadatos) + MinIO (archivos)  →  se ve en el frontend
```

Tu trabajo es **solo la primera caja**: dado un rango de fechas
(`fini`, `ffin`), encontrar los documentos publicados en ese rango y
describir cada uno con un `RawDocModel` (título, tipo, fecha, enlace de
descarga, carpeta). La descarga, la detección de duplicados, la
republicación, el almacenamiento y la interfaz ya están resueltos.

Términos que vas a ver:

| Término | Qué es |
|---|---|
| **Familia** | Un scraper. Clave corta en minúsculas (`supervigilancia`, `sic`). |
| **Fuente** | Una fila en la tabla `sources` que usa una familia. Casi siempre una familia = una fuente. (SAMAI y Rama Judicial son la excepción: una familia, muchas fuentes.) |
| **Sección** | Un tipo de documento dentro de la fuente (Resoluciones, Circulares, Conceptos…). |
| **Corrida** | Una ejecución del scraper para un rango de fechas. La diaria la lanza Celery Beat sola; también se lanzan a mano desde el frontend. |
| **Sigla** | Abreviatura de la entidad que va en el nombre del documento (`SVySP`, `SIC`, `SNR`). |

---

## 2. El flujo completo

| # | Paso | Entregable |
|---|---|---|
| 1 | Recibir la solicitud y aclarar alcance | Lista de secciones y desde qué año |
| 2 | Investigar el sitio | Notas de cómo se obtiene cada sección |
| 3 | Escribir el diseño | `docs/superpowers/specs/AAAA-MM-DD-fuente-<familia>-design.md` |
| 4 | Escribir el plan | `docs/superpowers/plans/AAAA-MM-DD-fuente-<familia>.md` |
| 5 | Implementar con pruebas | Scraper + pruebas + seed |
| 6 | Corrida real en local | Revisión de lo que se descargó |
| 7 | Documentar | Ficha en `docs/guia-despliegue-sistemas.md` |
| 8 | Pull Request | PR a `master` con CI en verde |
| 9 | Despliegue en producción | Lo hace el administrador (ver paso 9) |

### Paso 1 — Aclarar la solicitud

Antes de abrir el editor, confirma con quien pidió la fuente:

- **Qué secciones** quiere (¿solo resoluciones? ¿también conceptos?).
- **Desde qué año** (el "piso"; la mayoría de las fuentes usan 2015).
- **La URL** que tiene en mente. Ojo: muchas veces la URL que dan no es el
  listado real (ver el caso de Supervigilancia en su diseño). Verifica.

### Paso 2 — Investigar el sitio

Es el paso más importante: el 80 % de los problemas se ven aquí. Responde:

1. **¿Qué tecnología usa el sitio?** (WordPress, Drupal, Liferay, SharePoint,
   Odoo, ASP.NET…). Casi siempre ya hay una familia con la misma plataforma
   que sirve de modelo — búscala (ver tabla en la sección 5).
2. **¿Hay una API o todo es HTML?** Mira la pestaña *Red* del navegador
   mientras navegas el listado. Una API JSON (por ejemplo, SharePoint REST) es
   mucho más estable que leer HTML.
3. **¿Cómo se pagina?** ¿Hay páginas, "cargar más", un tope de resultados?
4. **¿Dónde está la fecha de cada documento?** ¿En la fila, en el PDF, en el
   nombre del archivo? ¿Es fecha de expedición o de publicación?
5. **¿Dónde está el número del documento?** Lo necesitas para el título.
6. **¿Hay bloqueos?** Si el sitio exige resolver un desafío de JavaScript o
   tiene un "bot manager" (Radware, Incapsula/Imperva, Cloudflare), **no
   intentes saltarlo**. Se documenta y se pausa la fuente (así quedaron
   Minhacienda y Superservicios). Consúltalo antes de invertir más tiempo.
7. **¿El certificado HTTPS es válido?** Si la cadena está incompleta, se usa
   `verify=False` **solo para ese host** (en las peticiones del scraper y en
   `link["verify"] = False` de cada documento, para que la descarga también
   funcione) y se deja escrito en el código y en la
   guía (como `ssf`, `snr`, `supersolidaria`). Nunca como primera opción.

Haz las pruebas con `requests` desde Python, no solo con el navegador: el
navegador a veces pasa cosas (cookies, idioma, JavaScript) que el scraper no.

### Paso 3 — Diseño

Un documento corto en `docs/superpowers/specs/` con: objetivo, tabla de
secciones (URL, `tipo`, prefijo de título), cómo se construye el sitio, cómo
se obtiene fecha y número, convención de nombres, qué queda **fuera de
alcance** y por qué. Usa como plantilla el más reciente
(`2026-09-10-fuente-supervigilancia-design.md`). **Se aprueba antes de
programar.**

### Paso 4 — Plan

Lista de tareas pequeñas, cada una con su prueba, en `docs/superpowers/plans/`.
Plantilla: `2026-09-10-fuente-supervigilancia.md`. Para una fuente sencilla
(una o dos secciones de HTML simple) basta con una lista corta al final del
diseño; el plan aparte vale la pena cuando hay varias secciones o un
transporte complicado.

### Paso 5 — Implementar

Trabaja en una rama propia (`feature/fuente-<familia>`), nunca directo en
`master` (está protegida).

Archivos que tocas — normalmente **solo estos**:

| Archivo | Qué haces |
|---|---|
| `core/scrapers/families/<familia>.py` | El scraper (nuevo). |
| `core/scrapers/families/__init__.py` | Agregar `<familia>` al `import` de la única línea. Sin esto la familia no se registra. |
| `core/seed.py` | Agregar la familia a `_FAMILIES` (nombre + descripción) y crear su fuente con `repository.create_source_if_missing(...)` al final de `seed_source_families_and_sources`. |
| `tests/families/test_<familia>.py` | Las pruebas (nuevo). |
| `tests/test_seed.py` | Subir en uno los conteos fijos de familias y fuentes y agregar la clave al conjunto esperado. **Se olvida siempre**; si no, CI falla. |

Mira el PR #101 (Supervigilancia) como ejemplo completo:
`git show --stat ee5fa7e`.

#### Esqueleto del scraper

```python
from core.models import RawDocModel
from core.scrapers.base import BaseScrapper
from core.scrapers.registry import register_family
from core.utils import storage_path

_SOURCE = "Nombre exacto de la entidad"   # igual al name del seed
_ANIO_MINIMO = 2015


@register_family("mifamilia")
class ScrapMiFamilia(BaseScrapper):
    def __init__(self):
        self.source = _SOURCE

    def scrap(self, fini, ffin, q="", limit=10000, stop_event=None, on_progress=None):
        docs = []
        for ...:                                   # recorrer cada sección
            if stop_event is not None and stop_event.is_set():
                return docs[:limit]                # el usuario canceló
            # ... armar cada documento solo si su fecha cae en [fini, ffin]
            docs.append(RawDocModel(
                source=_SOURCE,
                # "method" es obligatorio: el descargador lo lee siempre.
                # Si el host tiene el certificado roto, se agrega "verify": False.
                link={"url": url_del_pdf, "method": "GET"},
                title="R_SIGLA_0123_2026",
                tipo="Resolución",
                f_public="2026-03-15",             # AAAA-MM-DD
                # fuente / fecha / tipo / nombre; "(extension)" lo reemplaza
                # el descargador por la extensión real del archivo.
                save_path=storage_path(_SOURCE, "2026-03-15", "Resolución",
                                       "R_SIGLA_0123_2026(extension)"),
            ))
            if len(docs) >= limit:
                return docs[:limit]
        return docs[:limit]
```

Reglas del método `scrap`:

- **Respeta `stop_event`** en cada vuelta de los ciclos largos: así funciona
  el botón de cancelar.
- **Usa `on_progress(texto)`** para avisar qué está haciendo
  (`"[Fuente] Procesando Resoluciones..."`) y para advertencias (archivo
  repetido, fila sin fecha). Es lo que se ve en la pantalla de la corrida.
- **Filtra por fecha** con `fini`/`ffin` y descarta lo anterior al piso.
- **No descargues los PDF** aquí: solo arma el enlace. El worker descarga.
- **Una sola `requests.Session()`** por corrida, con un `User-Agent` de
  navegador.
- **Si una sección falla, avisa y sigue** con las demás; no tumbes la corrida.
- Si no tienes un título fiable, pon el mejor texto disponible y
  `title_unverified=True`.

#### Ajustes opcionales de `BaseScrapper`

Están documentados en `core/scrapers/base.py`. Los que más se usan:

| Atributo | Cuándo usarlo |
|---|---|
| `scheduled_min_lookback_days` | El sitio sube documentos semanas después de su fecha. La corrida diaria normal mira solo 3 días atrás; con esto mira más (Supervigilancia usa 30). |
| `alerta_margen_dias` | La fuente publica muy de vez en cuando y no quieres que salga la alerta de "fuente que puede estar fallando" por eso. |
| `filters_by_publication_date` | La fecha que filtras es la de publicación y no la de expedición. |
| `checks_for_republication = False` | No hay un enlace directo al archivo que se pueda revisar con un `HEAD`. |
| `resolve_unverified_document(...)` | Puedes sacar el título real del PDF ya descargado. |

#### Nombres de los documentos

El título es lo que el usuario ve y el nombre del archivo en la descarga.
Convención actual: `{PREFIJO}_{SIGLA}_{número}_{año}`.

| Prefijo | Tipo | Ejemplo |
|---|---|---|
| `R` | Resolución | `R_SNR_0123_2026` |
| `C` | Circular | `C_SSF_0004_2025` |
| `CE` / `CJ` / `CC` | Circular externa / conjunta / carta circular | `CE_SES_0012_2024` |
| `CTO` | Concepto | `CTO_SSF_1234_2025` |
| `BOL` | Boletín | `BOL_SNS_0074_ENE-MAR_2026` |
| `_A01`, `_A02`… | Sufijo de anexo | `R_SNS_0100_2025_A01` |

Leyes y decretos de ministerios siguen otra regla (`L####YYY`, sin sigla) que
vive en `core/naming.py`. Antes de inventar un prefijo o sigla, busca si ya
existe uno equivalente en otra familia y reutilízalo.

#### Pruebas

- Van en `tests/families/test_<familia>.py`.
- **No salen a internet:** las respuestas del sitio se simulan con la
  librería `responses` usando fragmentos reales de HTML/JSON del sitio.
- Prueba cada función pequeña (extraer número, fecha, título) y al menos un
  `scrap()` completo con el sitio simulado, incluyendo filtro de fechas,
  duplicados, cancelación y una sección que falla.
- Ejecuta solo lo tuyo mientras trabajas:

  ```
  .venv\Scripts\pytest tests/families/test_<familia>.py tests/test_seed.py -v
  ```

  Evita correr toda la batería de base de datos en paralelo en tu equipo; CI
  la corre completa.

### Paso 6 — Corrida real en local

Las pruebas simuladas no garantizan que el sitio real se comporte igual. Con
el entorno local levantado (ver `README.md`):

1. `.venv\Scripts\python -m core.seed` para que la fuente aparezca.
2. **Reinicia el worker de Celery**: no recarga el código solo.
3. Desde el frontend lanza una corrida manual de la fuente con un rango
   amplio (por ejemplo, desde el piso hasta hoy).
4. Revisa el resultado:
   - ¿Cuántos documentos por sección? ¿Cuadra con lo que muestra el sitio?
   - ¿Los títulos tienen número y año correctos? Abre varios PDF y compara.
   - ¿Cuántos quedaron "sin verificar"? ¿Por qué?
   - ¿Hay duplicados o archivos que no son lo que dice el título?
5. Lanza una segunda corrida igual: **no debe descargar nada nuevo**. Si
   vuelve a bajar todo, hay un problema de identidad del documento.

Anota lo que encuentres: los errores del propio sitio (PDF repetidos,
enlaces cruzados) no se "arreglan", se documentan.

### Paso 7 — Documentar

Agrega una ficha de la fuente en `docs/guia-despliegue-sistemas.md`, en la
sección de fuentes, con el mismo formato que las demás. Esa guía la lee
el administrador, así que escribe **en lenguaje sencillo, sin jerga técnica**:

- **Qué trae** y desde qué año.
- **Cuánto entrega** (resultado de la corrida real) y cuánto tarda.
- **Qué no trae** y por qué.
- **Cómo quedan nombrados** (con ejemplo).
- **Fechas:** de dónde salen y cuántos días mira atrás la corrida diaria.
- **Datos del sitio con errores** (si los hay).
- **Detalle técnico** (certificados, cabeceras especiales…).
- **Fuente nueva:** el recordatorio de correr `core.seed` en producción.

### Paso 8 — Pull Request

- Abre el PR de tu rama hacia `master`. Coordina con el administrador antes de
  abrirlo y antes de borrar ramas remotas.
- El CI (GitHub Actions) corre todas las pruebas y debe quedar en verde.
- En la descripción: qué secciones trae, números de la corrida real, qué queda
  fuera y cualquier decisión discutible.

### Paso 9 — Despliegue en producción

No tienes acceso directo al servidor de producción; lo hace el administrador:

1. Al hacer merge del PR, el CI publica las imágenes nuevas en GHCR.
2. En el servidor de la oficina se actualizan los contenedores
   (`docker compose ... pull` / `up -d`).
3. **Una sola vez**, para que la fuente aparezca:

   ```
   docker compose --env-file .env.production -f docker-compose.prod.yml run --rm api python -m core.seed
   ```

4. Se lanza una corrida de prueba en producción y se valida contra lo visto
   en local.

---

## 3. Lista de verificación rápida

- [ ] Alcance confirmado (secciones + año piso)
- [ ] Sitio investigado; sin bloqueos que haya que saltar
- [ ] Diseño aprobado
- [ ] Rama `feature/fuente-<familia>`
- [ ] Scraper con `@register_family`, `stop_event`, `on_progress`, filtro de fechas
- [ ] Import en `core/scrapers/families/__init__.py`
- [ ] Familia + fuente en `core/seed.py` (el `_SOURCE` coincide con el `name`)
- [ ] Conteos actualizados en `tests/test_seed.py`
- [ ] Pruebas de la familia en verde, sin acceso a internet
- [ ] Corrida real local revisada (y segunda corrida sin descargas nuevas)
- [ ] Ficha en `docs/guia-despliegue-sistemas.md`
- [ ] PR con CI en verde
- [ ] Recordatorio de `core.seed` en producción

---

## 4. Errores frecuentes

| Síntoma | Causa habitual |
|---|---|
| CI falla en `test_seed.py` | No subiste los conteos de familias/fuentes. |
| "Familia técnica desconocida" | Falta el import en `families/__init__.py`. |
| La fuente no aparece en el frontend | No se corrió `core.seed` (local o producción). |
| El cambio de código no se nota en la corrida | No reiniciaste el worker de Celery. |
| La segunda corrida vuelve a descargar todo | El enlace o la fecha cambian entre corridas (parámetros como `?t=...`, fechas tipo "Hace 2 días"). |
| El listado llega vacío desde Python pero en el navegador se ve | Falta una cabecera (idioma, `User-Agent`), una cookie o el sitio carga por JavaScript. |
| Error de certificado SSL | Cadena incompleta en el sitio: evalúa `verify=False` solo para ese host y documéntalo. |
| Corridas "pendientes" que no avanzan | Una tarea anterior quedó colgada en el worker local; reinícialo y limpia la cola de Redis. |

---

## 5. Familias que sirven de modelo

| Situación | Mira |
|---|---|
| HTML simple con paginación | `supervigilancia`, `ssf` |
| SharePoint (API REST) | `minsalud`, `supersalud` (Boletín) |
| Búsqueda con formulario y token | `ssf` (conceptos) |
| Listado truncado que obliga a buscar por partes | `snr`, `sic` |
| Documento con anexos | `supersalud`, `supersolidaria` |
| Mismo documento en varias versiones (actuaciones) | `sic`, `samai` |
| Título que se corrige leyendo el PDF | `corte_suprema`, `samai`, `rama_judicial` |
| Certificado inválido (`verify=False`) | `ssf`, `snr`, `supersolidaria` |

Y para cualquier duda de diseño, el `spec` y el `plan` de cada una de estas
familias en `docs/superpowers/` explican por qué se hizo así.

---

## Anexo — Si trabajas con un asistente de IA

Las fuentes existentes se construyeron con Claude Code; los diseños y planes
de `docs/superpowers/` salieron de ese trabajo. Si usas un asistente:

- **Dale esta guía como contexto** al empezar ("lee
  `docs/guia-integracion-fuentes.md` y sigue ese flujo para la fuente X").
- **Pídele primero la investigación y el diseño, no el código.** Revisa el
  diseño tú mismo y llévalo a aprobación antes de dejarlo programar.
- **Pídele que trabaje con pruebas primero** (escribir la prueba, verla
  fallar, luego el código) y que te muestre la salida real de `pytest`.
- **No aceptes "ya funciona" sin evidencia:** la corrida real del paso 6 la
  revisas tú, abriendo PDF y comparando con el sitio.
- **No le dejes desactivar protecciones del sitio** (desafíos anti-robots,
  captchas) aunque lo proponga: la regla del paso 2 aplica igual.
- **Commits, PR y borrado de ramas:** que te pregunte antes de cada uno.

Si trabajas sin asistente, el flujo es el mismo; simplemente el diseño y el
plan los escribes tú, con las mismas plantillas.
