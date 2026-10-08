import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Optional

import requests
from bs4 import BeautifulSoup

from core.downloader import check_remote_content_length
from core.fecha_es import parse_fecha_providencia_es
from core.models import RawDocModel
from core.scrapers.base import BaseScrapper
from core.scrapers.registry import register_family
from core.utils import is_radicado_title, storage_path

logger = logging.getLogger(__name__)

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

# Código de 3-4 letras por tribunal, usado por _normalize_title para el
# prefijo "T_{CODIGO}_" del título normalizado. Dictado directamente por el
# usuario para cada uno de los 33 tribunales — no se deriva automáticamente
# del nombre.
TRIBUNAL_CODES = {
    "05": "ANTI",
    "08": "ATLA",
    "11": "BTA",
    "13": "BOLI",
    "15": "BOYA",
    "17": "CALD",
    "18": "CAQU",
    "19": "CAUC",
    "20": "CESA",
    "23": "CORD",
    "25": "CUND",
    "27": "CHOC",
    "41": "HUIL",
    "44": "GUAJ",
    "47": "MAGD",
    "50": "META",
    "52": "NARI",
    "54": "NSAN",
    "63": "QUIN",
    "66": "RISA",
    "68": "SANT",
    "70": "SUCR",
    "73": "TOLI",
    "76": "VALL",
    "81": "ARAU",
    "85": "CASA",
    "86": "PUTU",
    "88": "SAND",
    "91": "AMAZ",
    "94": "GUAI",
    "95": "GUAV",
    "97": "VAUP",
    "99": "VICH",
}

_RADICADO_PREFIX = re.compile(r"^(?:\d{2}-\d{2}-\d{4}\s+)?(\d{23})(?:[ _]|$)")

# El radicado (23 dígitos: 5 municipio + 2 entidad + 2 especialidad + 3
# despacho + 4 año + 5 consecutivo + 2 instancia) puede venir en cualquier
# parte del nombre o del texto, pegado a palabras, o con un separador entre sus
# partes ("41001-31-05-002-2021-00031-01", "11001 31 10 013 2023 00782 01").
# Medido en producción (octubre 2026): ~24% de los documentos de Tribunales
# Superiores que quedaban sin formato traían el radicado así.
_SEP = r"[\s\-_.]?"
_RADICADO_POR_PARTES = re.compile(
    rf"(?<!\d)(\d{{5}}){_SEP}(\d{{2}}){_SEP}(\d{{2}}){_SEP}(\d{{3}}){_SEP}(\d{{4}}){_SEP}(\d{{5}}){_SEP}(\d{{2}})(?!\d)"
)
# Cualquier tira de dígitos con separadores sueltos que sume exactamente 23
# dígitos — cubre agrupaciones distintas a la oficial, como
# "73-319-31-03-001-2022-00078-01" o "76 001 31 10 006 2024 00406 00".
_TIRA_DE_DIGITOS = re.compile(r"(?<!\d)\d(?:[\s\-_.]?\d)+(?!\d)")
# Listas de notificaciones del día (varios procesos en un mismo archivo): no
# corresponden a un solo radicado, se dejan con el nombre que trae la fuente.
# Ver _es_lista_de_estados: "estado" también aparece en providencias
# ("…Vs SEGUROS DEL ESTADO").
_LISTA_DE_ESTADOS = re.compile(r"estados?|edictos?", re.IGNORECASE)
# Listas que no dicen "estado": la tabla del día que algunos tribunales nombran
# por la sala y la fecha ("tribunal superior sala laboral_11-09-2026",
# "tribunal superior de sincelejo - sala civil familia laboral_10-09-2026") y
# las de Córdoba ("SIUGJ1").
_LISTA_SIN_LA_PALABRA = re.compile(r"^\s*_?tribunal superior\b.*\d{2}-\d{2}-\d{4}\s*$|^\s*siugj\s*\d*\s*$", re.IGNORECASE)

# Lo que sigue lo midió un diagnóstico de los 4.311 documentos de Tribunales
# Superiores que seguían sin formato en producción (octubre 2026): los
# despachos escriben el radicado de muchas formas que la regla estricta de
# arriba no reconoce.
#
# Guiones tipográficos que los PDF traen en lugar de "-" ("2024 – 00108 – 01").
_GUIONES = re.compile(r"[‐-―−﹘﹣－]")
# Tira de dígitos con separadores más sueltos: guion, punto, guion bajo o barra
# con espacios alrededor ("68001-31-05-004 - 2024 - 00108 - 01",
# "230012214-000-2026-10167/00"), o hasta dos espacios. No cruza saltos de línea.
_TIRA_TOLERANTE = re.compile(r"(?<!\d)\d(?:(?:[ \t]{0,2}[\-_./][ \t]{0,2}|[ \t]{1,2})?\d)*(?!\d)")
# Número corto en el nombre: año + consecutivo (3 a 6 dígitos) + instancia
# opcional — "2024-00214-01", "2019.00217.01", "(2023-0143)", "2026-00485",
# "20230002401". Sin separador entre año y consecutivo se exige el consecutivo
# de 5 dígitos, para no confundir fechas ("20261002") con radicados.
_NUMERO_CORTO = re.compile(r"(?<!\d)((?:19|20)\d{2})([\s\-_./]{0,3})(\d{3,6})(?:[\s\-_./]{1,3}(\d{2}))?(?!\d)")
# Palabra que anuncia el radicado del propio documento justo antes del número
# ("Radicación:", "Rad.", "RADICADO", "Expediente N°", "Proceso No.", "NUR").
_ETIQUETA_RADICADO = re.compile(
    r"(?i)(rad(?:icado|icaci[oó]n)?|proceso|expediente|ref(?:erencia)?|nur|n[uú]mero)\b[^\n\d]{0,25}$"
)


def _claves_cortas(nombre: str) -> list[tuple[str, str, Optional[str]]]:
    """(año, consecutivo de 5 dígitos, instancia o None) de cada número corto
    del nombre, en orden. Boyacá, por ejemplo, pone dos: el número interno del
    tribunal y el del proceso ("05 (2026-0688) (2023-0143)")."""
    claves = []
    for m in _NUMERO_CORTO.finditer(_GUIONES.sub("-", nombre or "")):
        anio, separador, consecutivo, instancia = m.groups()
        if not separador and len(consecutivo) != 5:
            continue
        if len(consecutivo) == 6:
            if consecutivo[0] != "0":
                continue
            consecutivo = consecutivo[1:]
        claves.append((anio, consecutivo.zfill(5), instancia))
    return claves


def _es_lista_de_estados(nombre: str) -> bool:
    """Lista de Estados/Edictos del día: dice "estado" o "edicto" y no trae
    ningún número de proceso. "2023-00249-01 …SegurosDelEstado" es una
    providencia, no una lista."""
    nombre = nombre or ""
    if _LISTA_SIN_LA_PALABRA.search(nombre):
        return True
    return bool(_LISTA_DE_ESTADOS.search(nombre)) and not _claves_cortas(nombre) and not _radicados_en(nombre)


def _interpretar_tira(tira: str) -> Optional[tuple[str, Optional[str]]]:
    """(proceso de 21 dígitos, instancia o None) de una tira de dígitos con
    separadores, o None si no es un radicado. Acepta, además de los 23 dígitos
    exactos, el consecutivo con 3-4 dígitos o con un cero de más
    ("…-2024-0321-01", "…-2024-000116-01") y el radicado sin instancia (21
    dígitos, "41551-31-84-002-2026-00031"). El proceso son los 12 dígitos de
    municipio/entidad/especialidad/despacho + año + consecutivo."""
    grupos = [g for g in re.split(r"\D+", tira) if g]
    digitos = "".join(grupos)

    def _valido(prefijo: str, anio: str) -> bool:
        return len(prefijo) == 12 and prefijo[:2] in TRIBUNAL_CODES and re.fullmatch(r"(?:19|20)\d\d", anio) is not None

    if len(digitos) in (21, 23) and _valido(digitos[:12], digitos[12:16]):
        if len(digitos) == 23 or len(grupos) == 1 or len(grupos[-1]) != 2:
            return digitos[:21], (digitos[21:] or None)

    # Por grupos: los 12 primeros dígitos, luego el año, el consecutivo y la
    # instancia en grupos separados.
    acumulado = ""
    for k, grupo in enumerate(grupos):
        if len(acumulado) == 12 and _valido(acumulado, grupo) and len(grupo) == 4:
            resto = grupos[k + 1:]
            if not resto:
                return None
            consecutivo = resto[0]
            if len(consecutivo) > 5:
                if consecutivo[: len(consecutivo) - 5].strip("0"):
                    return None
                consecutivo = consecutivo[-5:]
            if len(consecutivo) < 3:
                return None
            instancia = resto[1] if len(resto) > 1 and len(resto[1]) == 2 else None
            return acumulado + grupo + consecutivo.zfill(5), instancia
        acumulado += grupo
        if len(acumulado) > 12:
            break
    return None


def _procesos_en(texto: str) -> tuple[str, dict[tuple[str, Optional[str]], int]]:
    """Texto normalizado y {(proceso, instancia): posición de la primera
    aparición} de los radicados que aparecen en `texto`, escritos de cualquiera
    de las formas reconocidas."""
    texto = _GUIONES.sub("-", texto or "")
    encontrados: dict[tuple[str, Optional[str]], int] = {}

    def _agregar(clave, posicion):
        if clave is not None and clave not in encontrados:
            encontrados[clave] = posicion

    for m in _RADICADO_POR_PARTES.finditer(texto):
        radicado = "".join(m.groups())
        if radicado[:2] in TRIBUNAL_CODES:
            _agregar((radicado[:21], radicado[21:]), m.start())
    for patron in (_TIRA_DE_DIGITOS, _TIRA_TOLERANTE):
        for m in patron.finditer(texto):
            _agregar(_interpretar_tira(m.group()), m.start())
    return texto, encontrados


def _con_etiqueta(texto: str, posicion: int) -> bool:
    return bool(_ETIQUETA_RADICADO.search(texto[max(0, posicion - 40):posicion]))


def _radicados_en(texto: str) -> list[str]:
    """Radicados completos (23 dígitos) distintos que aparecen en `texto`, en
    orden de aparición. Solo cuenta los que empiezan con un código de
    departamento real — descarta números largos que no son radicados."""
    encontrados: list[str] = []
    candidatos = ["".join(m.groups()) for m in _RADICADO_POR_PARTES.finditer(texto or "")]
    candidatos += [re.sub(r"\D", "", m.group()) for m in _TIRA_DE_DIGITOS.finditer(texto or "")]
    for radicado in candidatos:
        if len(radicado) == 23 and radicado[:2] in TRIBUNAL_CODES and radicado not in encontrados:
            encontrados.append(radicado)
    return encontrados


def _titulo_con_radicado(radicado: str, codigo: str) -> str:
    n = radicado
    return f"T_{codigo}_{n[0:5]}_{n[5:7]}_{n[7:9]}_{n[9:12]}_{n[12:16]}_{n[16:21]}_{n[21:23]}"


def _normalize_title(name_no_ext: str, dept_code: str) -> str:
    """Reemplaza el nombre de archivo crudo por "T_{CODIGO}_{radicado segmentado}"
    cuando el nombre trae un radicado completo (23 dígitos) y el tribunal tiene
    un código conocido. El radicado puede venir en cualquier parte del nombre:
    al principio (lo más común), después de una fecha "DD-MM-YYYY " o de un
    número de orden, pegado a palabras ("Auto88001…"), o con guiones/espacios
    entre sus partes. El resto del nombre original (juez, acción) se descarta.
    Si no calza (nombre de persona, aviso genérico "ESTADO...", tribunal sin
    código, número con dígitos de más o de menos) o trae DOS radicados
    distintos (no se sabe cuál es el del documento), se deja tal cual — nunca
    se adivina."""
    codigo = TRIBUNAL_CODES.get(dept_code)
    if codigo is None:
        return name_no_ext

    radicados = _radicados_en(name_no_ext)
    if len(radicados) == 1:
        return _titulo_con_radicado(radicados[0], codigo)
    if radicados:
        return name_no_ext
    # Formas más sueltas ("…004 – 2024 – 00108 – 01", "…/02"): solo si traen
    # la instancia y hay un único radicado.
    _, encontrados = _procesos_en(name_no_ext)
    completos = {proceso + instancia for proceso, instancia in encontrados if instancia}
    if len(completos) != 1:
        return name_no_ext
    return _titulo_con_radicado(completos.pop(), codigo)


def _titulo_desde_pdf(nombre: str, texto_pdf: str, dept_code: str) -> Optional[str]:
    """Título "T_{CODIGO}_…" a partir del radicado escrito en el documento, para
    cuando el nombre de archivo no lo trae completo. Devuelve None cuando no se
    puede decidir con seguridad.

    - Si el nombre trae un número corto ("2022-00078-01", "(2023-0143)"), se
      usa el proceso del PDF con ese año y consecutivo; si el PDF no trae
      ninguno así, nada (el nombre y el PDF hablan de procesos distintos).
      La instancia la da el nombre cuando la trae: es la que puso el propio
      tribunal, aunque el PDF cite solo la de primera instancia.
    - Si no, el PDF debe traer un único proceso, o uno solo anunciado como
      "Radicación:"/"Rad."/"Expediente…" (el nombre suele traer solo la
      radicación interna del tribunal, "77.726").
    - Si el proceso aparece en varias instancias (…00 del juzgado y …01 del
      tribunal) y nada dice cuál es la del documento, se usa la anunciada
      como "Radicación:" o, si no, la más alta: la del tribunal.
    """
    codigo = TRIBUNAL_CODES.get(dept_code)
    if codigo is None or _es_lista_de_estados(nombre):
        return None
    texto, encontrados = _procesos_en(texto_pdf)
    if not encontrados:
        return None

    claves = _claves_cortas(nombre)
    clave = next(
        (k for k in claves if any(p[12:16] == k[0] and p[16:21] == k[1] for p, _ in encontrados)),
        None,
    )
    if claves and clave is None:
        return None

    if clave is not None:
        anio, consecutivo, instancia_nombre = clave
        candidatos = [r for r in encontrados if r[0][12:16] == anio and r[0][16:21] == consecutivo]
        if instancia_nombre:
            exactos = {p for p, i in candidatos if i == instancia_nombre}
            if len(exactos) == 1:
                return _titulo_con_radicado(exactos.pop() + instancia_nombre, codigo)
        if len({p for p, _ in candidatos}) != 1:
            return None
        if instancia_nombre:
            return _titulo_con_radicado(candidatos[0][0] + instancia_nombre, codigo)
    else:
        candidatos = list(encontrados)
        procesos = {p for p, _ in candidatos}
        # Tres o más procesos y ningún número en el nombre: es una lista
        # (tabla de Estados, fijación en lista, traslados) aunque no se llame
        # así ("tribunal superior sala laboral_11-09-2026").
        if len(procesos) >= 3:
            return None
        if len(procesos) != 1:
            candidatos = [r for r in candidatos if _con_etiqueta(texto, encontrados[r])]
            if len({p for p, _ in candidatos}) != 1:
                return None

    proceso = candidatos[0][0]
    instancias = sorted({i for _, i in candidatos if i})
    if not instancias:
        return None
    if len(instancias) > 1:
        etiquetadas = {i for p, i in candidatos if i and _con_etiqueta(texto, encontrados[(p, i)])}
        if len(etiquetadas) == 1:
            return _titulo_con_radicado(proceso + etiquetadas.pop(), codigo)
    return _titulo_con_radicado(proceso + instancias[-1], codigo)


# Salas donde el nombre trae solo "juzgado-año-consecutivo-instancia"
# ("008-2023-00294-01 NOMBRE") y el radicado completo no aparece ni en el PDF.
# El juzgado de origen se deduce de la sala: (municipio + entidad +
# especialidad del juzgado, lo mismo para el propio tribunal cuando el número
# de juzgado es 000, o None si en esa sala no se deduce). Verificado contra
# los documentos de esas salas cuyo PDF sí trae el radicado completo
# (octubre 2026): Familia de Bogotá 54 de 55, Civil del Valle 15 de 15 sin
# contar los 000.
_JUZGADO_DE_ORIGEN = {
    ("11", "FAMILIA"): ("1100131" "10", "1100122" "10"),
    ("76", "CIVIL"): ("7600131" "03", None),
}
_JUZGADO_ANIO_CONSECUTIVO = re.compile(
    r"(?<![\d\-.])(\d{2,3})\s*-\s*((?:19|20)\d{2})\s*-\s*(\d{3,5})\s*-\s*(\d{2})(?!\d)"
)
# La Sala Civil del Valle recibe procesos de todo el distrito, no solo de
# Cali: si el PDF nombra un juzgado de otro municipio, no se deduce nada.
_OTRO_MUNICIPIO_DEL_VALLE = re.compile(
    r"(?i)circuito[^\n]{0,40}?\bde\s+(palmira|buga|tulu[aá]|cartago|buenaventura|roldanillo|sevilla|"
    r"jamund[ií]|yumbo|caicedonia|candelaria|florida|pradera|el cerrito|dagua|zarzal|la uni[oó]n|"
    r"ginebra|guacar[ií]|restrepo|bugalagrande|andaluc[ií]a|el [aá]guila|ansermanuevo|toro|obando|"
    r"la victoria|vijes|yotoco|riofr[ií]o|trujillo|bol[ií]var|el dovio|versalles|argelia|alcal[aá]|"
    r"ulloa|calima|la cumbre|san pedro)\b"
)


def _titulo_por_juzgado_de_origen(nombre: str, especialidad: Optional[str], texto_pdf: str, dept_code: str) -> Optional[str]:
    """Título "T_…" armado con el juzgado de origen que se deduce de la sala
    (ver _JUZGADO_DE_ORIGEN), para los nombres "ddd-AAAA-ccccc-ii". None si la
    sala no tiene regla, el nombre no trae la instancia, o el PDF apunta a un
    juzgado de otro municipio."""
    codigo = TRIBUNAL_CODES.get(dept_code)
    regla = _JUZGADO_DE_ORIGEN.get((dept_code, (especialidad or "").strip().upper()))
    if codigo is None or regla is None or _es_lista_de_estados(nombre):
        return None
    m = _JUZGADO_ANIO_CONSECUTIVO.search(nombre)
    if not m:
        return None
    juzgado, anio, consecutivo, instancia = m.groups()
    juzgado_de_origen, tribunal = regla
    if int(juzgado) == 0:
        if tribunal is None:
            return None
        prefijo = tribunal + "000"
    elif int(juzgado) <= 99:
        prefijo = juzgado_de_origen + juzgado.zfill(3)
    else:
        return None
    if dept_code == "76" and _OTRO_MUNICIPIO_DEL_VALLE.search(texto_pdf or ""):
        return None
    return _titulo_con_radicado(prefijo + anio + consecutivo.zfill(5) + instancia, codigo)


def _titulo_desde_paginas(
    nombre: str, paginas: list[str], dept_code: str, especialidad: Optional[str] = None
) -> Optional[str]:
    """_titulo_desde_pdf con la primera página y, si ahí no se decide, con las
    dos primeras juntas (en ~60 documentos el radicado está en la segunda).
    Como último recurso, el juzgado de origen deducido de la sala
    (_titulo_por_juzgado_de_origen)."""
    if not paginas:
        return None
    titulo = _titulo_desde_pdf(nombre, paginas[0], dept_code)
    if titulo is None and len(paginas) > 1:
        titulo = _titulo_desde_pdf(nombre, "\n".join(paginas[:2]), dept_code)
    if titulo is None:
        titulo = _titulo_por_juzgado_de_origen(nombre, especialidad, "\n".join(paginas[:2]), dept_code)
    return titulo


_JUEZ_PREFIX = re.compile(r"^\s*(Dr|Dra)[A-ZÁÉÍÓÚÑ][a-záéíóúñ]*")
_CAMEL_CASE_BOUNDARY = re.compile(r"(?<=[a-záéíóúñ])(?=[A-ZÁÉÍÓÚÑ])")


def _extract_detalle(name_no_ext: str) -> Optional[str]:
    """Extrae una descripción legible de la acción (sin el juez) cuando el
    nombre de archivo empieza con el radicado completo (23 dígitos). El
    apellido del juez (prefijo "Dr"/"Dra") se descarta por completo; el resto
    se separa en palabras por límites de CamelCase y guiones bajos. Si no hay
    prefijo "Dr"/"Dra" (pasa en datos reales), se separa el resto completo tal
    cual. Devuelve None cuando el nombre no calza con el patrón de radicado, o
    cuando el radicado no viene acompañado de ninguna acción (nombre de
    archivo que es solo el radicado, sin texto después)."""
    match = _RADICADO_PREFIX.match(name_no_ext)
    if not match:
        return None

    resto = name_no_ext[match.end():]
    resto = _JUEZ_PREFIX.sub("", resto, count=1)
    resto = resto.replace("_", " ")
    return _CAMEL_CASE_BOUNDARY.sub(" ", resto).strip() or None


def _extraer_texto_paginas(local_path, cantidad: int = 2) -> list[str]:
    """Texto de las primeras `cantidad` páginas del PDF."""
    # Los PDFs de Rama Judicial vienen cifrados con AES (contraseña vacía);
    # pypdf los abre solo si 'cryptography' está instalado (ver requirements).
    from pypdf import PdfReader

    reader = PdfReader(str(local_path))
    if reader.is_encrypted:
        try:
            reader.decrypt("")
        except Exception:
            pass
    return [page.extract_text() or "" for page in reader.pages[:cantidad]]


# This site (shared by all 33 Tribunales Superiores + Juzgados sources, since
# they're all the same scraper class differing only by dept_code) goes
# through the same slow/overloaded stretches as JEP and SAMAI — confirmed in
# production when Tribunal Superior de Antioquia exhausted 3 immediate
# retries on a 60s read timeout during a period of heavy load. ConnectionError
# (a dropped/reset connection) is just as transient as a Timeout and was
# previously not retried at all, propagating on the very first occurrence.
# timeout=120 (raised from 60): even with the retry+backoff above, Antioquia
# and Tribunal Superior de Bogotá kept hitting the exact same 60s read
# timeout across three separate production runs, including at delta=10
# (small page) — ruling out response size as the cause and pointing at this
# site genuinely taking over a minute to answer some requests.
_RETRYABLE_NETWORK_ERRORS = (
    requests.exceptions.Timeout,
    requests.exceptions.ConnectionError,
    requests.exceptions.ChunkedEncodingError,
)


def _get_with_retries(session, url, headers, params=None, timeout=120, retries=3):
    """GET with up to `retries` attempts, retrying on a timeout, a dropped/reset
    connection, an interrupted read, or a 5xx status. A short pause between
    attempts (mirrors samai.py's time.sleep(5)) gives a genuinely overloaded
    site a moment to recover instead of hammering it again immediately. On
    the final attempt a transient network error propagates to the caller; a
    persistent 5xx does not raise here; it's left to the caller's own
    `raise_for_status()`/try-except.
    """
    resp = None
    for attempt in range(retries):
        try:
            resp = session.get(url, headers=headers, params=params, timeout=timeout)
            if resp.status_code < 500:
                break
        except _RETRYABLE_NETWORK_ERRORS:
            if attempt == retries - 1:
                raise
        if attempt < retries - 1:
            time.sleep(5)
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
    # El título corregido desde el PDF agrupa actuaciones del mismo radicado;
    # el archivo lo renombra storage_sync (ver BaseScrapper).
    rekey_storage_on_title_fix = False

    def __init__(self, dept_code: str = "", dept_name: str = "Rama Judicial", entidad_id: str = "22"):
        self.source = dept_name
        self.url = _TRIBUNALES_SUPERIORES_URL
        self._dept_code = dept_code
        self._entidad_id = entidad_id
        self._instance_id = None

    def _se_revisa_el_pdf(self, titulo: str) -> bool:
        """Si vale la pena leer la primera página del documento descargado: los
        que ya tienen título de radicado (para la fecha de providencia) y, en
        Tribunales Superiores, los que no lo tienen y no son una lista de
        Estados (para recuperar el radicado — ver _titulo_desde_pdf)."""
        if is_radicado_title(titulo):
            return True
        return self._dept_code in TRIBUNAL_CODES and not _es_lista_de_estados(titulo)

    def resolve_unverified_document(self, doc, local_path, content_type) -> None:
        # Rama Judicial no expone el radicado completo ni la fecha de
        # providencia en sus metadatos; ambos se leen del PDF (el radicado de
        # las dos primeras páginas, la fecha de la primera). Si no se puede
        # leer o no hay un radicado sin ambigüedad, el título queda como venía
        # y f_providencia en None (el nombre canónico usa el respaldo
        # f_public). Nunca interrumpe la ingestión.
        if not self._se_revisa_el_pdf(doc.title):
            return
        try:
            paginas = _extraer_texto_paginas(local_path)
        except Exception as e:
            logger.warning("No se pudo leer el PDF %s: %s", getattr(local_path, "name", local_path), e)
            return
        if not is_radicado_title(doc.title):
            titulo = _titulo_desde_paginas(doc.title, paginas, self._dept_code, doc.especialidad)
            if titulo is None:
                return
            doc.title = titulo
        fecha = parse_fecha_providencia_es(paginas[0] if paginas else "")
        if fecha is not None:
            doc.f_providencia = fecha.strftime("%Y-%m-%d")

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
        except _RETRYABLE_NETWORK_ERRORS:
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

    # limit=100 (the site's own page-size param, "delta") confirmed live against
    # this endpoint: a wide date range for Bogotá dropped from 76 pages at
    # delta=10 to 8 pages at delta=100, each request still answering in ~1-2s —
    # the previous limit=10 default meant far more sequential round trips than
    # this site needs, and was the main driver of long runs for wide ranges.
    def scrap(self, fini, ffin, q="", limit=100, stop_event=None, on_progress=None) -> List[RawDocModel]:
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
                    logger.warning("Error procesando fila: %s", e)
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
                                logger.warning(
                                    "%s cambió de tamaño entre listados (%s -> %s bytes); "
                                    "se conserva la primera aparición.",
                                    file_uuid, tamano_anterior, tamano_actual,
                                )
                            continue
                        tamanos_por_uuid[file_uuid] = check_remote_content_length(download_url)

                        name_no_ext = (filename.rsplit(".", 1)[0] if "." in filename else filename).strip()
                        doc_name = _INVALID_PATH_CHARS.sub("-", name_no_ext)
                        # mismo orden que las demás fuentes: clasificación → fecha → tipo
                        save_path = storage_path(
                            self.source, especialidad_dir, despacho_dir, fecha_p, tipo_dir, f"{doc_name}(extension)"
                        )
                        titulo_normalizado = _normalize_title(name_no_ext, self._dept_code)
                        docs.append(RawDocModel(
                            source=self.source,
                            link={"url": download_url, "method": "GET", "body": {"path": file_uuid}},
                            title=titulo_normalizado,
                            tipo=tipo,
                            especialidad=especialidad_raw,
                            seccion=despacho_raw,
                            f_public=fecha_p,
                            detalle=_extract_detalle(name_no_ext),
                            save_path=save_path,
                            title_unverified=self._se_revisa_el_pdf(titulo_normalizado),
                        ))

            if num_pag >= max_pages:
                break
            num_pag += 1

        return docs
