import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import List, Optional

import requests
from bs4 import BeautifulSoup

from core.models import RawDocModel
from core.scrapers.base import BaseScrapper
from core.scrapers.registry import register_family
from core.utils import storage_path

_URL = "https://samai.consejodeestado.gov.co/vistas/utiles/WEstados.aspx"

# Public: enumerated by core/seed.py to create one Source per tribunal.
SAMAI_CORPS = {
    "1100103": "Consejo de Estado",
    "0500123": "Tribunal Administrativo de Antioquia",
    "8100123": "Tribunal Administrativo de Arauca",
    "0800123": "Tribunal Administrativo del Atlántico",
    "1300123": "Tribunal Administrativo de Bolívar",
    "1500123": "Tribunal Administrativo de Boyacá",
    "1700123": "Tribunal Administrativo de Caldas",
    "1800123": "Tribunal Administrativo del Caquetá",
    "8500123": "Tribunal Administrativo del Casanare",
    "1900123": "Tribunal Administrativo del Cauca",
    "2000123": "Tribunal Administrativo del Cesar",
    "2700123": "Tribunal Administrativo del Chocó",
    "2300123": "Tribunal Administrativo de Córdoba",
    "2500023": "Tribunal Administrativo de Cundinamarca",
    "4100123": "Tribunal Administrativo del Huila",
    "4400123": "Tribunal Administrativo de la Guajira",
    "4700123": "Tribunal Administrativo del Magdalena",
    "5000123": "Tribunal Administrativo del Meta",
    "5200123": "Tribunal Administrativo de Nariño",
    "5400123": "Tribunal Administrativo de Norte de Santander",
    "8600123": "Tribunal Administrativo del Putumayo",
    "6300123": "Tribunal Administrativo del Quindío",
    "6600123": "Tribunal Administrativo de Risaralda",
    "8800123": "Tribunal Administrativo de San Andrés",
    "6800123": "Tribunal Administrativo de Santander",
    "7000123": "Tribunal Administrativo de Sucre",
    "7300123": "Tribunal Administrativo del Tolima",
    "7600123": "Tribunal Administrativo del Valle del Cauca",
}

_INVALID_PATH = re.compile(r'[\\/*?:"<>|]')


def _safe(text, maxlen=60):
    return _INVALID_PATH.sub("-", text)[:maxlen]


def _parse_estado_date(val: str):
    return datetime.strptime(val.split(" ")[0], "%d/%m/%Y")


def _parse_prov_date(val: str):
    try:
        return datetime.strptime(val.strip(), "%d/%m/%Y").strftime("%Y-%m-%d")
    except Exception:
        return None


def _all_inputs(soup) -> dict:
    out = {}
    for inp in soup.find_all("input"):
        name = inp.get("name")
        if name:
            out[name] = inp.get("value", "")
    return out


@register_family("samai")
class ScrapTribunales(BaseScrapper):
    source = "Tribunales Administrativos"
    # SAMAI's download goes through an indirect JWT hop, not a direct file URL —
    # there's nothing cheap to HEAD, so republication checking is out of scope for
    # this family (see tests/families/test_samai.py).
    checks_for_republication = False

    def __init__(self, corp_code: str, corp_name: str):
        self._corp_code = corp_code
        self._corp_name = corp_name
        self.source = corp_name

    def scrap(self, fini, ffin, q="", limit=1000, stop_event=None, on_progress=None) -> List[RawDocModel]:
        fini_dt = datetime.strptime(fini, "%Y-%m-%d")
        ffin_dt = datetime.strptime(ffin, "%Y-%m-%d")
        if on_progress:
            on_progress(f"[SAMAI] Procesando {self._corp_name}…")
        try:
            return self._scrap_corp(self._corp_code, self._corp_name, fini_dt, ffin_dt, stop_event, on_progress)
        except Exception as e:
            if on_progress:
                on_progress(f"[SAMAI] Error en {self._corp_name}: {e}")
            return []

    def _new_session(self):
        s = requests.Session()
        s.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
        return s

    @staticmethod
    def _fetch(fn, *args, **kwargs):
        for attempt in range(2):
            try:
                res = fn(*args, **kwargs)
                res.raise_for_status()
                return res
            except requests.exceptions.Timeout:
                if attempt == 0:
                    time.sleep(5)
                    continue
                raise

    def _step1_get(self, session):
        res = self._fetch(session.get, _URL, timeout=30)
        return BeautifulSoup(res.text, "html.parser")

    def _step2_select_corp(self, session, soup1, corp_code):
        data = {
            **_all_inputs(soup1),
            "ctl00$MainContent$LstCorpHabilitada": corp_code,
            "ctl00$MainContent$ImgBuscar2.x": "10",
            "ctl00$MainContent$ImgBuscar2.y": "10",
        }
        res = self._fetch(session.post, _URL, data=data, timeout=30)
        return BeautifulSoup(res.text, "html.parser")

    def _step3_select_section(self, session, soup2, corp_code, sec_code):
        data = {
            **_all_inputs(soup2),
            "ctl00$MainContent$LstCorpHabilitada": corp_code,
            "ctl00$MainContent$LstCoorporacion": sec_code,
            "ctl00$MainContent$ImgBuscar3.x": "10",
            "ctl00$MainContent$ImgBuscar3.y": "10",
        }
        res = self._fetch(session.post, _URL, data=data, timeout=30)
        return BeautifulSoup(res.text, "html.parser")

    def _step4a_check_all(self, session, soup3, corp_code, sec_code, fecha_val):
        data = {
            **_all_inputs(soup3),
            "ctl00$MainContent$LstCorpHabilitada": corp_code,
            "ctl00$MainContent$LstCoorporacion": sec_code,
            "ctl00$MainContent$LstUEstados": fecha_val,
            "ctl00$MainContent$ChkSeccion": "on",
            "__EVENTTARGET": "ctl00$MainContent$ChkSeccion",
            "__EVENTARGUMENT": "",
        }
        data.pop("ctl00$MainContent$ImgBuscar2", None)
        data.pop("ctl00$MainContent$ImgBuscar3", None)
        data.pop("ctl00$MainContent$CmdBuscar", None)
        res = self._fetch(session.post, _URL, data=data, timeout=30)
        return BeautifulSoup(res.text, "html.parser")

    def _step4b_consultar(self, session, soup_chk, corp_code, sec_code, fecha_val):
        data = {
            **_all_inputs(soup_chk),
            "ctl00$MainContent$LstCorpHabilitada": corp_code,
            "ctl00$MainContent$LstCoorporacion": sec_code,
            "ctl00$MainContent$LstUEstados": fecha_val,
            "ctl00$MainContent$ChkSeccion": "on",
            "ctl00$MainContent$LstCriterio": "Na",
            "ctl00$MainContent$Txtcriterio": "",
            "ctl00$MainContent$CmdBuscar": "Consultar",
        }
        data.pop("ctl00$MainContent$ImgBuscar2", None)
        data.pop("ctl00$MainContent$ImgBuscar3", None)
        return self._fetch(session.post, _URL, data=data, timeout=120).text

    def _scrap_corp(self, corp_code, corp_name, fini_dt, ffin_dt, stop_event, on_progress):
        session = self._new_session()
        soup1 = self._step1_get(session)
        soup2 = self._step2_select_corp(session, soup1, corp_code)

        sel_sec = soup2.find("select", {"id": "MainContent_LstCoorporacion"})
        if not sel_sec:
            return []

        secciones = [(o.get("value", ""), o.text.strip()) for o in sel_sec.find_all("option") if o.get("value")]

        def _process_section(sec_code, sec_name):
            try:
                s = self._new_session()
                s1 = self._step1_get(s)
                s2 = self._step2_select_corp(s, s1, corp_code)
                s3 = self._step3_select_section(s, s2, corp_code, sec_code)
                return self._scrap_section(
                    s, s3, corp_code, corp_name, sec_code, sec_name, fini_dt, ffin_dt, stop_event, on_progress
                )
            except Exception as e:
                if on_progress:
                    on_progress(f"[{corp_name}] Error en {sec_name}: {e}")
                return []

        docs = []
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = {
                executor.submit(_process_section, sec_code, sec_name): sec_name for sec_code, sec_name in secciones
            }
            for future in as_completed(futures):
                if stop_event and stop_event.is_set():
                    break
                try:
                    docs.extend(future.result())
                except Exception:
                    pass

        return docs

    def _scrap_section(
        self, session, soup3, corp_code, corp_name, sec_code, sec_name, fini_dt, ffin_dt, stop_event, on_progress
    ):
        sel_fechas = soup3.find("select", {"id": "MainContent_LstUEstados"})
        if not sel_fechas:
            return []

        fechas_en_rango = []
        for opt in sel_fechas.find_all("option"):
            val = opt.get("value", "")
            if not val:
                continue
            try:
                dt = _parse_estado_date(val)
                if fini_dt <= dt <= ffin_dt:
                    fechas_en_rango.append((val, dt))
            except Exception:
                continue

        if not fechas_en_rango:
            return []

        docs = []
        for fecha_val, fecha_dt in fechas_en_rango:
            if stop_event and stop_event.is_set():
                break
            try:
                soup_chk = self._step4a_check_all(session, soup3, corp_code, sec_code, fecha_val)
                html = self._step4b_consultar(session, soup_chk, corp_code, sec_code, fecha_val)

                if "No hay resultados" in html:
                    continue

                soup4 = BeautifulSoup(html, "html.parser")
                gv = soup4.find("table", {"id": "MainContent_GvProvidencias"})
                if not gv:
                    continue

                estado_fecha_str = fecha_dt.strftime("%Y-%m-%d")

                for row in gv.find_all("tr")[1:]:
                    doc = self._parse_row(row, corp_code, corp_name, sec_name, estado_fecha_str)
                    if doc:
                        docs.append(doc)
            except Exception as e:
                if on_progress:
                    on_progress(f"[SAMAI] Error fecha {fecha_val} en {sec_name}: {e}")

        return docs

    def _parse_row(self, row, corp_code, corp_name, sec_name, estado_fecha_str):
        tds = row.find_all("td")
        if len(tds) < 10:
            return None

        radicado = tds[1].get_text(strip=True)
        actuacion = tds[7].get_text(strip=True)
        fecha_prov_raw = tds[6].get_text(strip=True)
        fecha_prov = _parse_prov_date(fecha_prov_raw)

        jwt_url = self._extract_jwt_url(tds[9])
        if not jwt_url:
            return None

        palabras = actuacion.split()
        tipo = _safe(palabras[0]) if palabras else ""
        seccion = _safe(sec_name, maxlen=100)
        safe_radicado = _safe(radicado)

        path = storage_path(corp_name, seccion, estado_fecha_str, tipo, f"{safe_radicado}(extension)")

        return RawDocModel(
            source=corp_name,
            link={"url": jwt_url, "method": "jwt_indirect", "body": {"path": f"{corp_code}_{radicado}"}},
            title=radicado,
            tipo=tipo,
            detalle=actuacion,
            seccion=seccion,
            f_public=estado_fecha_str,
            f_providencia=fecha_prov,
            save_path=path,
            convert_to="rtf_word",
        )

    @staticmethod
    def _extract_jwt_url(td) -> Optional[str]:
        a = td.find("a", class_=lambda c: c and "btn-success" in c)
        if not a:
            return None
        onclick = a.get("onclick", "")
        m = re.search(r"CargarVentana\('(https?://[^']+)'\)", onclick, re.IGNORECASE)
        return m.group(1) if m else None
