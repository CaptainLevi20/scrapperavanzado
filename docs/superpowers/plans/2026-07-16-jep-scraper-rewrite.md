# Reescritura del scraper de JEP (searchadv) — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reemplazar la fuente de datos del scraper de JEP (`listarProvidecias`, solo año, tipo adivinado) por `searchadv` (fecha completa, tipo estructurado, sin credenciales), permitiendo filtrar documentos con precisión real de fecha en vez de solo por año.

**Architecture:** Reescritura completa de `core/scrapers/families/jep.py`, mismo `family_key="jep"` (hoy no hay documentos de JEP guardados, no hace falta migración). Se itera por cada año del rango pedido, paginando `searchadv` con `per_page=200` hasta agotar el total de ese año, y se filtra client-side por `fecha_documento` exacta contra `[fini, ffin]`.

**Tech Stack:** Python + `requests` (ya usado por el resto de scrapers), `responses` para tests (mismo patrón ya establecido en el proyecto).

## Global Constraints

- Mismo `family_key` ("jep") y misma clase (`ScrapJEP`) — no se crea una familia nueva.
- Endpoint: `POST https://relatoria.jep.gov.co/searchadv`, sin credenciales, body con `anio` (obligatorio, string) + campos de texto vacíos + `page`/`per_page`. `per_page=200`.
- El filtrado por fecha exacta ocurre del lado del cliente comparando `fecha_documento` (formato `AAAA-MM-DD`) contra `[fini, ffin]` — el servidor solo filtra por año.
- Mapeo de campos exacto: `title=radicado_documento`, `tipo=tipo_documento`, `seccion=sala_seccion`, `f_providencia=fecha_documento`, `f_public=fecha_publicacion` (recortado a 10 caracteres, con fallback a `fecha_documento` si falta), deduplicación por `providencia_id`.
- `hipervinculo` se normaliza quitando cualquier "/" inicial antes de anteponer `https://relatoria.jep.gov.co/`.
- Documentos sin `fecha_documento` se descartan (no se puede saber si caen en rango).
- `stop_event` se revisa entre cada página, no solo entre años.
- Se elimina por completo `_extraer_tipo` y su lógica de reglas por prefijo de nombre de archivo — ya no hace falta, `tipo_documento` viene directo de la fuente.

---

### Task 1: Reescribir `ScrapJEP` sobre `searchadv`

**Files:**
- Modify: `core/scrapers/families/jep.py`
- Modify: `tests/families/test_jep.py`

**Interfaces:**
- Produces: `ScrapJEP.scrap(fini, ffin, q="", limit=10000, stop_event=None, on_progress=None) -> List[RawDocModel]` — misma firma pública que ya consume `worker/tasks.py::scrape_source_task` vía `resolve_scraper`, sin cambios en el contrato de llamada.
- No expone ninguna función nueva fuera del módulo — `_years_in_range` es un helper interno.

- [ ] **Step 1: Escribir los tests que fallan**

Reemplazar el contenido completo de `tests/families/test_jep.py` por:

```python
import responses
from responses import matchers

import core.scrapers.families.jep as jep_module
from core.scrapers.families.jep import ScrapJEP
from core.scrapers.registry import FAMILY_REGISTRY

_URL = "https://relatoria.jep.gov.co/searchadv"


def _hit(
    providencia_id,
    radicado_documento="SRVR-003",
    tipo_documento="Auto",
    sala_seccion="S - Sala de Amnistía o Indulto",
    fecha_documento="2024-07-06",
    fecha_publicacion="2024-08-01T05:00:00.000000Z",
    hipervinculo="documentos/providencias/1/1/Auto_SRVR-003_06-julio-2024.pdf",
):
    return {
        "_source": {
            "providencia_id": providencia_id,
            "radicado_documento": radicado_documento,
            "tipo_documento": tipo_documento,
            "sala_seccion": sala_seccion,
            "fecha_documento": fecha_documento,
            "fecha_publicacion": fecha_publicacion,
            "hipervinculo": hipervinculo,
        }
    }


def _response(hits, total=None):
    return {"reponse": {"hits": {"total": {"value": total if total is not None else len(hits)}, "hits": hits}}}


def _body_matcher(anio, page=1, per_page=200):
    return matchers.json_params_matcher(
        {
            "alguna_palabra": "",
            "todas_palabras": "",
            "frase_exacta": "",
            "ninguna_palabra": "",
            "anio": anio,
            "sala_seccion": "",
            "tipo_documento": "",
            "page": page,
            "per_page": per_page,
        }
    )


@responses.activate
def test_scrap_maps_fields_correctly():
    responses.add(
        responses.POST, _URL,
        json=_response([_hit(1)]),
        match=[_body_matcher("2024")],
        status=200,
    )

    scraper = ScrapJEP()
    docs = scraper.scrap(fini="2024-01-01", ffin="2024-12-31")

    assert len(docs) == 1
    doc = docs[0]
    assert doc.title == "SRVR-003"
    assert doc.tipo == "Auto"
    assert doc.seccion == "S - Sala de Amnistía o Indulto"
    assert doc.seccion_en_carpeta is False
    assert doc.f_public == "2024-08-01"
    assert doc.f_providencia == "2024-07-06"
    assert doc.link == {
        "url": "https://relatoria.jep.gov.co/documentos/providencias/1/1/Auto_SRVR-003_06-julio-2024.pdf",
        "method": "GET",
    }
    assert doc.save_path == "JEP/2024-08-01/Auto/SRVR-003-1(extension)"


@responses.activate
def test_scrap_filters_out_documents_outside_the_exact_date_range():
    responses.add(
        responses.POST, _URL,
        json=_response([
            _hit(1, radicado_documento="EN-RANGO", fecha_documento="2024-06-15"),
            _hit(2, radicado_documento="FUERA-DE-RANGO", fecha_documento="2024-01-05"),
        ]),
        match=[_body_matcher("2024")],
        status=200,
    )

    scraper = ScrapJEP()
    docs = scraper.scrap(fini="2024-06-01", ffin="2024-06-30")

    assert len(docs) == 1
    assert docs[0].title == "EN-RANGO"


@responses.activate
def test_scrap_normalizes_hipervinculo_with_and_without_leading_slash():
    responses.add(
        responses.POST, _URL,
        json=_response([
            _hit(1, radicado_documento="CON-SLASH", hipervinculo="/documentos/providencias/1/1/a.pdf"),
            _hit(2, radicado_documento="SIN-SLASH", hipervinculo="documentos/providencias/1/1/b.pdf"),
        ]),
        match=[_body_matcher("2024")],
        status=200,
    )

    scraper = ScrapJEP()
    docs = scraper.scrap(fini="2024-01-01", ffin="2024-12-31")

    links = {doc.title: doc.link["url"] for doc in docs}
    assert links["CON-SLASH"] == "https://relatoria.jep.gov.co/documentos/providencias/1/1/a.pdf"
    assert links["SIN-SLASH"] == "https://relatoria.jep.gov.co/documentos/providencias/1/1/b.pdf"


@responses.activate
def test_scrap_paginates_until_total_exhausted(monkeypatch):
    monkeypatch.setattr(jep_module, "_PER_PAGE", 2)
    responses.add(
        responses.POST, _URL,
        json=_response([_hit(1, radicado_documento="UNO"), _hit(2, radicado_documento="DOS")], total=3),
        match=[_body_matcher("2024", page=1, per_page=2)],
        status=200,
    )
    responses.add(
        responses.POST, _URL,
        json=_response([_hit(3, radicado_documento="TRES")], total=3),
        match=[_body_matcher("2024", page=2, per_page=2)],
        status=200,
    )

    scraper = ScrapJEP()
    docs = scraper.scrap(fini="2024-01-01", ffin="2024-12-31")

    assert {doc.title for doc in docs} == {"UNO", "DOS", "TRES"}


@responses.activate
def test_scrap_deduplicates_repeated_providencia_id():
    responses.add(
        responses.POST, _URL,
        json=_response([_hit(1, radicado_documento="REPETIDO"), _hit(1, radicado_documento="REPETIDO")]),
        match=[_body_matcher("2024")],
        status=200,
    )

    scraper = ScrapJEP()
    docs = scraper.scrap(fini="2024-01-01", ffin="2024-12-31")

    assert len(docs) == 1


@responses.activate
def test_scrap_falls_back_to_fecha_documento_when_fecha_publicacion_missing():
    responses.add(
        responses.POST, _URL,
        json=_response([_hit(1, fecha_documento="2024-03-10", fecha_publicacion=None)]),
        match=[_body_matcher("2024")],
        status=200,
    )

    scraper = ScrapJEP()
    docs = scraper.scrap(fini="2024-01-01", ffin="2024-12-31")

    assert docs[0].f_public == "2024-03-10"


@responses.activate
def test_scrap_skips_document_missing_fecha_documento():
    responses.add(
        responses.POST, _URL,
        json=_response([_hit(1, fecha_documento=None), _hit(2, radicado_documento="VALIDO")]),
        match=[_body_matcher("2024")],
        status=200,
    )

    scraper = ScrapJEP()
    docs = scraper.scrap(fini="2024-01-01", ffin="2024-12-31")

    assert len(docs) == 1
    assert docs[0].title == "VALIDO"


def test_scrap_stops_early_when_stop_event_is_already_set():
    import threading

    stop_event = threading.Event()
    stop_event.set()

    scraper = ScrapJEP()
    docs = scraper.scrap(fini="2024-01-01", ffin="2024-12-31", stop_event=stop_event)

    assert docs == []


@responses.activate
def test_scrap_requests_each_year_in_a_multi_year_range():
    responses.add(
        responses.POST, _URL,
        json=_response([_hit(1, radicado_documento="DE-2025", fecha_documento="2025-12-20")]),
        match=[_body_matcher("2025")],
        status=200,
    )
    responses.add(
        responses.POST, _URL,
        json=_response([_hit(2, radicado_documento="DE-2026", fecha_documento="2026-01-10")]),
        match=[_body_matcher("2026")],
        status=200,
    )

    scraper = ScrapJEP()
    docs = scraper.scrap(fini="2025-12-15", ffin="2026-01-15")

    assert {doc.title for doc in docs} == {"DE-2025", "DE-2026"}


def test_jep_is_registered_under_its_family_key():
    import core.scrapers.families  # noqa: F401

    assert FAMILY_REGISTRY["jep"] is ScrapJEP
```

- [ ] **Step 2: Confirmar que fallan**

Run: `.venv\Scripts\pytest tests/families/test_jep.py -v`
Expected: FAIL — el módulo todavía importa `_extraer_tipo` (que se está reemplazando) y las URLs mockeadas (`searchadv`, POST) no coinciden con lo que la implementación actual golpea (`listarProvidecias`, GET), así que las llamadas mockeadas de `responses` no se activan y varias aserciones de campos no van a coincidir con el mapeo viejo.

- [ ] **Step 3: Reescribir la implementación**

Reemplazar el contenido completo de `core/scrapers/families/jep.py` por:

```python
import re
from typing import List

import requests

from core.models import RawDocModel
from core.scrapers.base import BaseScrapper
from core.scrapers.registry import register_family
from core.utils import storage_path

_JEP_SEARCHADV_URL = "https://relatoria.jep.gov.co/searchadv"
_JEP_BASE_URL = "https://relatoria.jep.gov.co/"

_INVALID_PATH_CHARS = re.compile(r'[\\/*?:"<>|]')

_PER_PAGE = 200


def _years_in_range(fini: str, ffin: str) -> list[int]:
    return list(range(int(fini[:4]), int(ffin[:4]) + 1))


@register_family("jep")
class ScrapJEP(BaseScrapper):
    def __init__(self):
        self.source = "JEP"

    def scrap(self, fini, ffin, q="", limit=10000, stop_event=None, on_progress=None) -> List[RawDocModel]:
        docs: List[RawDocModel] = []
        vistos = set()  # providencia_id ya procesados en esta corrida (JEP puede repetir el mismo documento)

        for anio in _years_in_range(fini, ffin):
            if stop_event is not None and stop_event.is_set():
                break

            page = 1
            while True:
                if stop_event is not None and stop_event.is_set():
                    break

                response = requests.post(
                    _JEP_SEARCHADV_URL,
                    json={
                        "alguna_palabra": "",
                        "todas_palabras": "",
                        "frase_exacta": "",
                        "ninguna_palabra": "",
                        "anio": str(anio),
                        "sala_seccion": "",
                        "tipo_documento": "",
                        "page": page,
                        "per_page": _PER_PAGE,
                    },
                )

                if response.status_code != 200:
                    raise Exception(
                        f"Error al obtener datos de {self.source}: {response.status_code} - {response.text}"
                    )

                try:
                    data = response.json()
                except ValueError:
                    raise Exception(
                        f"La respuesta no es JSON válido. Contenido recibido:\n{response.text[:500]}"
                    )

                reponse = data.get("reponse")
                if reponse is None:
                    break

                hits = reponse.get("hits", {}).get("hits", [])
                total = reponse.get("hits", {}).get("total", {}).get("value", 0)

                for hit in hits:
                    raw = hit["_source"]

                    providencia_id = raw.get("providencia_id")
                    if providencia_id in vistos:
                        continue
                    vistos.add(providencia_id)

                    fecha_documento = raw.get("fecha_documento")
                    if not fecha_documento:
                        continue  # sin fecha no se puede saber si cae dentro del rango pedido

                    if fecha_documento < fini or fecha_documento > ffin:
                        continue  # filtrado preciso: el servidor solo filtra por año

                    fecha_publicacion = raw.get("fecha_publicacion")
                    f_public = fecha_publicacion[:10] if fecha_publicacion else fecha_documento

                    radicado = raw.get("radicado_documento") or ""
                    tipo = raw.get("tipo_documento") or ""
                    seccion = raw.get("sala_seccion") or ""

                    hipervinculo = (raw.get("hipervinculo") or "").lstrip("/")
                    link = f"{_JEP_BASE_URL}{hipervinculo}"

                    safe_radicado = _INVALID_PATH_CHARS.sub("-", radicado)
                    path = storage_path(
                        self.source, f_public, tipo, f"{safe_radicado}-{providencia_id}(extension)"
                    )

                    docs.append(
                        RawDocModel(
                            source=self.source,
                            link={"url": link, "method": "GET"},
                            title=radicado,
                            tipo=tipo,
                            seccion=seccion,
                            seccion_en_carpeta=False,
                            f_public=f_public,
                            f_providencia=fecha_documento,
                            save_path=path,
                        )
                    )

                if len(hits) < _PER_PAGE or page * _PER_PAGE >= total:
                    break
                page += 1

        return docs
```

- [ ] **Step 4: Confirmar que los tests pasan**

Run: `.venv\Scripts\pytest tests/families/test_jep.py -v`
Expected: 10 passed.

- [ ] **Step 5: Correr toda la suite de backend**

Run: `.venv\Scripts\pytest -v`
Expected: todo PASS salvo la falla preexistente no relacionada de `test_migrations.py`.

- [ ] **Step 6: Commit**

```bash
git add core/scrapers/families/jep.py tests/families/test_jep.py
git commit -m "feat: rewrite JEP scraper to use searchadv (exact dates, structured tipo)"
```
