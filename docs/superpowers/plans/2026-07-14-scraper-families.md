# Portar las 8 familias de scrapers restantes — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Portar las 8 familias de scraping restantes (`corte_suprema`, `jep`, `cndj`, `adr`, `adres`, `ane`, `anh`, `rama_judicial`) desde `C:\Users\asant\WebScrapping_Fuentes\scrappers\` al patrón `BaseScrapper` + `@register_family` ya usado por `constitucional`/`samai`, y sembrarlas en `core/seed.py` para que aparezcan como fuentes reales en el dashboard.

**Architecture:** Sin cambios arquitectónicos — se reutiliza el pipeline existente end-to-end (`resolve_scraper` → `scraper.scrap()` → `Downloader.download()` → `upload_file()` → `repository.insert_document()`). Cada familia nueva es un módulo autocontenido en `core/scrapers/families/`, registrado vía decorador al importarse desde `core/scrapers/families/__init__.py`.

**Tech Stack:** Python 3.14, `requests`, `beautifulsoup4`, `pytest` + `responses` (HTTP mockeado) para tests.

## Global Constraints

- Cada familia nueva usa el `family_key` exacto indicado en la tabla de la sección Tasks — estos valores ya están fijados en el spec (`docs/superpowers/specs/2026-07-14-scraper-families-design.md`).
- No se modifica `core/downloader.py` — las 8 familias solo usan métodos `GET`/`POST`, ya soportados.
- No se modifica el frontend — las fuentes nuevas aparecen automáticamente en `SourcesPage`/`RunsPage`/`DocumentsPage` sin cambios.
- Toda construcción de `save_path` usa el helper `storage_path(*parts)` de `core/utils.py` (join con `/`), NO f-strings crudos con prefijo `downloads/` (ese prefijo es vestigial del proyecto de escritorio original y ya se eliminó en `constitucional`/`samai`).
- Las constantes de URL que en el original vienen de `config.config` se inlinean como constantes de módulo — no se crea un `core/config` compartido.
- Cada módulo nuevo se registra en `core/scrapers/families/__init__.py` (import agregado a la lista existente) para que el decorador `@register_family` se ejecute al arrancar el proceso.
- Cada familia lleva un test en `tests/families/test_<family_key>.py` con HTTP mockeado vía `responses` (mismo patrón que `tests/families/test_constitucional.py`/`test_samai.py`), incluyendo un test que confirma el registro en `FAMILY_REGISTRY`.
- Cada tarea de portado (1-8) incluye una validación en vivo contra el sitio real de la entidad, documentada en el reporte de la tarea — no como test automatizado permanente (evita atar la suite de CI a la disponibilidad de sitios externos).
- Los comentarios de dominio no obvios del código original (reglas de tipo de JEP, notas de granularidad de fecha, etc.) se preservan tal cual en el código portado.
- Comandos de este plan asumen Windows/PowerShell con el venv del proyecto (`.venv\Scripts\...`), igual que el resto del README.

---

### Task 1: Corte Suprema de Justicia (`corte_suprema`)

**Files:**
- Create: `core/scrapers/families/corte_suprema.py`
- Modify: `core/scrapers/families/__init__.py`
- Test: `tests/families/test_corte_suprema.py`

**Interfaces:**
- Consumes: `RawDocModel` (`core/models.py`), `BaseScrapper` (`core/scrapers/base.py`), `register_family`/`FAMILY_REGISTRY` (`core/scrapers/registry.py`), `storage_path` (`core/utils.py`) — todos ya existentes, sin cambios.
- Produces: clase `ScrapCorteSuprema` registrada bajo la clave `"corte_suprema"`, instanciable sin argumentos (`ScrapCorteSuprema()`), con `.scrap(fini, ffin, q="", limit=1000, stop_event=None, on_progress=None) -> List[RawDocModel]`. Usada por Task 9 (`core/seed.py`) para crear la fuente "CSJ".

- [ ] **Step 1: Escribir el test (va a fallar porque el módulo no existe aún)**

Crear `tests/families/test_corte_suprema.py`:

```python
import json
import re

import responses

from core.scrapers.families.corte_suprema import ScrapCorteSuprema
from core.scrapers.registry import FAMILY_REGISTRY

_URL = "https://consultaprovidenciasbk.cortesuprema.gov.co/api"


def _item(title="1. Sentencia SC1234-2024. Radicado 11001", fecha="2024-02-01T00:00:00Z", tipo="Sentencia"):
    return {
        "typeOfDocument": tipo,
        "title": title,
        "id": "abc123",
        "onlinePath": "path/to/file",
        "fechaCreacion": fecha,
    }


def _callback_factory(item_fecha="2024-02-01T00:00:00Z"):
    def _callback(request):
        body = json.loads(request.body)
        query = body["query"]
        start = int(re.search(r"start:\s*(\d+)", query).group(1))
        if start == 0:
            payload = {"data": {"getSearchResult": {"searchResults": [_item(fecha=item_fecha)]}}}
        else:
            payload = {"data": {"getSearchResult": {"searchResults": []}}}
        return (200, {"Content-Type": "application/json"}, json.dumps(payload))

    return _callback


@responses.activate
def test_scrap_returns_one_doc_per_tipo_within_range():
    responses.add_callback(responses.POST, _URL, callback=_callback_factory(), content_type="application/json")

    scraper = ScrapCorteSuprema()
    docs = scraper.scrap(fini="2024-01-01", ffin="2024-03-01")

    assert len(docs) == 4  # uno por cada tipo: Tutelas, Laboral, Civil, Penal
    assert {d.tipo for d in docs} == {"Sentencia"}
    assert {d.title for d in docs} == {"Sentencia SC1234-2024"}
    save_path_suffixes = {d.save_path.split("/")[1] for d in docs}
    assert save_path_suffixes == {"SCT", "SCL", "SCC", "SCP"}
    assert docs[0].link == {
        "url": "https://consultaprovidenciasbk.cortesuprema.gov.co/downloadFile/",
        "body": {"path": "path/to/file"},
        "method": "POST",
    }


@responses.activate
def test_scrap_excludes_items_older_than_fini():
    responses.add_callback(
        responses.POST,
        _URL,
        callback=_callback_factory(item_fecha="2020-01-01T00:00:00Z"),
        content_type="application/json",
    )

    scraper = ScrapCorteSuprema()
    docs = scraper.scrap(fini="2024-01-01", ffin="2024-03-01")

    assert docs == []
    # cada uno de los 4 tipos debe detenerse tras su primera petición (un item más
    # viejo que fini dispara `stop=True` antes de llegar a pedir "start=10")
    assert len(responses.calls) == 4


def test_corte_suprema_is_registered_under_its_family_key():
    import core.scrapers.families  # noqa: F401

    assert FAMILY_REGISTRY["corte_suprema"] is ScrapCorteSuprema
```

- [ ] **Step 2: Confirmar que falla**

Run: `.venv\Scripts\pytest tests/families/test_corte_suprema.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'core.scrapers.families.corte_suprema'`

- [ ] **Step 3: Crear el módulo portado**

Crear `core/scrapers/families/corte_suprema.py`:

```python
from datetime import datetime

import requests

from core.models import RawDocModel
from core.scrapers.base import BaseScrapper
from core.scrapers.registry import register_family
from core.utils import storage_path

_CORTE_SUPREMA_URL = "https://consultaprovidenciasbk.cortesuprema.gov.co/api"

_QUERY_TEMPLATE = """query GetSearchResult {{
    getSearchResult(
        searchQuery: {{
            query: "*"
            typeOfQuery: "{}"
            start: {}
            isExact: false
            magistrate: ""
            year: ""
            autoSentencia: ""
            order: "NEW_FIRST"
            roomTutelas: ""
        }}
    ) {{
        numOfResults
        searchResults {{
            typeOfDocument
            aplicationName
            fiveParaphraseResult
            title
            id
            onlinePath
            doctor
            fechaCreacion
            ano
            autoSentencia
            leyesOArticulos
        }}
    }}
}}
"""


@register_family("corte_suprema")
class ScrapCorteSuprema(BaseScrapper):
    def __init__(self):
        self.source = "CSJ"
        self.url = _CORTE_SUPREMA_URL
        self.tipos = {"Tutelas": "SCT", "Laboral": "SCL", "Civil": "SCC", "Penal": "SCP"}

    def scrap(self, fini, ffin, q="", limit=1000, stop_event=None, on_progress=None):
        docs = []

        fecha_inicio = datetime.fromisoformat(fini).date()
        fecha_fin = datetime.fromisoformat(ffin).date()

        for tipo in self.tipos:
            stop = False
            start = 0
            while not stop:
                try:
                    payload = {"query": _QUERY_TEMPLATE.format(tipo, start)}
                    headers = {"Content-Type": "application/json"}

                    response = requests.post(self.url, json=payload, headers=headers)

                    if response.status_code != 200:
                        if response.status_code in (502, 503, 504):
                            raise Exception(
                                f"Error al obtener datos de {self.source}: servidor temporalmente no disponible ({response.status_code}). Intenta de nuevo más tarde."
                            )
                        raise Exception(
                            f"Error al obtener datos de {self.source}: {response.status_code} — el sitio pudo haber cambiado su estructura. Informar al equipo de desarrollo."
                        )

                    data = response.json()

                    search_results = data.get("data", {}).get("getSearchResult", {}).get("searchResults", [])

                    if not search_results:
                        stop = True
                        break

                    for item in search_results:
                        fecha_obj = datetime.fromisoformat(item["fechaCreacion"].replace("Z", "+00:00"))

                        if fecha_obj.date() > fecha_fin:
                            continue
                        elif fecha_obj.date() < fecha_inicio:
                            stop = True
                            break

                        fecha = fecha_obj.strftime("%Y%m%d")
                        titulo = item["title"].split(".")[-2].strip()

                        doc = RawDocModel(
                            tipo=item.get("typeOfDocument") or "Desconocido",
                            title=titulo,
                            link={
                                "url": "https://consultaprovidenciasbk.cortesuprema.gov.co/downloadFile/",
                                "body": {"path": item["onlinePath"]},
                                "method": "POST",
                            },
                            f_public=fecha,
                            source=self.source,
                            save_path=storage_path(self.source, self.tipos[tipo], "(filename)(extension)"),
                        )
                        docs.append(doc)

                        if len(docs) >= limit:
                            stop = True
                            break

                    start += 10

                except KeyError as e:
                    print(f"Error: Missing expected field {e} in response for tipo '{tipo}'")
                    stop = True
                except Exception as e:
                    msg = str(e)
                    if "502" in msg or "503" in msg or "504" in msg:
                        msg += " Para el caso puntual de la Corte Suprema de Justicia no se puede realizar ningún cambio por el momento ya que ambas URLs apuntan a un mismo servidor que actualmente está caído."
                    print(f"Error scraping tipo '{tipo}': {msg}")
                    stop = True

        return docs
```

- [ ] **Step 4: Registrar la familia**

Modificar `core/scrapers/families/__init__.py`:

Antes:
```python
from . import constitucional, samai  # noqa: F401
```

Después:
```python
from . import constitucional, samai, corte_suprema  # noqa: F401
```

- [ ] **Step 5: Confirmar que el test pasa**

Run: `.venv\Scripts\pytest tests/families/test_corte_suprema.py -v`
Expected: PASS (3 tests)

- [ ] **Step 6: Validación en vivo**

Run:
```
.venv\Scripts\python -c "from core.scrapers.families.corte_suprema import ScrapCorteSuprema; docs = ScrapCorteSuprema().scrap(fini='2024-01-01', ffin='2024-01-31', limit=3); print(len(docs)); print(docs[0].title if docs else 'sin resultados')"
```
Reportar en el resultado de la tarea cuántos documentos reales encontró (o el error, si el sitio cambió de estructura desde que se escribió el scraper original). No bloquea el commit si el fallo es de disponibilidad transitoria del sitio — sí bloquea si el error indica que el porting introdujo un bug (comparar contra el comportamiento esperado descrito en este mismo paso).

- [ ] **Step 7: Commit**

```bash
git add core/scrapers/families/corte_suprema.py core/scrapers/families/__init__.py tests/families/test_corte_suprema.py
git commit -m "feat: port Corte Suprema scraper family"
```

---

### Task 2: JEP — Jurisdicción Especial para la Paz (`jep`)

**Files:**
- Create: `core/scrapers/families/jep.py`
- Modify: `core/scrapers/families/__init__.py`
- Test: `tests/families/test_jep.py`

**Interfaces:**
- Consumes: igual que Task 1.
- Produces: clase `ScrapJEP` registrada bajo `"jep"`, instanciable sin argumentos, más la función módulo-privada `_extraer_tipo(hipervinculo: str) -> str` (usada directamente en tests). Usada por Task 9 para crear la fuente "JEP".

- [ ] **Step 1: Escribir el test**

Crear `tests/families/test_jep.py`:

```python
import responses

from core.scrapers.families.jep import ScrapJEP, _extraer_tipo
from core.scrapers.registry import FAMILY_REGISTRY

_URL = "https://relatoria.jep.gov.co/listarProvidecias"


@responses.activate
def test_scrap_filters_by_year_and_deduplicates():
    responses.add(
        responses.GET,
        _URL,
        json=[
            {
                "id": 1, "fecha": 2024, "radicado": "SRVR-003",
                "nombre": "S - Sala de Amnistía o Indulto",
                "hipervinculo": "docs/Auto_SRVR-003_06-julio-2024.pdf",
            },
            {
                "id": 2, "fecha": 2024, "radicado": "SRVR-003",
                "nombre": "S - Sala de Amnistía o Indulto",
                "hipervinculo": "docs/Auto_SRVR-003_06-julio-2024.pdf",  # mismo hipervinculo → duplicado
            },
            {
                "id": 3, "fecha": 2018, "radicado": "SRVR-004",
                "nombre": "S - Sala de Amnistía o Indulto",
                "hipervinculo": "docs/Auto_SRVR-004_01-enero-2018.pdf",  # fuera del rango de año
            },
            {"id": 4, "fecha": 2024, "radicado": "No Aplica", "nombre": "", "hipervinculo": ""},  # placeholder
        ],
        status=200,
    )

    scraper = ScrapJEP()
    docs = scraper.scrap(fini="2023-01-01", ffin="2025-12-31")

    assert len(docs) == 1
    doc = docs[0]
    assert doc.title == "SRVR-003"
    assert doc.tipo == "Auto"
    assert doc.seccion == "S - Sala de Amnistía o Indulto"
    assert doc.seccion_en_carpeta is False
    assert doc.f_public == "2024"
    assert doc.link == {"url": "https://relatoria.jep.gov.co/docs/Auto_SRVR-003_06-julio-2024.pdf", "method": "GET"}
    assert doc.save_path == "JEP/2024/Auto/SRVR-003-1(extension)"


def test_extraer_tipo_prefers_compound_prefixes():
    assert _extraer_tipo("docs/SV-AV_2024.pdf") == "Salvamento y Aclaración de Voto"
    assert _extraer_tipo("docs/SV_2024.pdf") == "Salvamento de Voto"
    assert _extraer_tipo("docs/AV_2024.pdf") == "Aclaración de Voto"
    assert _extraer_tipo("docs/Sentencia_2024.pdf") == "Sentencia"
    assert _extraer_tipo("docs/Desconocido_2024.pdf") == ""


def test_jep_is_registered_under_its_family_key():
    import core.scrapers.families  # noqa: F401

    assert FAMILY_REGISTRY["jep"] is ScrapJEP
```

- [ ] **Step 2: Confirmar que falla**

Run: `.venv\Scripts\pytest tests/families/test_jep.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'core.scrapers.families.jep'`

- [ ] **Step 3: Crear el módulo portado**

Crear `core/scrapers/families/jep.py`:

```python
import re
import unicodedata
from typing import List

import requests

from core.models import RawDocModel
from core.scrapers.base import BaseScrapper
from core.scrapers.registry import register_family
from core.utils import storage_path

_JEP_URL = "https://relatoria.jep.gov.co/listarProvidecias"
_JEP_DOWNLOAD_URL = "https://relatoria.jep.gov.co/"

_INVALID_PATH_CHARS = re.compile(r'[\\/*?:"<>|]')

# El API de JEP no expone un campo de "tipo de documento" separado: "nombre" es en
# realidad la sala/sección (ej. "S - Sala de Amnistía o Indulto"), no el tipo. El
# tipo real (Auto, Resolución, Sentencia...) solo aparece como prefijo del nombre
# de archivo en "hipervinculo" (ej. "Auto_SRVR-003_06-julio-2018.pdf"). Reglas en
# orden de especificidad: los prefijos compuestos van antes que sus sub-cadenas
# (ej. "sv-av" antes que "sv" y "av") para no matchear la regla equivocada.
_TIPO_REGLAS = [
    ("sv-av", "Salvamento y Aclaración de Voto"),
    ("spav", "Salvamento y Aclaración de Voto"),
    ("sentencia-interpretativa", "Sentencia Interpretativa"),
    ("sentencia interpretativa", "Sentencia Interpretativa"),
    ("sentencia", "Sentencia"),
    ("resolucion", "Resolución"),
    ("resolicion", "Resolución"),  # typo visto en datos reales de la fuente
    ("auto", "Auto"),
    ("av", "Aclaración de Voto"),
    ("sv", "Salvamento de Voto"),
    ("concepto", "Concepto"),
    ("acuerdo", "Acuerdo"),
    ("anexo", "Anexo"),
    ("edicion", "Boletín"),
    ("boletin", "Boletín"),
    ("guia", "Guía"),
    ("protocolo", "Protocolo"),
    ("aclaracion", "Aclaración"),
    ("oficio", "Oficio"),
    ("manual", "Manual"),
    ("lineamiento", "Lineamiento"),
]


def _extraer_tipo(hipervinculo: str) -> str:
    fname = hipervinculo.rsplit("/", 1)[-1]
    prefijo = fname.split("_", 1)[0].strip()
    clave = unicodedata.normalize("NFKD", prefijo).encode("ascii", "ignore").decode().lower()
    for patron, tipo in _TIPO_REGLAS:
        if clave.startswith(patron):
            return tipo
    return ""


@register_family("jep")
class ScrapJEP(BaseScrapper):
    def __init__(self):
        self.source = "JEP"
        self.url = None

    def scrap(self, fini, ffin, q="", limit=10000, stop_event=None, on_progress=None) -> List[RawDocModel]:
        # El API de JEP no expone mes/día: "fecha" siempre es un año (ej. 2024), no una
        # fecha completa. Por eso fini/ffin se recortan a año aquí y el filtro de abajo
        # compara años, no días — pedir un rango de meses dentro del mismo año devuelve
        # el año completo, no un subconjunto. La deduplicación por doc_id en el pipeline
        # de descarga es lo que evita reprocesar/reportar los mismos documentos en cada corrida.
        anio_inicial = fini[:4]
        anio_final = ffin[:4]
        self.url = _JEP_URL
        docs = []

        response = requests.get(self.url)

        if response.status_code != 200:
            raise Exception(
                f"Error al obtener datos de {self.source}: {response.status_code} - {response.text} el sitio pudo haber cambiado su estructura o el formato de respuesta, informare al equipo de desarrollo para actualizar el scraper."
            )

        try:
            results = response.json()
        except ValueError:
            raise Exception(
                f"La respuesta no es JSON válido. Contenido recibido:\n{response.text[:500]}"
            )

        data = results
        vistos = set()  # JEP repite el mismo documento con distintos "id" en su propio listado

        for item in data:
            fecha_p = item.get("fecha", 0)
            if fecha_p is None:
                fecha_p = 0

            if int(fecha_p) < int(anio_inicial) or int(fecha_p) > int(anio_final):
                continue  # Salta al siguiente item si la fecha no está dentro del rango

            if not item.get("hipervinculo"):
                continue  # registros placeholder (ej. id=1 "No Aplica") sin archivo real

            hipervinculo = item["hipervinculo"]
            if hipervinculo in vistos:
                continue  # evita reintentar el mismo documento roto muchas veces en la misma corrida
            vistos.add(hipervinculo)

            link = f"{_JEP_DOWNLOAD_URL}{hipervinculo}"

            radicado = item.get("radicado", "")
            seccion = item.get("nombre") or ""  # sala/sección (ej. "S - Sala de Amnistía o Indulto")
            tipo = _extraer_tipo(hipervinculo)
            fecha_p = str(fecha_p)

            # el radicado NO identifica un único documento: el mismo número de caso se
            # reutiliza para el Auto, su SV/AV, y luego la Sentencia y el suyo propio.
            # Sin el id (único y siempre presente en el API) esos documentos distintos
            # comparten ruta local — el segundo pisa al primero, o peor: el downloader
            # ve que el archivo ya existe (guard pensado para el paralelismo de SAMAI) y
            # lo salta sin descargar, aunque igual quede marcado como descargado.
            safe_radicado = _INVALID_PATH_CHARS.sub("-", radicado)
            item_id = item.get("id", "")
            path = storage_path(self.source, fecha_p, tipo, f"{safe_radicado}-{item_id}(extension)")

            doc = RawDocModel(
                source=self.source,
                link={"url": link, "method": "GET"},
                title=radicado,
                tipo=tipo,
                seccion=seccion,
                seccion_en_carpeta=False,
                f_public=fecha_p,
                save_path=path,
            )

            docs.append(doc)

        return docs
```

- [ ] **Step 4: Registrar la familia**

Modificar `core/scrapers/families/__init__.py`:

Antes:
```python
from . import constitucional, samai, corte_suprema  # noqa: F401
```

Después:
```python
from . import constitucional, samai, corte_suprema, jep  # noqa: F401
```

- [ ] **Step 5: Confirmar que el test pasa**

Run: `.venv\Scripts\pytest tests/families/test_jep.py -v`
Expected: PASS (3 tests)

- [ ] **Step 6: Validación en vivo**

Run:
```
.venv\Scripts\python -c "from core.scrapers.families.jep import ScrapJEP; docs = ScrapJEP().scrap(fini='2024-01-01', ffin='2024-12-31'); print(len(docs)); print(docs[0].title if docs else 'sin resultados')"
```
Nota: JEP no aplica `limit` durante el scraping (queda tal cual en el original), así que este comando puede tardar y devolver muchos documentos si 2024 tuvo mucha actividad — es esperado. Reportar el conteo y si el sitio respondió con la forma esperada (JSON, no HTML de error).

- [ ] **Step 7: Commit**

```bash
git add core/scrapers/families/jep.py core/scrapers/families/__init__.py tests/families/test_jep.py
git commit -m "feat: port JEP scraper family"
```

---

### Task 3: CNDJ — Consejo Nacional de Disciplina Judicial (`cndj`)

**Files:**
- Create: `core/scrapers/families/cndj.py`
- Modify: `core/scrapers/families/__init__.py`
- Test: `tests/families/test_cndj.py`

**Interfaces:**
- Consumes: igual que Task 1.
- Produces: clase `ScrapCNDJ` registrada bajo `"cndj"`, instanciable sin argumentos, más la función módulo-privada `_format_radicado(numero_unico: str) -> str`. Usada por Task 9 para crear la fuente "Consejo Nacional de Disciplina Judicial".

- [ ] **Step 1: Escribir el test**

Crear `tests/families/test_cndj.py`:

```python
import responses

from core.scrapers.families.cndj import ScrapCNDJ, _format_radicado
from core.scrapers.registry import FAMILY_REGISTRY

_BASE = "https://relatoria.cndj.gov.co/"

_INDEX_HTML = """
<html><body>
<input name="__RequestVerificationToken" type="hidden" value="TOK1" />
<select id="ddlMagistrado">
  <option value="">Seleccione</option>
  <option value="Juan Perez">Juan Perez</option>
</select>
</body></html>
"""

_RESULTS_HTML = """
<html><body>
<input name="__RequestVerificationToken" type="hidden" value="TOK2" />
<table id="tablaResultados"><tbody>
<tr><td>0</td><td>Juan Perez</td><td>2</td><td>SENTENCIA DEL 15 DE ENERO DE 2024</td>
    <td>05001250200020210021501</td><td>3</td></tr>
</tbody></table>
</body></html>
"""


@responses.activate
def test_scrap_full_flow_returns_expected_document():
    responses.add(responses.GET, _BASE + "Index", body=_INDEX_HTML, status=200)
    responses.add(responses.POST, _BASE + "Resultados?handler=RecibirBusqueda", json={"success": True}, status=200)
    responses.add(responses.GET, _BASE + "Resultados", body=_RESULTS_HTML, status=200)
    responses.add(
        responses.POST,
        _BASE + "Resultados?handler=RecibirDataResumen",
        json={"archivo": "ALGO_ADJUNTA20240120103000"},
        status=200,
    )

    scraper = ScrapCNDJ()
    docs = scraper.scrap(fini="2024-01-01", ffin="2024-03-01")

    assert len(docs) == 1
    doc = docs[0]
    assert doc.title == "05001250200020210021501 - Juan Perez"
    assert doc.magistrado == "Juan Perez"
    assert doc.f_public == "2024-01-20"
    assert doc.f_providencia == "2024-01-15"
    assert doc.convert_to == "rtf"
    assert doc.link["url"] == "https://relatoria.cndj.gov.co/docs_relatoria/ALGO_ADJUNTA20240120103000.pdf"
    assert doc.link["body"] == {"path": "05001250200020210021501_3"}
    assert doc.save_path == (
        "Consejo Nacional de Disciplina Judicial/Juan Perez/2024-01-20/"
        "F05001-25-02-000-2021-00215-01_2024(extension)"
    )


def test_format_radicado_matches_docstring_example():
    assert _format_radicado("05001250200020210021501") == "05001-25-02-000-2021-00215-01"


def test_cndj_is_registered_under_its_family_key():
    import core.scrapers.families  # noqa: F401

    assert FAMILY_REGISTRY["cndj"] is ScrapCNDJ
```

- [ ] **Step 2: Confirmar que falla**

Run: `.venv\Scripts\pytest tests/families/test_cndj.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'core.scrapers.families.cndj'`

- [ ] **Step 3: Crear el módulo portado**

Crear `core/scrapers/families/cndj.py`:

```python
import re
from datetime import datetime, timedelta
from typing import List

import requests
from bs4 import BeautifulSoup

from core.models import RawDocModel
from core.scrapers.base import BaseScrapper
from core.scrapers.registry import register_family
from core.utils import storage_path

_CNDJ_BASE_URL = "https://relatoria.cndj.gov.co/"
_CNDJ_DOWNLOAD_URL = "https://relatoria.cndj.gov.co/docs_relatoria/"

_MESES = {
    "ENERO": "01", "FEBRERO": "02", "MARZO": "03", "ABRIL": "04",
    "MAYO": "05", "JUNIO": "06", "JULIO": "07", "AGOSTO": "08",
    "SEPTIEMBRE": "09", "OCTUBRE": "10", "NOVIEMBRE": "11", "DICIEMBRE": "12",
}

_DATE_PATTERN = re.compile(
    r"(\d{1,2})\s+DE[L]?\s+(ENERO|FEBRERO|MARZO|ABRIL|MAYO|JUNIO|JULIO|AGOSTO"
    r"|SEPTIEMBRE|OCTUBRE|NOVIEMBRE|DICIEMBRE)\s+DE[L]?\s+(\d{4})",
    re.IGNORECASE,
)

_TOKEN_PATTERN = re.compile(r'__RequestVerificationToken[^>]+value="([^"]+)"')
_ARCHIVO_TS_PATTERN = re.compile(r"(\d{14})$")


def _parse_date(text: str):
    m = _DATE_PATTERN.search(text.upper())
    if m:
        day = m.group(1).zfill(2)
        month = _MESES[m.group(2).upper()]
        year = m.group(3)
        if 1990 <= int(year) <= 2100:
            return f"{year}-{month}-{day}"
    return None


def _format_radicado(numero_unico: str) -> str:
    """'05001250200020210021501' → '05001-25-02-000-2021-00215-01'"""
    n = numero_unico.replace("/", "").replace("-", "").replace("\\", "")
    if len(n) != 23:
        return n
    return f"{n[0:5]}-{n[5:7]}-{n[7:9]}-{n[9:12]}-{n[12:16]}-{n[16:21]}-{n[21:23]}"


def _radicado_year(numero_unico: str):
    if len(numero_unico) >= 16:
        year = numero_unico[12:16]
        if year.isdigit() and 1990 <= int(year) <= 2100:
            return f"{year}-01-01"
    return None


@register_family("cndj")
class ScrapCNDJ(BaseScrapper):
    def __init__(self):
        self.source = "Consejo Nacional de Disciplina Judicial"

    def scrap(self, fini, ffin, q="", limit=10000, stop_event=None, on_progress=None) -> List[RawDocModel]:
        session = requests.Session()
        session.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})

        # 1. Obtener token CSRF y lista de magistrados desde la página principal
        index_resp = session.get(_CNDJ_BASE_URL + "Index", timeout=30)
        index_resp.raise_for_status()
        token_m = _TOKEN_PATTERN.search(index_resp.text)
        if not token_m:
            raise Exception(f"No se encontró el token de verificación en {self.source}")
        token = token_m.group(1)

        index_soup = BeautifulSoup(index_resp.text, "html.parser")
        magistrados = [
            opt["value"].strip()
            for opt in index_soup.select("#ddlMagistrado option[value]")
            if opt["value"].strip()
        ]
        if not magistrados:
            raise Exception(f"No se encontraron magistrados en {self.source}")

        # 2. Buscar por cada magistrado y recolectar filas únicas por numeroUnico
        # La búsqueda avanzada garantiza cobertura total (~20k docs vs ~17k con búsqueda general)
        all_rows: dict[str, tuple] = {}  # numero_unico -> (magistrado, decision_text, numero_ficha)

        for mag in magistrados:
            body = {
                "Type": "avanzada",
                "BusquedaAvanzada": {
                    "PorMagistrado": True,
                    "PorAnhoRadicacion": False,
                    "PorTemas": False,
                    "PorRestrictores": False,
                    "PorAsunto": False,
                    "PorDisciplinado": False,
                    "Magistrado": mag,
                    "AnhoRadicacion": "",
                    "Tema": "",
                    "Restrictor": "",
                    "Asunto": "",
                    "Disciplinado": "",
                },
            }
            try:
                search_resp = session.post(
                    _CNDJ_BASE_URL + "Resultados?handler=RecibirBusqueda",
                    json=body,
                    headers={"Content-Type": "application/json", "RequestVerificationToken": token},
                    timeout=60,
                )
                search_resp.raise_for_status()
                if not search_resp.json().get("success"):
                    continue

                results_resp = session.get(_CNDJ_BASE_URL + "Resultados", timeout=180)
                results_resp.raise_for_status()
            except Exception:
                continue

            # Actualizar token para la siguiente búsqueda
            token_m2 = _TOKEN_PATTERN.search(results_resp.text)
            if token_m2:
                token = token_m2.group(1)

            soup = BeautifulSoup(results_resp.text, "html.parser")
            for row in soup.select("#tablaResultados tbody tr"):
                tds = row.find_all("td")
                if len(tds) < 6:
                    continue
                magistrado = tds[1].get_text(strip=True)
                decision_text = tds[3].get_text(strip=True)
                numero_unico = tds[4].get_text(strip=True)
                numero_ficha = tds[5].get_text(strip=True) or "1"

                if numero_unico and numero_unico not in all_rows:
                    all_rows[numero_unico] = (magistrado, decision_text, numero_ficha)

        # 3. Filtrar por fecha y obtener archivo desde endpoint de detalle
        years_in_range = {str(y) for y in range(int(fini[:4]), int(ffin[:4]) + 1)}

        detail_headers = {
            "Content-Type": "application/json",
            "RequestVerificationToken": token,
        }

        docs = []
        for numero_unico, (magistrado, decision_text, numero_ficha) in all_rows.items():
            # Pre-filtro por año: descarta filas donde ningún año del rango aparezca
            # en el texto de decisión ni en el número único (simula búsqueda DataTables)
            if not any(y in decision_text or y in numero_unico for y in years_in_range):
                continue

            fecha_decision = _parse_date(decision_text)
            fecha_estimada = fecha_decision or _radicado_year(numero_unico) or fini

            # margen de holgura: el archivo suele publicarse días o semanas después de
            # la decisión (confirmado con datos reales), así que el pre-filtro no puede
            # exigir precisión exacta antes de consultar el detalle
            fini_holgado = (datetime.strptime(fini, "%Y-%m-%d") - timedelta(days=90)).strftime("%Y-%m-%d")
            ffin_holgado = (datetime.strptime(ffin, "%Y-%m-%d") + timedelta(days=90)).strftime("%Y-%m-%d")
            if fecha_estimada < fini_holgado or fecha_estimada > ffin_holgado:
                continue

            try:
                detail_resp = session.post(
                    _CNDJ_BASE_URL + "Resultados?handler=RecibirDataResumen",
                    json={"Proceso": numero_unico, "NumeroFicha": str(numero_ficha)},
                    headers=detail_headers,
                    timeout=30,
                )
                detail_resp.raise_for_status()
                detail_data = detail_resp.json()
            except Exception:
                continue

            archivo = detail_data.get("archivo", "")
            if not archivo or not archivo.strip():
                continue

            # el nombre del archivo trae la fecha real de publicación/adjunción al final
            # (ej. "...ADJUNTA20251024143552"); distinta de fecha_decision (f_providencia),
            # no se mezclan — aunque no es 100% monótona respecto a la decisión (~8% de ruido)
            ts_m = _ARCHIVO_TS_PATTERN.search(archivo)
            f_public = (
                (f"{ts_m.group(1)[0:4]}-{ts_m.group(1)[4:6]}-{ts_m.group(1)[6:8]}" if ts_m else None)
                or fecha_decision
                or _radicado_year(numero_unico)
                or fini
            )

            if f_public < fini or f_public > ffin:
                continue

            url = f"{_CNDJ_DOWNLOAD_URL}{archivo}.pdf"
            dedup_key = f"{numero_unico}_{numero_ficha}"
            magistrado_fmt = magistrado.title()
            safe_num = "F" + _format_radicado(numero_unico) + f"_{f_public[:4]}"
            path = storage_path(self.source, magistrado_fmt, f_public, f"{safe_num}(extension)")

            docs.append(RawDocModel(
                source=self.source,
                link={"url": url, "method": "GET", "body": {"path": dedup_key}},
                title=f"{numero_unico} - {magistrado}",
                tipo="",
                magistrado=magistrado_fmt,
                f_public=f_public,
                f_providencia=fecha_decision,
                save_path=path,
                convert_to="rtf",
            ))

        return docs
```

- [ ] **Step 4: Registrar la familia**

Modificar `core/scrapers/families/__init__.py`:

Antes:
```python
from . import constitucional, samai, corte_suprema, jep  # noqa: F401
```

Después:
```python
from . import constitucional, samai, corte_suprema, jep, cndj  # noqa: F401
```

- [ ] **Step 5: Confirmar que el test pasa**

Run: `.venv\Scripts\pytest tests/families/test_cndj.py -v`
Expected: PASS (3 tests)

- [ ] **Step 6: Validación en vivo (versión ligera)**

CNDJ itera sobre TODOS los magistrados registrados (potencialmente cientos), cada uno con 2 peticiones — correr `.scrap()` completo como validación en vivo sería lento e innecesariamente pesado para el sitio real. En su lugar, validar solo que la estructura del sitio (token CSRF + select de magistrados) sigue siendo la esperada:

Crear un script temporal `check_cndj_live.py` (no se commitea) en la raíz del repo:
```python
import re
import requests

resp = requests.get("https://relatoria.cndj.gov.co/Index", timeout=30)
print("status:", resp.status_code)
token_found = bool(re.search(r'__RequestVerificationToken[^>]+value="([^"]+)"', resp.text))
print("token encontrado:", token_found)
print("select de magistrado presente:", 'ddlMagistrado' in resp.text)
```

Run: `.venv\Scripts\python check_cndj_live.py`
Expected: `status: 200`, `token encontrado: True`, `select de magistrado presente: True`. Reportar el resultado real en la tarea. Borrar `check_cndj_live.py` después (`git status` debe quedar limpio).

- [ ] **Step 7: Commit**

```bash
git add core/scrapers/families/cndj.py core/scrapers/families/__init__.py tests/families/test_cndj.py
git commit -m "feat: port CNDJ scraper family"
```

---

### Task 4: Agencia de Desarrollo Rural (`adr`)

**Files:**
- Create: `core/scrapers/families/adr.py`
- Modify: `core/scrapers/families/__init__.py`
- Test: `tests/families/test_adr.py`

**Interfaces:**
- Consumes: igual que Task 1.
- Produces: clase `ScrapADR` registrada bajo `"adr"`, instanciable sin argumentos, con método `_extraer_documentos(html, tipo, fini, ffin)` accesible para tests. Usada por Task 9 para crear la fuente "Agencia de Desarrollo Rural".

- [ ] **Step 1: Escribir el test**

Crear `tests/families/test_adr.py`:

```python
import json
from urllib.parse import parse_qs, urlparse

import responses

from core.scrapers.families.adr import ScrapADR, _API_PAGES
from core.scrapers.registry import FAMILY_REGISTRY


def test_extraer_documentos_parses_full_date():
    scraper = ScrapADR()
    html = '<a href="/wp-content/uploads/2024/04/decreto-381.pdf">Decreto No. 0381 del 07 de abril de 2024</a>'
    docs = scraper._extraer_documentos(html, "Decreto", "2024-01-01", "2024-12-31")

    assert len(docs) == 1
    assert docs[0].f_public == "2024-04-07"
    assert docs[0].save_path == "Agencia de Desarrollo Rural/2024-04-07/Decreto/(filename)(extension)"


def test_extraer_documentos_falls_back_to_year_only():
    scraper = ScrapADR()
    html = '<a href="/wp-content/uploads/2024/06/ley-2387.pdf">LEY 2387 DE 2024</a>'
    docs = scraper._extraer_documentos(html, "Ley", "2024-01-01", "2024-12-31")

    assert len(docs) == 1
    assert docs[0].f_public == "2024-01-01"


def test_extraer_documentos_falls_back_to_upload_date():
    scraper = ScrapADR()
    html = '<a href="/wp-content/uploads/2024/06/circular-sin-fecha.pdf">Circular sin fecha en el texto</a>'
    docs = scraper._extraer_documentos(html, "Circular", "2024-01-01", "2024-12-31")

    assert len(docs) == 1
    assert docs[0].f_public == "2024-06-01"


def test_extraer_documentos_excludes_out_of_range():
    scraper = ScrapADR()
    html = '<a href="/wp-content/uploads/2020/04/decreto-viejo.pdf">Decreto No. 0100 del 01 de abril de 2020</a>'
    docs = scraper._extraer_documentos(html, "Decreto", "2024-01-01", "2024-12-31")

    assert docs == []


@responses.activate
def test_scrap_aggregates_across_categories():
    def _callback(request):
        slug = parse_qs(urlparse(request.url).query).get("slug", [""])[0]
        if slug == "leyes":
            html = '<a href="/wp-content/uploads/2024/05/ley-123.pdf">LEY 123 DE 2024</a>'
            body = json.dumps([{"content": {"rendered": html}}])
        else:
            body = json.dumps([{"content": {"rendered": ""}}])
        return (200, {"Content-Type": "application/json"}, body)

    responses.add_callback(responses.GET, _API_PAGES, callback=_callback, content_type="application/json")

    scraper = ScrapADR()
    docs = scraper.scrap(fini="2024-01-01", ffin="2024-12-31")

    assert len(docs) == 1
    assert docs[0].tipo == "Ley"
    assert docs[0].f_public == "2024-01-01"


def test_adr_is_registered_under_its_family_key():
    import core.scrapers.families  # noqa: F401

    assert FAMILY_REGISTRY["adr"] is ScrapADR
```

- [ ] **Step 2: Confirmar que falla**

Run: `.venv\Scripts\pytest tests/families/test_adr.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'core.scrapers.families.adr'`

- [ ] **Step 3: Crear el módulo portado**

Crear `core/scrapers/families/adr.py`:

```python
import re
from typing import List

import requests

from core.models import RawDocModel
from core.scrapers.base import BaseScrapper
from core.scrapers.registry import register_family
from core.utils import storage_path

_BASE_URL = "https://www.adr.gov.co"
_API_PAGES = f"{_BASE_URL}/wp-json/wp/v2/pages"

# Categorías de "Normativa de la entidad" que son páginas planas de WordPress
# (un solo listado de enlaces, sin subdivisión por año)
_CATEGORIAS_PLANAS = {
    "leyes": "Ley",
    "decretos": "Decreto",
    "acuerdos": "Acuerdo",
    "reglamentos": "Reglamento",
    "circulares": "Circular",
    "conceptos-juridicos": "Concepto Jurídico",
    "directivas": "Directiva",
    "covid-19": "Covid-19",
}
# "Resoluciones" es la única categoría dividida en subpáginas por año
# (resoluciones-2016 ... resoluciones-2026), más una subpágina fija de nombramientos
_RESOLUCIONES_SLUGS_FIJOS = ["resoluciones-de-nombramientos"]

_MESES = {
    "ENERO": "01", "FEBRERO": "02", "MARZO": "03", "ABRIL": "04",
    "MAYO": "05", "JUNIO": "06", "JULIO": "07", "AGOSTO": "08",
    "SEPTIEMBRE": "09", "OCTUBRE": "10", "NOVIEMBRE": "11", "DICIEMBRE": "12",
}
# Nivel 1 de precisión: fecha completa embebida en el texto del enlace
# (ej. "Decreto No. 0381 del 07 de abril de 2026")
_FULL_DATE_PATTERN = re.compile(
    r"(\d{1,2})\s+DE[L]?\s+(ENERO|FEBRERO|MARZO|ABRIL|MAYO|JUNIO|JULIO|AGOSTO"
    r"|SEPTIEMBRE|OCTUBRE|NOVIEMBRE|DICIEMBRE)\s+DE[L]?\s+(\d{4})",
    re.IGNORECASE,
)
# Nivel 2: solo el año (ej. "LEY 2387 DE 2024", "Acuerdo 001 de 2025")
_YEAR_ONLY_PATTERN = re.compile(r"\bDE[L]?\s+(\d{4})\b", re.IGNORECASE)
# Nivel 3 (último recurso): fecha de subida del archivo, tomada de la ruta
# /wp-content/uploads/YYYY/MM/ — para documentos sin ninguna fecha en el texto
_UPLOAD_DATE_PATTERN = re.compile(r"/uploads/(\d{4})/(\d{2})/")

_PDF_LINK_PATTERN = re.compile(r'<a[^>]+href="([^"]+\.pdf)"[^>]*>([^<]*)</a>', re.IGNORECASE)


def _parse_full_date(text: str):
    m = _FULL_DATE_PATTERN.search(text.upper())
    if m:
        day = m.group(1).zfill(2)
        month = _MESES[m.group(2).upper()]
        year = int(m.group(3))
        if 1990 <= year <= 2100:
            return f"{year}-{month}-{day}"
    return None


def _parse_year_only(text: str):
    m = _YEAR_ONLY_PATTERN.search(text.upper())
    if m and 1990 <= int(m.group(1)) <= 2100:
        return int(m.group(1))
    return None


def _parse_upload_year_month(url: str):
    m = _UPLOAD_DATE_PATTERN.search(url)
    if m:
        return int(m.group(1)), m.group(2)
    return None


@register_family("adr")
class ScrapADR(BaseScrapper):
    def __init__(self):
        self.source = "Agencia de Desarrollo Rural"

    def _fetch_page_content(self, session, slug):
        resp = session.get(_API_PAGES, params={"slug": slug}, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        if not data:
            return None
        return data[0]["content"]["rendered"]

    def _extraer_documentos(self, html, tipo, fini, ffin):
        docs = []
        if not html:
            return docs

        anio_inicial = int(fini[:4])
        anio_final = int(ffin[:4])

        for href, texto in _PDF_LINK_PATTERN.findall(html):
            texto = texto.strip()
            url = href if href.startswith("http") else f"{_BASE_URL}{href}"

            fecha_completa = _parse_full_date(texto)
            if fecha_completa:
                if fecha_completa < fini or fecha_completa > ffin:
                    continue
                f_public = fecha_completa
            else:
                anio = _parse_year_only(texto)
                mes = "01"
                if anio is None:
                    upload = _parse_upload_year_month(url)
                    if upload is None:
                        continue
                    anio, mes = upload
                if anio < anio_inicial or anio > anio_final:
                    continue
                f_public = f"{anio}-{mes}-01"

            path = storage_path(self.source, f_public, tipo, "(filename)(extension)")

            docs.append(RawDocModel(
                source=self.source,
                link={"url": url, "method": "GET"},
                title=texto or url.rsplit("/", 1)[-1],
                tipo=tipo,
                f_public=f_public,
                save_path=path,
            ))

        return docs

    def scrap(self, fini, ffin, q="", limit=10000, stop_event=None, on_progress=None) -> List[RawDocModel]:
        session = requests.Session()
        session.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})

        docs = []

        for slug, tipo in _CATEGORIAS_PLANAS.items():
            if stop_event is not None and stop_event.is_set():
                return docs
            if on_progress:
                on_progress(f"[{self.source}] Procesando {tipo}...")
            html = self._fetch_page_content(session, slug)
            docs.extend(self._extraer_documentos(html, tipo, fini, ffin))
            if len(docs) >= limit:
                return docs[:limit]

        if stop_event is not None and stop_event.is_set():
            return docs
        if on_progress:
            on_progress(f"[{self.source}] Procesando Resolución...")

        for slug in _RESOLUCIONES_SLUGS_FIJOS:
            html = self._fetch_page_content(session, slug)
            docs.extend(self._extraer_documentos(html, "Resolución", fini, ffin))

        anio_inicial = int(fini[:4])
        anio_final = int(ffin[:4])
        for anio in range(anio_inicial, anio_final + 1):
            if stop_event is not None and stop_event.is_set():
                return docs
            html = self._fetch_page_content(session, f"resoluciones-{anio}")
            docs.extend(self._extraer_documentos(html, "Resolución", fini, ffin))
            if len(docs) >= limit:
                return docs[:limit]

        return docs
```

- [ ] **Step 4: Registrar la familia**

Modificar `core/scrapers/families/__init__.py`:

Antes:
```python
from . import constitucional, samai, corte_suprema, jep, cndj  # noqa: F401
```

Después:
```python
from . import constitucional, samai, corte_suprema, jep, cndj, adr  # noqa: F401
```

- [ ] **Step 5: Confirmar que el test pasa**

Run: `.venv\Scripts\pytest tests/families/test_adr.py -v`
Expected: PASS (6 tests)

- [ ] **Step 6: Validación en vivo**

Run:
```
.venv\Scripts\python -c "from core.scrapers.families.adr import ScrapADR; docs = ScrapADR().scrap(fini='2023-01-01', ffin='2024-12-31'); print(len(docs)); print(docs[0].title if docs else 'sin resultados')"
```
Reportar el conteo real encontrado y confirmar que no lanzó excepciones.

- [ ] **Step 7: Commit**

```bash
git add core/scrapers/families/adr.py core/scrapers/families/__init__.py tests/families/test_adr.py
git commit -m "feat: port Agencia de Desarrollo Rural scraper family"
```

---

### Task 5: ADRES (`adres`)

**Files:**
- Create: `core/scrapers/families/adres.py`
- Modify: `core/scrapers/families/__init__.py`
- Test: `tests/families/test_adres.py`

**Interfaces:**
- Consumes: igual que Task 1.
- Produces: clase `ScrapADRES` registrada bajo `"adres"`, instanciable sin argumentos, con métodos `_extraer_filas(html, tipo, fini, ffin, vistos)` y `_extraer_next_links(html)` accesibles para tests. Usada por Task 9 para crear la fuente ADRES.

- [ ] **Step 1: Escribir el test**

Crear `tests/families/test_adres.py`:

```python
from core.scrapers.families.adres import ScrapADRES
from core.scrapers.registry import FAMILY_REGISTRY

_TABLE_HTML = """
<table>
<tr><td>Fecha</td><td>Documento</td><td>Descripción</td></tr>
<tr><td>15/01/2024</td><td><a href="/normativa/resolucion-1.pdf">Resolución 1</a></td><td>Detalle 1</td></tr>
<tr><td>15/01/2020</td><td><a href="/normativa/resolucion-vieja.pdf">Resolución vieja</a></td><td>Detalle 2</td></tr>
</table>
"""


def test_extraer_filas_filters_by_date_and_builds_absolute_urls():
    scraper = ScrapADRES()
    docs, fechas = scraper._extraer_filas(_TABLE_HTML, "Resolución", "2024-01-01", "2024-12-31", set())

    assert len(docs) == 1
    assert docs[0].title == "Resolución 1"
    assert docs[0].f_public == "2024-01-15"
    assert docs[0].link["url"] == "https://www.adres.gov.co/normativa/resolucion-1.pdf"
    assert docs[0].detalle == "Detalle 1"
    assert fechas == ["2024-01-15", "2020-01-15"]  # todas las fechas vistas, sin filtrar


def test_extraer_filas_ignores_tables_without_fecha_header():
    scraper = ScrapADRES()
    html = "<table><tr><td>Otro</td><td>Col</td></tr><tr><td>x</td><td>y</td></tr></table>"
    docs, fechas = scraper._extraer_filas(html, "Resolución", "2024-01-01", "2024-12-31", set())

    assert docs == []
    assert fechas == []


def test_extraer_next_links_finds_pagination_urls():
    scraper = ScrapADRES()
    html = '<script>RefreshPageTo(event, "/normativa/resoluciones?page=2");</script>'
    links = scraper._extraer_next_links(html)

    assert links == ["https://www.adres.gov.co/normativa/resoluciones?page=2"]


def test_adres_is_registered_under_its_family_key():
    import core.scrapers.families  # noqa: F401

    assert FAMILY_REGISTRY["adres"] is ScrapADRES
```

- [ ] **Step 2: Confirmar que falla**

Run: `.venv\Scripts\pytest tests/families/test_adres.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'core.scrapers.families.adres'`

- [ ] **Step 3: Crear el módulo portado**

Crear `core/scrapers/families/adres.py`:

```python
import re
from typing import List
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from core.models import RawDocModel
from core.scrapers.base import BaseScrapper
from core.scrapers.registry import register_family
from core.utils import storage_path

_BASE_URL = "https://www.adres.gov.co"
_ALLOWED_DOMAIN = "adres.gov.co"

# Solo las categorías con una tabla real de fecha estructurada (Resoluciones,
# Circulares, Acuerdos). "Proyecto de Acto Administrativo" no tiene fecha en
# ningún lado y "Acción popular"/"Fallos de tutela" están vacías — se dejan fuera.
_CATEGORIAS = {
    "/normativa/resoluciones": "Resolución",
    "/normativa/circulares": "Circular",
    "/normativa/acuerdos": "Acuerdo",
}

_NEXT_LINK_PATTERN = re.compile(r'RefreshPageTo\(event,\s*"([^"]+)"\)')
_FECHA_PATTERN = re.compile(r"(\d{2})/(\d{2})/(\d{4})")
_MAX_PAGINAS_POR_CATEGORIA = 60


@register_family("adres")
class ScrapADRES(BaseScrapper):
    def __init__(self):
        self.source = "Administradora de los Recursos del Sistema General de Seguridad Social en Salud"

    def _es_url_propia(self, url: str) -> bool:
        try:
            return _ALLOWED_DOMAIN in urlparse(url).netloc
        except Exception:
            return False

    def _extraer_filas(self, html: str, tipo: str, fini: str, ffin: str, vistos: set):
        """Devuelve (docs_en_rango, fechas_vistas_sin_filtrar) de todas las tablas
        cuya primera columna de encabezado es "Fecha" (biblioteca de documentos
        propia + lista mixta, en ambas variantes de clase CSS que usa SharePoint)."""
        docs = []
        fechas_vistas = []
        soup = BeautifulSoup(html, "html.parser")

        for table in soup.find_all("table"):
            rows = table.find_all("tr")
            if not rows:
                continue
            header = [c.get_text(" ", strip=True) for c in rows[0].find_all(["td", "th"])]
            if not header or header[0].strip() != "Fecha":
                continue

            for row in rows[1:]:
                cells = row.find_all("td")
                if len(cells) < 2:
                    continue
                m = _FECHA_PATTERN.match(cells[0].get_text(" ", strip=True))
                if not m:
                    continue
                f_public = f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
                fechas_vistas.append(f_public)

                if f_public < fini or f_public > ffin:
                    continue

                a = cells[1].find("a", href=True)
                if not a:
                    continue
                url = urljoin(_BASE_URL, a["href"])
                if not self._es_url_propia(url) or url in vistos:
                    continue
                vistos.add(url)

                titulo = a.get_text(strip=True)
                descripcion = cells[2].get_text(" ", strip=True) if len(cells) > 2 else ""

                docs.append(RawDocModel(
                    source=self.source,
                    link={"url": url, "method": "GET"},
                    title=titulo,
                    tipo=tipo,
                    detalle=descripcion or None,
                    f_public=f_public,
                    save_path=storage_path(self.source, f_public, tipo, "(filename)(extension)"),
                ))

        return docs, fechas_vistas

    def _extraer_next_links(self, html: str) -> List[str]:
        return [
            urljoin(_BASE_URL, m.group(1).replace("&amp;", "&"))
            for m in _NEXT_LINK_PATTERN.finditer(html)
        ]

    def scrap(self, fini, ffin, q="", limit=10000, stop_event=None, on_progress=None) -> List[RawDocModel]:
        session = requests.Session()
        session.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})

        docs = []
        vistos: set = set()

        for path, tipo in _CATEGORIAS.items():
            if stop_event is not None and stop_event.is_set():
                return docs
            if on_progress:
                on_progress(f"[{self.source}] Procesando {tipo}...")

            # BFS sobre los enlaces "Siguiente": la biblioteca propia y la lista
            # mixta paginan de forma independiente, cada "Siguiente" trae su propio
            # cursor de continuación, así que no hace falta correlacionarlas a mano
            queue = [f"{_BASE_URL}{path}"]
            visitadas: set = set()
            paginas = 0

            while queue and paginas < _MAX_PAGINAS_POR_CATEGORIA:
                if stop_event is not None and stop_event.is_set():
                    return docs
                url = queue.pop(0)
                if url in visitadas:
                    continue
                visitadas.add(url)
                paginas += 1

                try:
                    resp = session.get(url, timeout=30)
                    resp.raise_for_status()
                except Exception:
                    continue

                nuevos, fechas = self._extraer_filas(resp.text, tipo, fini, ffin, vistos)
                docs.extend(nuevos)
                if len(docs) >= limit:
                    return docs[:limit]

                # las filas vienen ordenadas por fecha descendente; si ya pasamos
                # el inicio del rango en esta página, no vale la pena seguir esa
                # cadena de paginación (solo vamos a encontrar fechas más viejas)
                if fechas and min(fechas) < fini:
                    continue

                for next_url in self._extraer_next_links(resp.text):
                    if next_url not in visitadas:
                        queue.append(next_url)

        return docs
```

- [ ] **Step 4: Registrar la familia**

Modificar `core/scrapers/families/__init__.py`:

Antes:
```python
from . import constitucional, samai, corte_suprema, jep, cndj, adr  # noqa: F401
```

Después:
```python
from . import constitucional, samai, corte_suprema, jep, cndj, adr, adres  # noqa: F401
```

- [ ] **Step 5: Confirmar que el test pasa**

Run: `.venv\Scripts\pytest tests/families/test_adres.py -v`
Expected: PASS (4 tests)

- [ ] **Step 6: Validación en vivo**

Run:
```
.venv\Scripts\python -c "from core.scrapers.families.adres import ScrapADRES; docs = ScrapADRES().scrap(fini='2024-01-01', ffin='2024-12-31'); print(len(docs)); print(docs[0].title if docs else 'sin resultados')"
```
Reportar el conteo real y confirmar que no lanzó excepciones.

- [ ] **Step 7: Commit**

```bash
git add core/scrapers/families/adres.py core/scrapers/families/__init__.py tests/families/test_adres.py
git commit -m "feat: port ADRES scraper family"
```

---

### Task 6: Agencia Nacional del Espectro (`ane`)

**Files:**
- Create: `core/scrapers/families/ane.py`
- Modify: `core/scrapers/families/__init__.py`
- Test: `tests/families/test_ane.py`

**Interfaces:**
- Consumes: igual que Task 1.
- Produces: clase `ScrapANE` registrada bajo `"ane"`, instanciable sin argumentos. Usada por Task 9 para crear la fuente "Agencia Nacional del Espectro".

- [ ] **Step 1: Escribir el test**

Crear `tests/families/test_ane.py`:

```python
import json
from urllib.parse import parse_qs, urlparse

import responses

from core.scrapers.families.ane import ScrapANE, _LIST_API
from core.scrapers.registry import FAMILY_REGISTRY

_ROOT_ID = 711


@responses.activate
def test_scrap_recurses_tree_and_filters_by_full_date():
    def _callback(request):
        qs = parse_qs(urlparse(request.url).query)
        filtro = qs.get("$filter", [""])[0]
        if filtro == f"padre eq {_ROOT_ID}":
            value = [
                {"ID": 900, "Title": "Resoluciones", "tipoContenido": "Carpeta", "archivo": None, "vigencia": None},
            ]
        elif filtro == "padre eq 900":
            value = [
                {
                    "ID": 901,
                    "Title": "Resolución 500 del 10 de mayo de 2024",
                    "tipoContenido": "Archivo",
                    "archivo": {"Url": "https://ane.gov.co/files/resolucion-500.pdf"},
                    "vigencia": None,
                },
            ]
        else:
            value = []
        return (200, {"Content-Type": "application/json"}, json.dumps({"value": value}))

    responses.add_callback(responses.GET, _LIST_API, callback=_callback, content_type="application/json")

    scraper = ScrapANE()
    docs = scraper.scrap(fini="2024-01-01", ffin="2024-12-31")

    assert len(docs) == 1
    assert docs[0].title == "Resolución 500 del 10 de mayo de 2024"
    assert docs[0].f_public == "2024-05-10"
    assert docs[0].tipo == "Resolución"
    assert docs[0].link["url"] == "https://ane.gov.co/files/resolucion-500.pdf"


@responses.activate
def test_scrap_skips_normograma_and_foreign_domains():
    def _callback(request):
        qs = parse_qs(urlparse(request.url).query)
        filtro = qs.get("$filter", [""])[0]
        if filtro == f"padre eq {_ROOT_ID}":
            value = [
                {"ID": 902, "Title": "Normograma general", "tipoContenido": "Archivo",
                 "archivo": {"Url": "https://ane.gov.co/files/normograma.pdf"}, "vigencia": None},
                {"ID": 903, "Title": "Documento externo 2024", "tipoContenido": "Archivo",
                 "archivo": {"Url": "https://external.example.com/doc.pdf"}, "vigencia": "2024"},
            ]
        else:
            value = []
        return (200, {"Content-Type": "application/json"}, json.dumps({"value": value}))

    responses.add_callback(responses.GET, _LIST_API, callback=_callback, content_type="application/json")

    scraper = ScrapANE()
    docs = scraper.scrap(fini="2024-01-01", ffin="2024-12-31")

    assert docs == []


def test_ane_is_registered_under_its_family_key():
    import core.scrapers.families  # noqa: F401

    assert FAMILY_REGISTRY["ane"] is ScrapANE
```

- [ ] **Step 2: Confirmar que falla**

Run: `.venv\Scripts\pytest tests/families/test_ane.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'core.scrapers.families.ane'`

- [ ] **Step 3: Crear el módulo portado**

Crear `core/scrapers/families/ane.py`:

```python
import re
import unicodedata
from typing import List
from urllib.parse import urlparse

import requests

from core.models import RawDocModel
from core.scrapers.base import BaseScrapper
from core.scrapers.registry import register_family
from core.utils import storage_path

_BASE_URL = "https://ane.gov.co"
_LIST_API = f"{_BASE_URL}/_api/web/lists/getbytitle('contenidos')/items"
_ALLOWED_DOMAIN = "ane.gov.co"

# "Normativa aplicable" — la sección raíz que corresponde a la URL que se compartió
# (?p=711). El árbol se recorre recursivamente vía SharePoint REST ("contenidos"
# list, campo "padre") hasta llegar a nodos tipoContenido="Archivo".
_ROOT_ID = 711

_MESES = {
    "ENERO": "01", "FEBRERO": "02", "MARZO": "03", "ABRIL": "04",
    "MAYO": "05", "JUNIO": "06", "JULIO": "07", "AGOSTO": "08",
    "SEPTIEMBRE": "09", "OCTUBRE": "10", "NOVIEMBRE": "11", "DICIEMBRE": "12",
}
_FULL_DATE_PATTERN = re.compile(
    r"(\d{1,2})\s+DE[L]?\s+(ENERO|FEBRERO|MARZO|ABRIL|MAYO|JUNIO|JULIO|AGOSTO"
    r"|SEPTIEMBRE|OCTUBRE|NOVIEMBRE|DICIEMBRE)\s+DE[L]?\s+(\d{4})",
    re.IGNORECASE,
)
_YEAR_ONLY_PATTERN = re.compile(r"\bDE[L]?\s+(\d{4})\b", re.IGNORECASE)


def _parse_full_date(text: str):
    m = _FULL_DATE_PATTERN.search(text.upper())
    if m:
        day = m.group(1).zfill(2)
        month = _MESES[m.group(2).upper()]
        year = int(m.group(3))
        if 1990 <= year <= 2100:
            return f"{year}-{month}-{day}"
    return None


def _parse_year_only(text: str):
    m = _YEAR_ONLY_PATTERN.search(text.upper())
    if m and 1990 <= int(m.group(1)) <= 2100:
        return int(m.group(1))
    return None


@register_family("ane")
class ScrapANE(BaseScrapper):
    def __init__(self):
        self.source = "Agencia Nacional del Espectro"

    def _hijos(self, session, padre_id):
        params = {
            "$filter": f"padre eq {padre_id}",
            "$select": "ID,Title,tipoContenido,archivo,vigencia",
            "$top": "500",
        }
        resp = session.get(_LIST_API, params=params, timeout=30)
        resp.raise_for_status()
        return resp.json().get("value", [])

    def _es_url_propia(self, url: str) -> bool:
        try:
            return _ALLOWED_DOMAIN in urlparse(url).netloc
        except Exception:
            return False

    def scrap(self, fini, ffin, q="", limit=10000, stop_event=None, on_progress=None) -> List[RawDocModel]:
        session = requests.Session()
        session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            "Accept": "application/json;odata=nometadata",
        })

        anio_inicial = int(fini[:4])
        anio_final = int(ffin[:4])

        docs = []
        visitados = set()
        cola = [_ROOT_ID]

        while cola:
            if stop_event is not None and stop_event.is_set():
                return docs
            padre_id = cola.pop(0)
            if padre_id in visitados:
                continue
            visitados.add(padre_id)

            try:
                items = self._hijos(session, padre_id)
            except Exception as e:
                if on_progress:
                    on_progress(f"[{self.source}] Error consultando sección {padre_id}: {e}")
                continue

            for it in items:
                tipo_contenido = (it.get("tipoContenido") or "").strip()
                # algunos títulos vienen con acentos en forma NFD (o + combining
                # acute) en vez de NFC; normalizar evita que "Resolución" se
                # cuente como dos "tipo" distintos
                titulo = unicodedata.normalize("NFC", (it.get("Title") or "").strip())

                if tipo_contenido != "Archivo":
                    cola.append(it["ID"])
                    continue

                if titulo.lower().startswith("normograma"):
                    continue  # compendio temático sin fecha real por documento

                archivo = it.get("archivo") or {}
                url = archivo.get("Url") or ""
                if not url or not self._es_url_propia(url):
                    continue

                fecha_completa = _parse_full_date(titulo)
                if fecha_completa:
                    if fecha_completa < fini or fecha_completa > ffin:
                        continue
                    f_public = fecha_completa
                else:
                    anio = _parse_year_only(titulo)
                    if anio is None:
                        vigencia = str(it.get("vigencia") or "")
                        if vigencia.isdigit() and len(vigencia) == 4:
                            anio = int(vigencia)
                    if anio is None:
                        continue
                    if anio < anio_inicial or anio > anio_final:
                        continue
                    f_public = f"{anio}-01-01"

                palabras = titulo.split()
                tipo = palabras[0] if palabras else "Documento"

                docs.append(RawDocModel(
                    source=self.source,
                    link={"url": url, "method": "GET"},
                    title=titulo,
                    tipo=tipo,
                    f_public=f_public,
                    save_path=storage_path(self.source, f_public, tipo, "(filename)(extension)"),
                ))
                if len(docs) >= limit:
                    return docs[:limit]

            if on_progress and items:
                on_progress(f"[{self.source}] Procesadas {len(visitados)} secciones, {len(docs)} documentos...")

        return docs
```

- [ ] **Step 4: Registrar la familia**

Modificar `core/scrapers/families/__init__.py`:

Antes:
```python
from . import constitucional, samai, corte_suprema, jep, cndj, adr, adres  # noqa: F401
```

Después:
```python
from . import constitucional, samai, corte_suprema, jep, cndj, adr, adres, ane  # noqa: F401
```

- [ ] **Step 5: Confirmar que el test pasa**

Run: `.venv\Scripts\pytest tests/families/test_ane.py -v`
Expected: PASS (3 tests)

- [ ] **Step 6: Validación en vivo**

Run:
```
.venv\Scripts\python -c "from core.scrapers.families.ane import ScrapANE; docs = ScrapANE().scrap(fini='2023-01-01', ffin='2024-12-31'); print(len(docs)); print(docs[0].title if docs else 'sin resultados')"
```
Reportar el conteo real. Este scraper recorre un árbol vía SharePoint REST; puede tardar más que los demás — es esperado.

- [ ] **Step 7: Commit**

```bash
git add core/scrapers/families/ane.py core/scrapers/families/__init__.py tests/families/test_ane.py
git commit -m "feat: port Agencia Nacional del Espectro scraper family"
```

---

### Task 7: Agencia Nacional de Hidrocarburos (`anh`)

**Files:**
- Create: `core/scrapers/families/anh.py`
- Modify: `core/scrapers/families/__init__.py`
- Test: `tests/families/test_anh.py`

**Interfaces:**
- Consumes: igual que Task 1.
- Produces: clase `ScrapANH` registrada bajo `"anh"`, instanciable sin argumentos. Usada por Task 9 para crear la fuente "Agencia Nacional de Hidrocarburos".

- [ ] **Step 1: Escribir el test**

Crear `tests/families/test_anh.py`:

```python
import responses

from core.scrapers.families.anh import ScrapANH, _LIST_URL
from core.scrapers.registry import FAMILY_REGISTRY

_PAGE_HTML = """
<table>
<tr><th>Tipo</th><th>Tipo</th><th>Numero</th><th>Fecha</th><th>Descripcion</th><th>Accion</th></tr>
<tr>
  <td>x</td><td>Resolución</td><td>500</td><td>10 de mayo de 2024</td><td>Descripción de prueba</td>
  <td><a href="/files/resolucion-500.pdf">Descargar</a></td>
</tr>
</table>
"""


@responses.activate
def test_scrap_parses_table_and_stops_without_pagination():
    responses.add(responses.GET, _LIST_URL, body=_PAGE_HTML, status=200)

    scraper = ScrapANH()
    docs = scraper.scrap(fini="2024-01-01", ffin="2024-12-31")

    assert len(docs) == 1
    assert docs[0].title == "Resolución 500 de 2024"
    assert docs[0].f_public == "2024-05-10"
    assert docs[0].tipo == "Resolución"
    assert docs[0].link["url"] == "https://www.anh.gov.co/files/resolucion-500.pdf"
    assert len(responses.calls) == 1  # sin bloque de paginación, no debe pedir una página 2


def test_anh_is_registered_under_its_family_key():
    import core.scrapers.families  # noqa: F401

    assert FAMILY_REGISTRY["anh"] is ScrapANH
```

- [ ] **Step 2: Confirmar que falla**

Run: `.venv\Scripts\pytest tests/families/test_anh.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'core.scrapers.families.anh'`

- [ ] **Step 3: Crear el módulo portado**

Crear `core/scrapers/families/anh.py`:

```python
import re
from typing import List
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from core.models import RawDocModel
from core.scrapers.base import BaseScrapper
from core.scrapers.registry import register_family
from core.utils import storage_path

_BASE_URL = "https://www.anh.gov.co"
_LIST_URL = f"{_BASE_URL}/es/normatividad2/normatividad/"

_MESES = {
    "ENERO": "01", "FEBRERO": "02", "MARZO": "03", "ABRIL": "04",
    "MAYO": "05", "JUNIO": "06", "JULIO": "07", "AGOSTO": "08",
    "SEPTIEMBRE": "09", "OCTUBRE": "10", "NOVIEMBRE": "11", "DICIEMBRE": "12",
}
_DATE_PATTERN = re.compile(
    r"(\d{1,2})\s+DE[L]?\s+(ENERO|FEBRERO|MARZO|ABRIL|MAYO|JUNIO|JULIO|AGOSTO"
    r"|SEPTIEMBRE|OCTUBRE|NOVIEMBRE|DICIEMBRE)\s+DE[L]?\s+(\d{4})",
    re.IGNORECASE,
)
_MAX_PAGINAS = 60


def _parse_fecha(text: str):
    m = _DATE_PATTERN.search(text.upper())
    if m:
        day = m.group(1).zfill(2)
        month = _MESES[m.group(2).upper()]
        year = int(m.group(3))
        if 1990 <= year <= 2100:
            return f"{year}-{month}-{day}"
    return None


@register_family("anh")
class ScrapANH(BaseScrapper):
    def __init__(self):
        self.source = "Agencia Nacional de Hidrocarburos"

    def scrap(self, fini, ffin, q="", limit=10000, stop_event=None, on_progress=None) -> List[RawDocModel]:
        session = requests.Session()
        session.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})

        docs = []

        for pagina in range(1, _MAX_PAGINAS + 1):
            if stop_event is not None and stop_event.is_set():
                return docs
            if on_progress:
                on_progress(f"[{self.source}] Página {pagina}...")

            params = {"start_date": fini, "end_date": ffin, "page": pagina}
            try:
                resp = session.get(_LIST_URL, params=params, timeout=30)
                resp.raise_for_status()
            except Exception as e:
                if on_progress:
                    on_progress(f"[{self.source}] Error en página {pagina}: {e}")
                break

            soup = BeautifulSoup(resp.text, "html.parser")
            table = soup.find("table")
            if not table:
                break
            rows = table.find_all("tr")[1:]  # saltar encabezado
            if not rows:
                break

            for row in rows:
                cells = row.find_all("td")
                if len(cells) < 6:
                    continue

                tipo = cells[1].get_text(strip=True)
                numero = cells[2].get_text(strip=True)
                fecha_txt = cells[3].get_text(strip=True)
                descripcion = cells[4].get_text(" ", strip=True)

                f_public = _parse_fecha(fecha_txt)
                if not f_public:
                    continue

                a_descargar = cells[5].find("a", string=lambda s: s and "descargar" in s.lower())
                if not a_descargar or not a_descargar.get("href"):
                    continue
                url = urljoin(_BASE_URL, a_descargar["href"])

                anio = f_public[:4]
                titulo = f"{tipo} {numero} de {anio}"

                docs.append(RawDocModel(
                    source=self.source,
                    link={"url": url, "method": "GET"},
                    title=titulo,
                    tipo=tipo,
                    detalle=descripcion or None,
                    f_public=f_public,
                    save_path=storage_path(self.source, f_public, tipo, "(filename)(extension)"),
                ))
                if len(docs) >= limit:
                    return docs[:limit]

            pagination = soup.find("ul", class_="pagination")
            if pagination is None:
                break
            paginas_disponibles = [
                a.get_text(strip=True) for a in pagination.find_all("a", class_="page-link")
                if a.get_text(strip=True).isdigit()
            ]
            if not paginas_disponibles or pagina >= int(max(paginas_disponibles)):
                break

        return docs
```

- [ ] **Step 4: Registrar la familia**

Modificar `core/scrapers/families/__init__.py`:

Antes:
```python
from . import constitucional, samai, corte_suprema, jep, cndj, adr, adres, ane  # noqa: F401
```

Después:
```python
from . import constitucional, samai, corte_suprema, jep, cndj, adr, adres, ane, anh  # noqa: F401
```

- [ ] **Step 5: Confirmar que el test pasa**

Run: `.venv\Scripts\pytest tests/families/test_anh.py -v`
Expected: PASS (2 tests)

- [ ] **Step 6: Validación en vivo**

Run:
```
.venv\Scripts\python -c "from core.scrapers.families.anh import ScrapANH; docs = ScrapANH().scrap(fini='2024-01-01', ffin='2024-12-31'); print(len(docs)); print(docs[0].title if docs else 'sin resultados')"
```
Reportar el conteo real.

- [ ] **Step 7: Commit**

```bash
git add core/scrapers/families/anh.py core/scrapers/families/__init__.py tests/families/test_anh.py
git commit -m "feat: port Agencia Nacional de Hidrocarburos scraper family"
```

---

### Task 8: Rama Judicial — Tribunales Superiores y Juzgados (`rama_judicial`)

**Files:**
- Create: `core/scrapers/families/rama_judicial.py`
- Modify: `core/scrapers/families/__init__.py`
- Test: `tests/families/test_rama_judicial.py`

**Interfaces:**
- Consumes: igual que Task 1.
- Produces: clase `ScrapRamaJudicial(dept_code="", dept_name="Rama Judicial", entidad_id="22")` registrada bajo `"rama_judicial"`, más los diccionarios públicos `SUPERIORES_DEPTS` (32 entradas, `dept_code -> dept_name`) y `JUZGADOS_ENTIDADES` (6 entradas, `entidad_id -> juz_name`). Usados por Task 9 para crear las 38 fuentes con fan-out (mismo patrón que `SAMAI_CORPS` en `core/scrapers/families/samai.py`).

- [ ] **Step 1: Escribir el test**

Crear `tests/families/test_rama_judicial.py`:

```python
import responses

from core.scrapers.families.rama_judicial import (
    JUZGADOS_ENTIDADES,
    SUPERIORES_DEPTS,
    ScrapRamaJudicial,
)
from core.scrapers.registry import FAMILY_REGISTRY

_BASE_DOMAIN = "https://publicacionesprocesales.ramajudicial.gov.co"

_DETAIL_HTML = """
<table id="tabla-docs-1"><tbody>
<tr><td><a href="/descargas/archivo.pdf?uuid=abc-123">Auto_2024.pdf</a></td></tr>
</tbody></table>
"""

_LISTING_HTML = """
<html><body>
<span>Página 1 de 1</span>
<tbody class="table-data">
<tr>
  <div class="titulo-publicacion"><a href="https://publicacionesprocesales.ramajudicial.gov.co/detalle/1">Ver</a></div>
  <p class="publish-date">Fecha: 15/06/2024</p>
  <span class="categoria-ep">Tipo de publicación: Sentencias</span>
  <span class="categoria-ep">Especialidad: Civil</span>
  <span class="categoria-ep">Despacho: Juzgado 1 Civil del Circuito</span>
</tr>
</tbody>
</body></html>
"""


def test_superiores_depts_and_juzgados_entidades_counts():
    assert len(SUPERIORES_DEPTS) == 32
    assert SUPERIORES_DEPTS["05"] == "Tribunal Superior de Antioquia"
    assert len(JUZGADOS_ENTIDADES) == 6
    assert JUZGADOS_ENTIDADES["31"] == "Juzgado de Circuito"


@responses.activate
def test_fetch_detail_parses_file_table():
    responses.add(responses.GET, _BASE_DOMAIN + "/detalle/1", body=_DETAIL_HTML, status=200)

    scraper = ScrapRamaJudicial(dept_code="05", dept_name="Tribunal Superior de Antioquia", entidad_id="22")
    files = scraper._fetch_detail({"User-Agent": "test"}, _BASE_DOMAIN + "/detalle/1")

    assert files == [("Auto_2024.pdf", _BASE_DOMAIN + "/descargas/archivo.pdf?uuid=abc-123", "abc-123")]


@responses.activate
def test_scrap_builds_docs_from_listing_and_detail(monkeypatch):
    responses.add(
        responses.GET,
        "https://publicacionesprocesales.ramajudicial.gov.co/web/publicaciones-procesales/inicio",
        body=_LISTING_HTML,
        status=200,
    )

    scraper = ScrapRamaJudicial(dept_code="05", dept_name="Tribunal Superior de Antioquia", entidad_id="22")
    monkeypatch.setattr(scraper, "_get_instance_id", lambda session, headers: "XYZ")
    monkeypatch.setattr(
        scraper,
        "_fetch_detail",
        lambda headers, url: [("Auto_2024.pdf", _BASE_DOMAIN + "/descargas/archivo.pdf?uuid=abc-123", "abc-123")],
    )

    docs = scraper.scrap(fini="2024-01-01", ffin="2024-12-31")

    assert len(docs) == 1
    doc = docs[0]
    assert doc.title == "Auto_2024"
    assert doc.tipo == "Sentencias"
    assert doc.especialidad == "Civil"
    assert doc.seccion == "Juzgado 1 Civil del Circuito"
    assert doc.f_public == "15/06/2024"
    assert doc.convert_to == "rtf"
    assert doc.link == {
        "url": _BASE_DOMAIN + "/descargas/archivo.pdf?uuid=abc-123",
        "method": "GET",
        "body": {"path": "abc-123"},
    }
    assert doc.save_path == (
        "Tribunal Superior de Antioquia/Civil/Juzgado 1 Civil del Circuito/15/06/2024/Sentencias/Auto_2024(extension)"
    )


def test_rama_judicial_is_registered_under_its_family_key():
    import core.scrapers.families  # noqa: F401

    assert FAMILY_REGISTRY["rama_judicial"] is ScrapRamaJudicial
```

- [ ] **Step 2: Confirmar que falla**

Run: `.venv\Scripts\pytest tests/families/test_rama_judicial.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'core.scrapers.families.rama_judicial'`

- [ ] **Step 3: Crear el módulo portado**

Crear `core/scrapers/families/rama_judicial.py`:

```python
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List

import requests
from bs4 import BeautifulSoup

from core.models import RawDocModel
from core.scrapers.base import BaseScrapper
from core.scrapers.registry import register_family
from core.utils import storage_path

_TRIBUNALES_SUPERIORES_URL = "https://publicacionesprocesales.ramajudicial.gov.co/web/publicaciones-procesales/inicio"
_BASE_DOMAIN = "https://publicacionesprocesales.ramajudicial.gov.co"
_PORTLET = "co_com_avanti_efectosProcesales_PublicacionesEfectosProcesalesPortletV2_INSTANCE"
_INVALID_PATH_CHARS = re.compile(r'[<>:"/\\|?*]')
_TIPOS_PERMITIDOS = {
    "Notificaciones por Estados",
    "Acciones de Tutela",
    "Sentencias",
    "Autos masivo",
}
_DETAIL_WORKERS = 5

# Público: enumerado por core/seed.py para crear una Source por cada tribunal superior.
SUPERIORES_DEPTS = {
    "05": "Tribunal Superior de Antioquia",
    "08": "Tribunal Superior del Atlántico",
    "11": "Tribunal Superior de Bogotá",
    "13": "Tribunal Superior de Bolívar",
    "15": "Tribunal Superior de Boyacá",
    "17": "Tribunal Superior de Caldas",
    "18": "Tribunal Superior del Caquetá",
    "19": "Tribunal Superior del Cauca",
    "20": "Tribunal Superior del Cesar",
    "23": "Tribunal Superior de Córdoba",
    "25": "Tribunal Superior de Cundinamarca",
    "27": "Tribunal Superior del Chocó",
    "41": "Tribunal Superior del Huila",
    "44": "Tribunal Superior de la Guajira",
    "47": "Tribunal Superior del Magdalena",
    "50": "Tribunal Superior del Meta",
    "52": "Tribunal Superior de Nariño",
    "54": "Tribunal Superior de Norte de Santander",
    "63": "Tribunal Superior del Quindío",
    "66": "Tribunal Superior de Risaralda",
    "68": "Tribunal Superior de Santander",
    "70": "Tribunal Superior de Sucre",
    "73": "Tribunal Superior del Tolima",
    "76": "Tribunal Superior del Valle del Cauca",
    "81": "Tribunal Superior de Arauca",
    "85": "Tribunal Superior de Casanare",
    "86": "Tribunal Superior del Putumayo",
    "88": "Tribunal Superior de San Andrés",
    "91": "Tribunal Superior del Amazonas",
    "94": "Tribunal Superior de Guainía",
    "95": "Tribunal Superior del Guaviare",
    "97": "Tribunal Superior del Vaupés",
    "99": "Tribunal Superior del Vichada",
}

# Público: enumerado por core/seed.py para crear una Source por cada tipo de juzgado.
JUZGADOS_ENTIDADES = {
    "31": "Juzgado de Circuito",
    "33": "Juzgado Administrativo",
    "34": "Juzgado de Circuito de Ejecución",
    "40": "Juzgado Municipal",
    "41": "Juzgado de Pequeñas Causas",
    "43": "Juzgado Municipal de Ejecución",
}


@register_family("rama_judicial")
class ScrapRamaJudicial(BaseScrapper):
    def __init__(self, dept_code: str = "", dept_name: str = "Rama Judicial", entidad_id: str = "22"):
        self.source = dept_name
        self.url = _TRIBUNALES_SUPERIORES_URL
        self._dept_code = dept_code
        self._entidad_id = entidad_id
        self._instance_id = None

    def _get_instance_id(self, session, headers):
        for attempt in range(3):
            try:
                resp = session.get(self.url, headers=headers, timeout=60)
                if resp.status_code < 500:
                    break
            except requests.exceptions.Timeout:
                if attempt == 2:
                    raise
        resp.raise_for_status()
        match = re.search(rf'p_p_id_{_PORTLET}_([A-Za-z0-9]+)_', resp.text)
        if not match:
            raise Exception(
                "No se encontró instance_id. El sitio puede haber cambiado su estructura."
            )
        return match.group(1)

    def _p(self, key):
        return f"_{_PORTLET}_{self._instance_id}_{key}"

    def _fetch_detail(self, headers, detail_url):
        """Fetch a detail page in its own session (thread-safe) and return file list."""
        s = requests.Session()
        for attempt in range(3):
            try:
                resp = s.get(detail_url, headers=headers, timeout=60)
                if resp.status_code < 500:
                    break
            except requests.exceptions.Timeout:
                if attempt == 2:
                    return []
        try:
            resp.raise_for_status()
        except Exception:
            return []

        soup = BeautifulSoup(resp.text, "html.parser")
        files = []
        table = soup.find("table", id=re.compile(r"tabla-docs"))
        if not table:
            return files
        tbody = table.find("tbody")
        if not tbody:
            return files

        for row in tbody.find_all("tr"):
            a = row.find("a")
            if not a:
                continue
            filename = a.text.strip()
            href = a.get("href", "")
            if not href:
                continue
            download_url = (_BASE_DOMAIN + href) if href.startswith("/") else href
            uuid_match = re.search(r'uuid=([^&]+)', href)
            file_uuid = uuid_match.group(1) if uuid_match else filename
            files.append((filename, download_url, file_uuid))

        return files

    def scrap(self, fini, ffin, q="", limit=10, stop_event=None, on_progress=None) -> List[RawDocModel]:
        session = requests.Session()
        headers = {"User-Agent": "Mozilla/5.0"}

        self._instance_id = self._get_instance_id(session, headers)
        p_p_id = f"{_PORTLET}_{self._instance_id}"

        docs = []
        num_pag = 1
        max_pages = None

        while True:
            params = {
                "p_p_id": p_p_id,
                "p_p_lifecycle": 0,
                "p_p_state": "normal",
                "p_p_mode": "view",
                self._p("action"): "busqueda",
                self._p("idEntidad"): self._entidad_id,
                self._p("fechaInicio"): fini,
                self._p("fechaFin"): ffin,
                self._p("verTotales"): "true",
                self._p("delta"): limit,
                self._p("resetCur"): "false",
                self._p("cur"): num_pag,
            }
            if self._dept_code:
                params[self._p("idDepto")] = self._dept_code

            for attempt in range(3):
                try:
                    response = session.get(self.url, params=params, headers=headers, timeout=60)
                    if response.status_code < 500:
                        break
                except requests.exceptions.Timeout:
                    if attempt == 2:
                        raise
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")

            if max_pages is None:
                page_span = soup.find("span", string=re.compile(r"Página 1 de \d+"))
                if page_span:
                    m = re.search(r"Página 1 de (\d+)", page_span.text)
                    max_pages = int(m.group(1)) if m else 1
                else:
                    max_pages = 1

            tbody = soup.find("tbody", {"class": "table-data"})
            if not tbody:
                break
            rows = tbody.find_all("tr")
            if not rows:
                break

            pending = []
            for row in rows:
                if stop_event is not None and stop_event.is_set():
                    return docs
                try:
                    title_tag = row.find("div", class_="titulo-publicacion")
                    if not title_tag:
                        continue
                    a_tag = title_tag.find("a")
                    if not a_tag:
                        continue

                    fecha_p_tag = row.find("p", class_="publish-date")
                    if not fecha_p_tag:
                        continue
                    fecha_p = fecha_p_tag.text.split(":")[-1].strip()

                    categorias = {}
                    for span in row.find_all("span", class_="categoria-ep"):
                        text = span.text.strip()
                        if ":" in text:
                            k, v = text.split(":", 1)
                            categorias[k.strip()] = v.strip()

                    tipo = categorias.get("Tipo de publicación", "")
                    if tipo not in _TIPOS_PERMITIDOS:
                        continue

                    especialidad_raw = categorias.get("Especialidad", "sin-especialidad")
                    despacho_raw = categorias.get("Despacho", "")
                    especialidad_dir = _INVALID_PATH_CHARS.sub("-", especialidad_raw)[:60]
                    despacho_dir = _INVALID_PATH_CHARS.sub("-", despacho_raw)[:60]
                    tipo_dir = _INVALID_PATH_CHARS.sub("-", tipo)

                    detail_url = a_tag.get("href", "")
                    if not detail_url:
                        continue

                    pending.append((fecha_p, tipo, tipo_dir, especialidad_dir, despacho_dir, detail_url))
                except Exception as e:
                    print(f"Error procesando fila: {e}")
                    continue

            if on_progress and pending:
                on_progress(f"[{self.source}] Obteniendo {len(pending)} detalles en paralelo…")

            with ThreadPoolExecutor(max_workers=_DETAIL_WORKERS) as executor:
                future_to_meta = {
                    executor.submit(self._fetch_detail, headers, item[-1]): item
                    for item in pending
                }
                for future in as_completed(future_to_meta):
                    if stop_event is not None and stop_event.is_set():
                        return docs
                    fecha_p, tipo, tipo_dir, especialidad_dir, despacho_dir, _ = future_to_meta[future]
                    try:
                        archivos = future.result()
                    except Exception:
                        continue

                    for filename, download_url, file_uuid in archivos:
                        name_no_ext = (filename.rsplit(".", 1)[0] if "." in filename else filename).strip()
                        doc_name = _INVALID_PATH_CHARS.sub("-", name_no_ext)
                        # mismo orden que las demás fuentes: clasificación → fecha → tipo
                        save_path = storage_path(
                            self.source, especialidad_dir, despacho_dir, fecha_p, tipo_dir, f"{doc_name}(extension)"
                        )
                        docs.append(RawDocModel(
                            source=self.source,
                            link={"url": download_url, "method": "GET", "body": {"path": file_uuid}},
                            title=name_no_ext,
                            tipo=tipo,
                            especialidad=especialidad_dir,
                            seccion=despacho_dir,
                            f_public=fecha_p,
                            save_path=save_path,
                            convert_to="rtf",
                        ))

            if num_pag >= max_pages:
                break
            num_pag += 1

        return docs
```

- [ ] **Step 4: Registrar la familia**

Modificar `core/scrapers/families/__init__.py`:

Antes:
```python
from . import constitucional, samai, corte_suprema, jep, cndj, adr, adres, ane, anh  # noqa: F401
```

Después:
```python
from . import constitucional, samai, corte_suprema, jep, cndj, adr, adres, ane, anh, rama_judicial  # noqa: F401
```

- [ ] **Step 5: Confirmar que el test pasa**

Run: `.venv\Scripts\pytest tests/families/test_rama_judicial.py -v`
Expected: PASS (4 tests)

- [ ] **Step 6: Validación en vivo**

Run:
```
.venv\Scripts\python -c "from core.scrapers.families.rama_judicial import ScrapRamaJudicial; docs = ScrapRamaJudicial(dept_code='05', dept_name='Tribunal Superior de Antioquia', entidad_id='22').scrap(fini='2026-07-01', ffin='2026-07-14', limit=5); print(len(docs)); print(docs[0].title if docs else 'sin resultados')"
```
Se valida con un solo tribunal representativo (Antioquia), no los 38 — el resto comparte la misma clase e instance_id-resolution, así que si este funciona, el patrón funciona para todos. Reportar el conteo real.

- [ ] **Step 7: Commit**

```bash
git add core/scrapers/families/rama_judicial.py core/scrapers/families/__init__.py tests/families/test_rama_judicial.py
git commit -m "feat: port Rama Judicial scraper family (Tribunales Superiores + Juzgados fan-out)"
```

---

### Task 9: Sembrar las 8 familias nuevas y verificación final

**Files:**
- Modify: `core/seed.py`
- Modify: `tests/test_seed.py`
- Modify: `README.md`

**Interfaces:**
- Consumes: `SUPERIORES_DEPTS`/`JUZGADOS_ENTIDADES` de `core/scrapers/families/rama_judicial.py` (Task 8), `SAMAI_CORPS` de `core/scrapers/families/samai.py` (ya existente) — todos los nombres de clase/función de las 8 familias ya están registrados vía `@register_family`, así que `core/seed.py` no necesita importar las clases de scraper directamente, solo los diccionarios de fan-out.
- Produces: 74 `Source` rows totales (1 Corte Constitucional + 28 SAMAI + 7 de fuente única + 32 Tribunales Superiores + 6 Juzgados) y 10 `SourceFamily` rows, visibles de inmediato en `SourcesPage`/`RunsPage`/`DocumentsPage` del frontend sin cambios adicionales.

- [ ] **Step 1: Actualizar el test de seed (va a fallar hasta que se actualice `seed.py`)**

Modificar `tests/test_seed.py` (reemplazar el archivo completo):

```python
from core.db import repository
from core.seed import seed_source_families_and_sources


def test_seed_populates_families_and_sources_and_is_idempotent(db_session):
    seed_source_families_and_sources(db_session)
    seed_source_families_and_sources(db_session)  # running twice must not duplicate rows

    families = repository.list_source_families(db_session)
    assert {f.key for f in families} == {
        "constitucional", "samai", "corte_suprema", "jep", "cndj",
        "adr", "adres", "ane", "anh", "rama_judicial",
    }

    sources = repository.list_sources(db_session)
    # 1 (Corte Constitucional) + 28 (SAMAI) + 7 (fuente única: corte_suprema, jep, cndj,
    # adr, adres, ane, anh) + 32 (Tribunales Superiores) + 6 (tipos de Juzgado) = 74
    assert len(sources) == 1 + 28 + 7 + 32 + 6

    rama_judicial_sources = repository.list_sources(db_session, family_key="rama_judicial")
    assert len(rama_judicial_sources) == 38
    assert any(s.family_params.get("dept_code") == "05" for s in rama_judicial_sources)
    assert any(
        s.family_params.get("entidad_id") == "31" and s.family_params.get("dept_code") == ""
        for s in rama_judicial_sources
    )
```

- [ ] **Step 2: Confirmar que falla**

Run: `.venv\Scripts\pytest tests/test_seed.py -v`
Expected: FAIL — `AssertionError` porque `seed.py` todavía solo conoce `constitucional`/`samai`.

- [ ] **Step 3: Actualizar `core/seed.py`**

Reemplazar el archivo completo `core/seed.py`:

```python
from core.db import repository
from core.db.session import SessionLocal
from core.scrapers.families.rama_judicial import JUZGADOS_ENTIDADES, SUPERIORES_DEPTS
from core.scrapers.families.samai import SAMAI_CORPS

_FAMILIES = {
    "constitucional": ("Corte Constitucional", "Buscador de relatoría de la Corte Constitucional"),
    "samai": (
        "SAMAI (Tribunales Administrativos)",
        "Sistema SAMAI del Consejo de Estado; cubre Consejo de Estado y Tribunales Administrativos",
    ),
    "corte_suprema": (
        "Corte Suprema de Justicia",
        "API GraphQL de consulta de providencias de la Corte Suprema de Justicia",
    ),
    "jep": ("Jurisdicción Especial para la Paz", "API de relatoría de la JEP"),
    "cndj": ("Consejo Nacional de Disciplina Judicial", "Buscador de relatoría del CNDJ"),
    "adr": ("Agencia de Desarrollo Rural", "Normativa publicada por la Agencia de Desarrollo Rural"),
    "adres": (
        "Administradora de los Recursos del Sistema General de Seguridad Social en Salud",
        "Normativa publicada por ADRES",
    ),
    "ane": ("Agencia Nacional del Espectro", "Normativa publicada por la Agencia Nacional del Espectro"),
    "anh": ("Agencia Nacional de Hidrocarburos", "Normativa publicada por la Agencia Nacional de Hidrocarburos"),
    "rama_judicial": (
        "Rama Judicial (Tribunales Superiores y Juzgados)",
        "Publicaciones procesales de la Rama Judicial; cubre Tribunales Superiores por departamento y Juzgados por tipo",
    ),
}


def seed_source_families_and_sources(db) -> None:
    existing_families = {f.key for f in repository.list_source_families(db)}
    for key, (display_name, description) in _FAMILIES.items():
        if key not in existing_families:
            repository.create_source_family(db, key=key, display_name=display_name, description=description)

    existing_sources = {s.name for s in repository.list_sources(db)}

    if "Corte Constitucional" not in existing_sources:
        repository.create_source(db, family_key="constitucional", name="Corte Constitucional", family_params={})

    for corp_code, corp_name in SAMAI_CORPS.items():
        if corp_name not in existing_sources:
            repository.create_source(
                db, family_key="samai", name=corp_name, family_params={"corp_code": corp_code, "corp_name": corp_name}
            )

    if "CSJ" not in existing_sources:
        repository.create_source(db, family_key="corte_suprema", name="CSJ", family_params={})

    if "JEP" not in existing_sources:
        repository.create_source(db, family_key="jep", name="JEP", family_params={})

    if "Consejo Nacional de Disciplina Judicial" not in existing_sources:
        repository.create_source(
            db, family_key="cndj", name="Consejo Nacional de Disciplina Judicial", family_params={}
        )

    if "Agencia de Desarrollo Rural" not in existing_sources:
        repository.create_source(db, family_key="adr", name="Agencia de Desarrollo Rural", family_params={})

    adres_name = "Administradora de los Recursos del Sistema General de Seguridad Social en Salud"
    if adres_name not in existing_sources:
        repository.create_source(db, family_key="adres", name=adres_name, family_params={})

    if "Agencia Nacional del Espectro" not in existing_sources:
        repository.create_source(db, family_key="ane", name="Agencia Nacional del Espectro", family_params={})

    if "Agencia Nacional de Hidrocarburos" not in existing_sources:
        repository.create_source(db, family_key="anh", name="Agencia Nacional de Hidrocarburos", family_params={})

    for dept_code, dept_name in SUPERIORES_DEPTS.items():
        if dept_name not in existing_sources:
            repository.create_source(
                db,
                family_key="rama_judicial",
                name=dept_name,
                family_params={"dept_code": dept_code, "dept_name": dept_name, "entidad_id": "22"},
            )

    for juz_id, juz_name in JUZGADOS_ENTIDADES.items():
        if juz_name not in existing_sources:
            repository.create_source(
                db,
                family_key="rama_judicial",
                name=juz_name,
                family_params={"dept_code": "", "dept_name": juz_name, "entidad_id": juz_id},
            )


def main():
    db = SessionLocal()
    try:
        seed_source_families_and_sources(db)
    finally:
        db.close()


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Confirmar que el test de seed pasa**

Run: `.venv\Scripts\pytest tests/test_seed.py -v`
Expected: PASS (1 test)

- [ ] **Step 5: Actualizar el README**

Modificar `README.md`, sección "Alcance":

Antes:
```markdown
## Alcance

Este repo porta dos familias de scraping como prueba del modelo (`constitucional`, `samai`). Las demás familias de `WebScrapping_Fuentes` (Corte Suprema, JEP, CNDJ, Rama Judicial, ADR, ADRES, ANE, ANH) se portan siguiendo el mismo patrón de `core/scrapers/families/` + `@register_family(...)` como trabajo de seguimiento.
```

Después:
```markdown
## Alcance

Este repo porta las 10 familias de scraping de `WebScrapping_Fuentes` (`constitucional`, `samai`, `corte_suprema`, `jep`, `cndj`, `adr`, `adres`, `ane`, `anh`, `rama_judicial`), cada una siguiendo el patrón `core/scrapers/families/` + `@register_family(...)`.
```

- [ ] **Step 6: Correr la suite completa de backend**

Run: `.venv\Scripts\pytest -v`
Expected: PASS — todos los tests (los preexistentes + los 8 archivos nuevos de `tests/families/` + `test_seed.py` actualizado). Si `test_migrations.py` u otro test preexistente falla por razones no relacionadas a este trabajo (según la nota ya registrada en `.superpowers/sdd/progress.md` de una sesión anterior), documentarlo pero no bloquear por eso.

- [ ] **Step 7: Commit**

```bash
git add core/seed.py tests/test_seed.py README.md
git commit -m "feat: seed the 8 newly-ported scraper families (74 sources total)"
```

---

## Self-Review

**Spec coverage:** las 8 familias de la tabla del spec tienen su propia tarea (1-8); el seeding (incluido el fan-out de 38 fuentes de Rama Judicial) y la actualización del README están cubiertos en la Tarea 9; la validación en vivo por familia está en el Step 6 de cada tarea 1-8, con el ajuste explícito para CNDJ (chequeo ligero de estructura, no el `.scrap()` completo) justificado por el volumen de peticiones que implicaría iterar todos los magistrados. `core/downloader.py` y el frontend no se tocan en ninguna tarea, como exige el spec.

**Placeholder scan:** ningún paso usa "TBD"/"agregar validación apropiada"/"similar a la tarea N" — cada tarea trae el código completo, sin abreviar.

**Type consistency:** `family_key` usados en `core/seed.py` (Tarea 9) coinciden exactamente con los decoradores `@register_family(...)` de las Tareas 1-8 (`corte_suprema`, `jep`, `cndj`, `adr`, `adres`, `ane`, `anh`, `rama_judicial`). Los nombres de `Source` creados en la Tarea 9 (`"CSJ"`, `"JEP"`, etc.) coinciden con `self.source` de cada clase portada, para que el nombre mostrado en el frontend sea consistente con lo que el scraper reporta internamente. Los campos de `family_params` para `rama_judicial` (`dept_code`, `dept_name`, `entidad_id`) coinciden exactamente con la firma `__init__(self, dept_code="", dept_name="Rama Judicial", entidad_id="22")` de `ScrapRamaJudicial`.
