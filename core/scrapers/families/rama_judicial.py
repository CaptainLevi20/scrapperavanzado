import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List

import requests
from bs4 import BeautifulSoup

from core.downloader import check_remote_content_length
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


def _get_with_retries(session, url, headers, params=None, timeout=60, retries=3):
    """GET with up to `retries` attempts, retrying on timeout or a 5xx status.

    Mirrors the original per-call retry loops in this module: on the final
    attempt a Timeout propagates to the caller; a persistent 5xx does not
    raise here; it's left to the caller's own `raise_for_status()`/try-except.
    """
    resp = None
    for attempt in range(retries):
        try:
            resp = session.get(url, headers=headers, params=params, timeout=timeout)
            if resp.status_code < 500:
                break
        except requests.exceptions.Timeout:
            if attempt == retries - 1:
                raise
    return resp


@register_family("rama_judicial")
class ScrapRamaJudicial(BaseScrapper):
    # f_public aquí es la fecha de la fila de listado ("estado"), no una fecha
    # intrínseca del documento — el sitio repite la misma fila (mismo archivo)
    # bajo una fecha nueva cuando la notificación no fue reclamada. Si doc_id
    # incluyera f_public, el mismo archivo generaría un doc_id distinto cada
    # vez que se re-lista, escondiendo la republicación para siempre del
    # chequeo de tamaño/versionado en worker/tasks.py.
    doc_id_uses_publication_date = False

    def __init__(self, dept_code: str = "", dept_name: str = "Rama Judicial", entidad_id: str = "22"):
        self.source = dept_name
        self.url = _TRIBUNALES_SUPERIORES_URL
        self._dept_code = dept_code
        self._entidad_id = entidad_id
        self._instance_id = None

    def _get_instance_id(self, session, headers):
        resp = _get_with_retries(session, self.url, headers)
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
        try:
            resp = _get_with_retries(s, detail_url, headers)
        except requests.exceptions.Timeout:
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
        # Un mismo archivo puede reaparecer bajo una fila de listado distinta
        # (fecha distinta) cuando el sitio republica un "estado" no reclamado
        # al día siguiente. doc_id_uses_publication_date=False hace que el
        # identificador persistido (doc_id) dependa solo del uuid del archivo,
        # no de esta fecha de listado que puede repetirse — así el mecanismo
        # de detección de republicación (worker/tasks.py, igual que Corte
        # Constitucional) sí lo detecta entre corridas distintas. Dentro de
        # esta misma corrida, sin embargo, nunca se puede emitir dos
        # RawDocModel con el mismo doc_id (violaría la restricción única de
        # la tabla al insertar), así que se deduplica aquí por uuid,
        # confirmando con un HEAD real que de verdad es el mismo archivo en
        # vez de asumirlo solo por coincidencia de uuid.
        tamanos_por_uuid: dict[str, int | None] = {}
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

            response = _get_with_retries(session, self.url, headers, params=params)
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
                    fecha_p_raw = fecha_p_tag.text.split(":")[-1].strip()
                    # El pipeline de este backend (worker/tasks.py:_parse_date) exige
                    # "YYYY-MM-DD" estricto. El sitio ya publica ese formato hoy (ej.
                    # "2026-07-14", confirmado en vivo), pero se tolera también
                    # "DD/MM/YYYY" por si el formato varía o revierte.
                    if "/" in fecha_p_raw:
                        dia, mes, anio = fecha_p_raw.split("/")
                        fecha_p = f"{anio}-{mes}-{dia}"
                    else:
                        fecha_p = fecha_p_raw

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
                    # Los "_dir" son solo para el segmento de carpeta (límite de ruta);
                    # especialidad_raw/despacho_raw (sin acortar) son los que se guardan
                    # como metadato real en especialidad/seccion — acortarlos ahí perdía
                    # información a mitad de palabra (ej. "...DEL TRIBUNAL" -> "...DEL TRIB").
                    especialidad_dir = _INVALID_PATH_CHARS.sub("-", especialidad_raw)[:60]
                    despacho_dir = _INVALID_PATH_CHARS.sub("-", despacho_raw)[:60]
                    tipo_dir = _INVALID_PATH_CHARS.sub("-", tipo)

                    detail_url = a_tag.get("href", "")
                    if not detail_url:
                        continue

                    pending.append(
                        (fecha_p, tipo, tipo_dir, especialidad_dir, despacho_dir, especialidad_raw, despacho_raw, detail_url)
                    )
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
                    fecha_p, tipo, tipo_dir, especialidad_dir, despacho_dir, especialidad_raw, despacho_raw, _ = (
                        future_to_meta[future]
                    )
                    try:
                        archivos = future.result()
                    except Exception:
                        continue

                    for filename, download_url, file_uuid in archivos:
                        if file_uuid in tamanos_por_uuid:
                            tamano_anterior = tamanos_por_uuid[file_uuid]
                            tamano_actual = check_remote_content_length(download_url)
                            if (
                                tamano_anterior is not None
                                and tamano_actual is not None
                                and tamano_actual != tamano_anterior
                            ):
                                print(
                                    f"Advertencia: {file_uuid} cambió de tamaño entre listados "
                                    f"({tamano_anterior} -> {tamano_actual} bytes); se conserva la primera aparición."
                                )
                            continue
                        tamanos_por_uuid[file_uuid] = check_remote_content_length(download_url)

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
                            especialidad=especialidad_raw,
                            seccion=despacho_raw,
                            f_public=fecha_p,
                            save_path=save_path,
                        ))

            if num_pag >= max_pages:
                break
            num_pag += 1

        return docs
