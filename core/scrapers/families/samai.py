import logging
import re
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import List, Optional

import requests
from bs4 import BeautifulSoup

from core.models import RawDocModel
from core.scrapers.base import BaseScrapper
from core.scrapers.families.rama_judicial import TRIBUNAL_CODES
from core.scrapers.registry import register_family
from core.utils import storage_path

_URL = "https://samai.consejodeestado.gov.co/vistas/utiles/WEstados.aspx"

logger = logging.getLogger(__name__)

# El código de SAMAI_CORPS para Consejo de Estado — el único corp cuyo título
# sigue llevando el acrónimo de la clase entre paréntesis (ver _normalizar_titulo).
_CONSEJO_DE_ESTADO_CORP_CODE = "1100103"

# La columna "Clase" de SAMAI describe el tipo de proceso, pero el mismo proceso
# aparece escrito de formas distintas según la sección/época (con o sin el
# prefijo "LEY 1437 ...", con o sin "ACCIÓN (DE) ...", con o sin la referencia
# "ARTÍCULO ### DECISIÓN ###"/"ART. ##") — _normalizar_clase quita ese ruido
# antes de buscar el acrónimo.
_LEY_RE = re.compile(r"LEY\s+[0-9./-]+\s*", re.IGNORECASE)
_ACCION_RE = re.compile(r"^ACCION(ES)?\s+(DE\s+)?", re.IGNORECASE)
_ART_RE = re.compile(r"ART(?:ICULO|[IÍ]CULO|\.)?\s*\d+\s*(?:DECISION\s+\d+\s*)?", re.IGNORECASE)


def _normalizar_clase(raw: str) -> str:
    t = _LEY_RE.sub("", raw or "")
    t = "".join(c for c in unicodedata.normalize("NFKD", t) if not unicodedata.combining(c)).upper()
    t = _ACCION_RE.sub("", t)
    t = _ART_RE.sub("", t)
    return re.sub(r"\s+", " ", t).strip(" -.")


# Catálogo dictado directamente por el usuario a partir de un año real de datos
# de Consejo de Estado (jul. 2026: 1,070 documentos, 6 secciones — un rango más
# amplio no encontró clases adicionales porque SAMAI solo mantiene visible
# alrededor de un mes de "estados"). Varias claves distintas apuntan al mismo
# acrónimo cuando el usuario confirmó que son la misma clase de proceso escrita
# de otra forma.
_CLASE_ACRONIMOS = {
    "NULIDAD Y RESTABLECIMIENTO DEL DERECHO": "NRD",
    "NULIDAD ELECTORAL": "NE",
    "NULIDAD CON SUSPENSION PROVISIONAL": "NSP",
    "NULIDAD Y SUSPENSION PROVISIONAL": "NSP",
    "NULIDAD": "N",
    "RECURSO EXTRAORDINARIO DE REVISION": "RER",
    "REPARACION DIRECTA": "RD",
    "CONTROVERSIAS CONTRACTUALES": "CTR",
    "CONTRACTUAL": "CTR",
    "EJECUTIVO": "EJE",
    "POPULARES": "AP",
    "CUMPLIMIENTO": "ACU",
    "REPETICION": "REP",
    "EXTENSION DE JURISPRUDENCIA": "EXJ",
    "REPARACION DE PERJUICIOS CAUSADOS A UN GRUPO": "RPAG",
    "REPARACION DE LOS PERJUCIOS CAUSADOS A UN GRUPO": "RPAG",
    "CONFLICTOS DE COMPETENCIA": "CCO",
    "CONFLICTOS DE COMPETENCIA JUDICIAL": "CCO",
    "PERDIDA DE INVESTIDURA": "PI",
    "NULIDAD RELATIVA": "NR",
    "PERDIDA DE INVESTIDURA 1RA INSTANCIA": "PI1",
    "NULIDAD Y RESTABLECIMIENTO SUSP. PROV": "NRSP",
    "RECURSO EXTRAORDINARIO DE UNIFICACION DE JURISPRUDENCIA": "REU",
    "RECURSO EXTRAORDINARIO DE UNIFICACION": "REU",
    "PROTECCION DERECHOS E INTERESES COLECTIVOS": "PDIC",
    "PROTECCION DE LOS DERECHOS E INTERESES COLECTIVOS": "PDIC",
    "PERDIDA DE INVESTIDURA 2DA INSTANCIA": "PI2",
    "RECURSO DE ANULACION DE LAUDO ARBITRAL": "RALA",
    "REVISION": "REV",
    "NULIDAD INCONSTITUCIONALIDAD SUSP PROV": "NISP",
    "REVISION EVENTUAL": "REVE",
    "CONCILIACION": "CON",
    "GRUPO": "AG",
    "NULIDAD ABSOLUTA": "NA",
    "NULIDAD POR INCONSTITUCIONALIDAD": "NI",
    "INSISTENCIA PETICIONES DE INFORMACION": "IPI",
    # Vistas por primera vez examinando datos reales de Tribunales Administrativos
    # (jul. 2026: Antioquia y Bolívar, 1,351 documentos) — la clase no importa para
    # el título de un Tribunal Administrativo (ver _normalizar_titulo), pero estas
    # clases también pueden aparecer en Consejo de Estado, así que nutren este mismo
    # catálogo. Las siguientes son variantes de clases que ya existían arriba:
    "POPULAR": "AP",
    "CONFLICTO DE COMPETENCIA": "CCO",
    "CUMPLIMIENTO DE NORMAS CON FUERZA MATERIAL DE LEY (ACCION DE CUMPLIMIENTO)": "ACU",
    "PROTECCION DE LOS DERECHOS E INTERESES COLECTIVOS (ACCION POPULAR)": "PDIC",
    "RECURSO INSISTENCIA": "IPI",
    "RECURSO DE INSISTENCIA": "IPI",
    "A. DE NULIDAD CONTRA ACTOS DE CONTENIDO ELECTORAL": "NE",
    # Estas sí son clases genuinamente nuevas para el catálogo:
    "APELACION SENTENCIA": "AS",
    "TUTELA": "T",
    "EJECUTIVO CONEXO": "EC",
    "EJECUTIVO SINGULAR": "ES",
    "REVISION ACUERDOS": "RAC",
    "APELACION AUTO": "AA",
    "HABEAS CORPUS": "HC",
    "MEDIDAS CAUTELARES": "MC",
    "REVISION DECRETOS": "RDE",
    "RECURSO DE QUEJA": "RQ",
    "CONSULTA INCIDENTE DESACATO": "CID",
    "INCIDENTE DESACATO": "ID",
    # Confirmado con el usuario: "Electorales" y "Observaciones" NO son lo
    # mismo que "Nulidad Electoral" — son clases aparte, con su propia sigla.
    "ELECTORALES": "E",
    "OBSERVACIONES": "O",
}


def _normalizar_titulo(radicado: str, clase: str, corp_code: str) -> str:
    # Consejo de Estado keeps {radicado}({ACRÓNIMO}) — but Tribunales
    # Administrativos must NOT look the same (serían fácilmente confundibles
    # con providencias de Consejo de Estado). En su lugar imitan el formato
    # de los Tribunales Superiores (core/scrapers/families/rama_judicial.py::
    # _normalize_title): "T_{CÓDIGO}_{radicado segmentado con guiones bajos}".
    # El radicado de SAMAI ya llega segmentado con guiones (5-2-2-3-4-5-2
    # dígitos), así que basta con cambiar "-" por "_" para calzar exactamente
    # con la segmentación que produce rama_judicial. La clase de proceso no
    # importa para el título de un Tribunal Administrativo (solo se usa para
    # nutrir el catálogo de Consejo de Estado — ver _especialidad_legible).
    if corp_code == _CONSEJO_DE_ESTADO_CORP_CODE:
        acronimo = _CLASE_ACRONIMOS.get(_normalizar_clase(clase))
        return f"{radicado}({acronimo})" if acronimo else radicado
    codigo = TRIBUNAL_CODES.get(corp_code[:2])
    return f"T_{codigo}_{radicado.replace('-', '_')}" if codigo else radicado


# Nombre legible por acrónimo, para la columna Especialidad/Proceso — el sitio
# a veces trae la clase con el código de ley ("LEY 1437 NULIDAD...") y otras
# veces sin él ("Nulidad..."), y esta columna siempre debe mostrar la forma
# limpia sin importar cuál trajo el sitio para ese documento en particular.
_ACRONIMO_A_NOMBRE = {
    "NRD": "Nulidad y restablecimiento del derecho",
    "NE": "Nulidad electoral",
    "NSP": "Nulidad con suspensión provisional",
    "N": "Nulidad",
    "RER": "Recurso extraordinario de revisión",
    "RD": "Reparación directa",
    "CTR": "Controversias contractuales",
    "EJE": "Ejecutivo",
    "AP": "Acciones populares",
    "ACU": "Acciones de cumplimiento",
    "REP": "Repetición",
    "EXJ": "Extensión de jurisprudencia",
    "RPAG": "Reparación de perjuicios causados a un grupo",
    "CCO": "Conflictos de competencia",
    "PI": "Pérdida de investidura",
    "NR": "Nulidad relativa",
    "PI1": "Pérdida de investidura 1ra instancia",
    "NRSP": "Nulidad y restablecimiento del derecho con suspensión provisional",
    "REU": "Recurso extraordinario de unificación de jurisprudencia",
    "PDIC": "Protección de los derechos e intereses colectivos",
    "PI2": "Pérdida de investidura 2da instancia",
    "RALA": "Recurso de anulación de laudo arbitral",
    "REV": "Revisión",
    "NISP": "Nulidad por inconstitucionalidad con suspensión provisional",
    "REVE": "Revisión eventual",
    "CON": "Conciliación",
    "AG": "Acción de grupo",
    "NA": "Nulidad absoluta",
    "NI": "Nulidad por inconstitucionalidad",
    "IPI": "Insistencia en peticiones de información",
    "AS": "Apelación de sentencia",
    "T": "Tutela",
    "EC": "Ejecutivo conexo",
    "ES": "Ejecutivo singular",
    "RAC": "Revisión de acuerdos",
    "AA": "Apelación de auto",
    "HC": "Habeas corpus",
    "MC": "Medidas cautelares",
    "RDE": "Revisión de decretos",
    "RQ": "Recurso de queja",
    "CID": "Consulta de incidente de desacato",
    "ID": "Incidente de desacato",
    "E": "Electorales",
    "O": "Observaciones",
}


def _especialidad_legible(clase: str) -> str:
    acronimo = _CLASE_ACRONIMOS.get(_normalizar_clase(clase))
    return _ACRONIMO_A_NOMBRE.get(acronimo, clase) if acronimo else clase

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


# Un título de Consejo de Estado es siempre "{radicado}" o
# "{radicado}({SIGLA})" (ver _normalizar_titulo) — nunca el formato
# "T_{CÓDIGO}_..." de un Tribunal Administrativo, así que este patrón sirve
# tanto para separar el radicado como para confirmar que el título es
# realmente de Consejo de Estado antes de tocarlo.
_TITULO_CE_RE = re.compile(r"^([\d-]+)(\([A-Z0-9]+\))?$")

# Un título ya complementado trae el número justo después del radicado —
# "{radicado}({número})..." (ver _complementar_titulo_con_numero). El grupo
# del número siempre empieza con un dígito (a diferencia de la sigla de
# clase, que _CLASE_ACRONIMOS garantiza que siempre empieza con una letra
# mayúscula), así que basta con mirar el primer carácter para distinguir "ya
# tiene el número" de "todavía no, esto es la sigla" — sin asumir que el
# número es solo dígitos (ver _numero_extra_desde_texto: también aparece como
# "3104-2023" o "74.604" en datos reales). Misma forma que valida
# _YA_COMPLEMENTADO_RE en core/backfill_ce_titles.py, pero definida aquí
# también para que _complementar_titulo_con_numero sea segura de llamar más
# de una vez por sí misma — el guard del backfill es, con esto, solo una
# optimización para no volver a descargar un PDF ya procesado, no lo único que
# evita duplicar el número.
_YA_COMPLEMENTADO_RE = re.compile(r"^[\d-]+\(\d[^)]*\)")


def _extraer_texto_primera_pagina(local_path) -> str:
    # A diferencia de CSJ (core/scrapers/families/corte_suprema.py), SAMAI
    # solo entrega PDF a través de su hop jwt_indirect — no hace falta
    # distinguir por content_type ni soportar .docx.
    from pypdf import PdfReader

    reader = PdfReader(str(local_path))
    if not reader.pages:
        return ""
    return reader.pages[0].extract_text() or ""


def _numero_extra_desde_texto(texto: str, radicado: str) -> Optional[str]:
    # El número entre paréntesis no siempre son solo dígitos — datos reales
    # confirmaron también "3104-2023" (número-año) y "74.604" (con punto de
    # miles). Se acepta el contenido tal cual venga, mientras tenga al menos
    # un dígito. Cuando no hay ningún dígito (ej. "(principal)", que indica
    # cuaderno principal, no un número de caso) se descarta — no es el dato
    # que buscamos.
    #
    # El radicado dentro del PDF tampoco siempre usa guion como separador
    # entre segmentos — a veces aparece con espacios ("11001 03 25 000 2025
    # 00135 00"), mismos dígitos exactos, solo cambia el separador (a
    # diferencia de un typo real, donde los dígitos sí difieren y no se debe
    # adivinar). Se busca segmento por segmento, aceptando guion o espacio
    # entre cada uno.
    segmentos = radicado.split("-")
    patron_radicado = r"[\s-]".join(re.escape(s) for s in segmentos)
    match = re.search(patron_radicado + r"\s*\(([^)]{1,30})\)", texto or "")
    if not match:
        return None
    contenido = match.group(1).strip()
    return contenido if any(c.isdigit() for c in contenido) else None


def _complementar_titulo_con_numero(titulo: str, numero: str) -> str:
    if _YA_COMPLEMENTADO_RE.match(titulo):
        return titulo
    match = _TITULO_CE_RE.match(titulo)
    if not match:
        return titulo
    radicado, sufijo_acronimo = match.group(1), match.group(2) or ""
    return f"{radicado}({numero}){sufijo_acronimo}"


@register_family("samai")
class ScrapTribunales(BaseScrapper):
    source = "Tribunales Administrativos"
    # SAMAI repeats the same "estado" row under a new date when the notification
    # wasn't claimed — same reasoning as Rama Judicial (core/scrapers/families/
    # rama_judicial.py): f_public is the date of that listing, not a property of
    # the document itself, so it must not be part of doc_id or the same file
    # gets a brand-new identity (and a duplicate row) every time it's relisted.
    doc_id_uses_publication_date = False
    # SAMAI's download goes through an indirect JWT hop, not a direct file URL,
    # so the cheap HEAD in check_remote_content_length can't see the real file
    # size (it only sees the intermediate viewer page) — every relisting is
    # treated as a republication candidate and actually re-downloaded, but
    # _download_and_upload_one's skip_upload_if_size_matches still discards it
    # without creating a new version when the real downloaded size is unchanged.
    checks_for_republication = True

    def __init__(self, corp_code: str, corp_name: str):
        self._corp_code = corp_code
        self._corp_name = corp_name
        self.source = corp_name

    def resolve_unverified_document(self, doc, local_path, content_type) -> None:
        # Se dispara solo para Consejo de Estado (ver title_unverified en
        # _parse_row) — este chequeo extra es defensivo: si algún día algo
        # más marca title_unverified=True, un título de Tribunal
        # Administrativo simplemente no matchea _TITULO_CE_RE y se ignora.
        match = _TITULO_CE_RE.match(doc.title)
        if not match:
            return
        radicado = match.group(1)

        try:
            texto = _extraer_texto_primera_pagina(local_path)
        except Exception as e:
            logger.warning(
                "No se pudo leer la primera página de %s para complementar el título: %s",
                local_path.name, e,
            )
            return

        numero = _numero_extra_desde_texto(texto, radicado)
        if not numero:
            return

        doc.title = _complementar_titulo_con_numero(doc.title, numero)

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
        clase = tds[5].get_text(strip=True)
        actuacion = tds[7].get_text(strip=True)
        fecha_prov_raw = tds[6].get_text(strip=True)
        fecha_prov = _parse_prov_date(fecha_prov_raw)

        jwt_url = self._extract_jwt_url(tds[9])
        if not jwt_url:
            return None

        palabras = actuacion.split()
        tipo = _safe(palabras[0]) if palabras else ""
        seccion = _safe(sec_name, maxlen=100)
        titulo = _normalizar_titulo(radicado, clase, corp_code)
        safe_radicado = _safe(radicado)

        path = storage_path(corp_name, seccion, estado_fecha_str, tipo, f"{safe_radicado}(extension)")

        # radicado alone identifies the *case*, not a specific document — a case
        # accumulates many distinct actuaciones (different Autos on different
        # dates) that all share it, exactly like Rama Judicial. Folding every
        # relisting of a radicado into one document (see git history — the
        # first attempt at this) silently buried genuinely different
        # actuaciones as unreviewable "versions" of whichever was seen first.
        # f_providencia (the real decision date) is what's actually stable
        # across a true republication (same decision, relisted because the
        # notification wasn't claimed) and different across distinct
        # actuaciones on the same case, so it — not estado_fecha_str, which is
        # just the listing date — belongs in the identity key.
        identidad_fecha = fecha_prov or fecha_prov_raw
        return RawDocModel(
            source=corp_name,
            link={
                "url": jwt_url,
                "method": "jwt_indirect",
                "body": {"path": f"{corp_code}_{radicado}_{identidad_fecha}"},
            },
            title=titulo,
            tipo=tipo,
            detalle=actuacion,
            seccion=seccion,
            especialidad=_especialidad_legible(clase),
            f_public=estado_fecha_str,
            f_providencia=fecha_prov,
            save_path=path,
            # Solo Consejo de Estado: algunos de sus documentos traen, en la
            # primera página del PDF, un número entre paréntesis junto al
            # radicado que no aparece en esta tabla — resolve_unverified_document
            # lo busca una vez descargado el archivo y complementa el título.
            title_unverified=(corp_code == _CONSEJO_DE_ESTADO_CORP_CODE),
        )

    @staticmethod
    def _extract_jwt_url(td) -> Optional[str]:
        a = td.find("a", class_=lambda c: c and "btn-success" in c)
        if not a:
            return None
        onclick = a.get("onclick", "")
        m = re.search(r"CargarVentana\('(https?://[^']+)'\)", onclick, re.IGNORECASE)
        return m.group(1) if m else None
