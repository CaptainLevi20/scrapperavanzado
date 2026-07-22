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
        self.source = "Comisión Nacional de Disciplina Judicial"

    def scrap(self, fini, ffin, q="", limit=10000, stop_event=None, on_progress=None) -> List[RawDocModel]:
        docs: List[RawDocModel] = []
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
            if stop_event is not None and stop_event.is_set():
                return docs
            if on_progress:
                on_progress(f"[{self.source}] Consultando magistrado {mag}...")

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

        for numero_unico, (magistrado, decision_text, numero_ficha) in all_rows.items():
            if stop_event is not None and stop_event.is_set():
                return docs

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

            if on_progress:
                on_progress(f"[{self.source}] Consultando detalle de {numero_unico}...")

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
                title=safe_num,
                tipo="Magistrado",
                magistrado=magistrado_fmt,
                f_public=f_public,
                f_providencia=fecha_decision,
                save_path=path,
            ))

        return docs
