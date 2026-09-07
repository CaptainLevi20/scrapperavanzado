import datetime
import json
import re
import unicodedata
from typing import List, Optional, Tuple

import requests

from core.models import RawDocModel
from core.scrapers.base import BaseScrapper
from core.scrapers.registry import register_family
from core.utils import storage_path

_BASE = "https://www.supersalud.gov.co/es-co"
_CONTEXTINFO = f"{_BASE}/_api/contextinfo"
_PROCESS_QUERY = f"{_BASE}/_vti_bin/client.svc/ProcessQuery"
_DOCS_PREFIX = "https://docs.supersalud.gov.co/PortalWeb/Juridica"

# (carpeta en docs.supersalud, tipo mostrado, letra del código de título)
_CATEGORIAS = [
    ("Resoluciones", "Resolución", "R"),
    ("CircularesExterna", "Circular Externa", "C"),
]

_ANIO_MINIMO = 2015
_PAGE = 500

_SOURCE = "Superintendencia Nacional de Salud"

_INVALID_PATH_CHARS = re.compile(r'[\\/*?:"<>|]')
# año (4) + bloque de 12 dígitos (dependencia 6 + consecutivo 6) + sufijo "-D" o "D"
_RADICADO_RE = re.compile(r"(\d{4})(\d{12})-?\d?\b")
_CLASICO_RE = re.compile(r"^0*(\d{1,5})$")
_SUFIJO_ANIO_RE = re.compile(r"\s+de\s+\d{4}\s*$", re.IGNORECASE)
_ANEXO_PREFIJO_RE = re.compile(r"^anexo\s+", re.IGNORECASE)

_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

# Plantilla CSOM ProcessQuery para una KeywordQuery + SearchExecutor.
# Marcadores: __CARPETA__ (carpeta en docs.supersalud), __HEXYEAR__ (año en
# hex UTF-8), __RL__ (RowLimit), __SR__ (StartRow). Los delimitadores ǂ
# alrededor del año son FQL de SharePoint. Estructura verificada contra el
# tráfico real del Content Search Web Part del portal.
_CSOM_BODY = (
    '<Request xmlns="http://schemas.microsoft.com/sharepoint/clientquery/2009" '
    'SchemaVersion="15.0.0.0" LibraryVersion="16.0.0.0" ApplicationName="Javascript Library">'
    "<Actions>"
    '<ObjectPath Id="2" ObjectPathId="1" />'
    '<SetProperty Id="3" ObjectPathId="1" Name="QueryText"><Parameter Type="String">*</Parameter></SetProperty>'
    '<SetProperty Id="4" ObjectPathId="1" Name="QueryTemplate"><Parameter Type="String">'
    "path:&quot;https://docs.supersalud.gov.co/PortalWeb/Juridica/__CARPETA__&quot; "
    "(IsDocument:&quot;True&quot; OR contentclass:&quot;STS_ListItem&quot;)"
    "</Parameter></SetProperty>"
    '<SetProperty Id="5" ObjectPathId="1" Name="RowLimit"><Parameter Type="Number">__RL__</Parameter></SetProperty>'
    '<SetProperty Id="6" ObjectPathId="1" Name="StartRow"><Parameter Type="Number">__SR__</Parameter></SetProperty>'
    '<SetProperty Id="7" ObjectPathId="1" Name="ClientType"><Parameter Type="String">ContentSearchRegular</Parameter></SetProperty>'
    '<SetProperty Id="8" ObjectPathId="1" Name="TrimDuplicates"><Parameter Type="Boolean">false</Parameter></SetProperty>'
    '<SetProperty Id="9" ObjectPathId="1" Name="Culture"><Parameter Type="Number">3082</Parameter></SetProperty>'
    '<ObjectPath Id="11" ObjectPathId="10" />'
    '<Method Name="Add" Id="12" ObjectPathId="10"><Parameters><Parameter Type="String">Title</Parameter></Parameters></Method>'
    '<Method Name="Add" Id="13" ObjectPathId="10"><Parameters><Parameter Type="String">Path</Parameter></Parameters></Method>'
    '<Method Name="Add" Id="14" ObjectPathId="10"><Parameters><Parameter Type="String">NumeroOWSTEXT</Parameter></Parameters></Method>'
    '<Method Name="Add" Id="15" ObjectPathId="10"><Parameters><Parameter Type="String">DescripcionOWSMTXT</Parameter></Parameters></Method>'
    '<Method Name="Add" Id="16" ObjectPathId="10"><Parameters><Parameter Type="String">FechadePublicacionOWSDATE</Parameter></Parameters></Method>'
    '<Method Name="Add" Id="17" ObjectPathId="10"><Parameters><Parameter Type="String">RefinableString00</Parameter></Parameters></Method>'
    '<Method Name="Add" Id="18" ObjectPathId="10"><Parameters><Parameter Type="String">FileExtension</Parameter></Parameters></Method>'
    '<ObjectPath Id="31" ObjectPathId="30" />'
    '<Method Name="Add" Id="32" ObjectPathId="30"><Parameters>'
    '<Parameter Type="String">RefinableString00:&quot;ǂǂ__HEXYEAR__&quot;</Parameter>'
    "</Parameters></Method>"
    '<ObjectPath Id="20" ObjectPathId="19" />'
    '<Method Name="Add" Id="33" ObjectPathId="19"><Parameters>'
    '<Parameter Type="String">FechadePublicacionOWSDATE</Parameter><Parameter Type="Number">1</Parameter>'
    "</Parameters></Method>"
    '<ObjectPath Id="22" ObjectPathId="21" />'
    '<Method Name="ExecuteQuery" Id="23" ObjectPathId="21"><Parameters><Parameter ObjectPathId="1" /></Parameters></Method>'
    "</Actions>"
    "<ObjectPaths>"
    '<Constructor Id="1" TypeId="{80173281-fffd-47b6-9a49-312e06ff8428}" />'
    '<Property Id="10" ParentId="1" Name="SelectProperties" />'
    '<Property Id="30" ParentId="1" Name="RefinementFilters" />'
    '<Property Id="19" ParentId="1" Name="SortList" />'
    '<Constructor Id="21" TypeId="{8d2ac302-db2f-46fe-9015-872b35f15098}" />'
    "</ObjectPaths></Request>"
)


def _sin_acentos(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s or "") if not unicodedata.combining(c))


def _es_anexo(title: Optional[str]) -> bool:
    return _sin_acentos((title or "").strip()).lower().startswith("anexo")


def _parse_numero(numero_raw: Optional[str], title: Optional[str]) -> Optional[int]:
    base = (numero_raw or "").strip() or (title or "").strip()
    if not base:
        return None
    base = _sin_acentos(base)
    base = _ANEXO_PREFIJO_RE.sub("", base)
    base = re.sub(r"\s+", " ", base).strip()
    base = _SUFIJO_ANIO_RE.sub("", base).strip()

    m = _RADICADO_RE.search(base)
    if m:
        return int(m.group(2)[-6:])

    # For classic form, find all digit sequences in the text
    numbers = re.findall(r"\d+", base)
    if len(numbers) == 1 and _CLASICO_RE.match(numbers[0]):
        return int(numbers[0])

    return None


def _safe_title(title: str) -> str:
    return _INVALID_PATH_CHARS.sub("-", title)[:120].strip(" .")


def _titulo(
    letra: str, numero_raw: Optional[str], title_raw: str, anio: str, es_anexo: bool
) -> Tuple[str, bool]:
    numero = _parse_numero(numero_raw, title_raw)
    if numero is None:
        return (title_raw or "").strip()[:120], True
    base = f"{letra}_SNS_{numero:04d}_{anio}"
    if es_anexo:
        base = f"{base}_A01"
    return base, False


def _fecha_publicacion(raw: Optional[str]) -> Optional[str]:
    if not raw:
        return None
    candidato = raw.split("\n")[0].strip()[:10]
    try:
        datetime.date.fromisoformat(candidato)
    except ValueError:
        return None
    return candidato


def _fila_a_doc(fila, tipo, letra, fini, ffin, on_progress) -> Optional[RawDocModel]:
    url = (fila.get("Path") or "").strip()
    if not url:
        return None

    f_public = _fecha_publicacion(fila.get("FechadePublicacionOWSDATE"))
    title_raw = (fila.get("Title") or "").strip()
    if f_public is None:
        if on_progress:
            on_progress(f"[{_SOURCE}] Aviso: fila sin fecha de publicación parseable «{title_raw[:80]}», se omite")
        return None
    if f_public < fini or f_public > ffin:
        return None

    es_anexo = _es_anexo(title_raw)
    title, unverified = _titulo(
        letra, fila.get("NumeroOWSTEXT"), title_raw, f_public[:4], es_anexo
    )
    safe = _safe_title(title)
    return RawDocModel(
        source=_SOURCE,
        link={"url": url, "method": "GET"},
        title=title,
        tipo=tipo,
        f_public=f_public,
        f_providencia=f_public,
        detalle=(fila.get("DescripcionOWSMTXT") or "").strip() or None,
        save_path=storage_path(_SOURCE, f_public, tipo, f"{safe}(extension)"),
        title_unverified=unverified,
    )


def _build_body(carpeta: str, anio: int, start_row: int, row_limit: int = _PAGE) -> str:
    hexyear = str(anio).encode("utf-8").hex()
    return (
        _CSOM_BODY.replace("__CARPETA__", carpeta)
        .replace("__HEXYEAR__", hexyear)
        .replace("__RL__", str(row_limit))
        .replace("__SR__", str(start_row))
    )


def _decode(resp) -> object:
    return json.loads(resp.content.decode("utf-8-sig"))


def _form_digest(session: requests.Session) -> str:
    resp = session.post(_CONTEXTINFO, headers={"Accept": "application/json;odata=nometadata"}, timeout=30)
    resp.raise_for_status()
    return _decode(resp)["FormDigestValue"]


def _process_query(
    session: requests.Session, digest: str, carpeta: str, anio: int, start_row: int, row_limit: int = _PAGE
) -> List[dict]:
    resp = session.post(
        _PROCESS_QUERY,
        data=_build_body(carpeta, anio, start_row, row_limit).encode("utf-8"),
        headers={"Content-Type": "text/xml", "X-RequestDigest": digest},
        timeout=90,
    )
    resp.raise_for_status()
    payload = _decode(resp)
    for item in payload:
        if isinstance(item, dict) and item.get("ErrorInfo"):
            raise RuntimeError(item["ErrorInfo"].get("ErrorMessage") or "ProcessQuery devolvió ErrorInfo")
    for item in payload:
        if isinstance(item, dict) and item.get("ResultTables"):
            for tabla in item["ResultTables"]:
                if tabla.get("TableType") == "RelevantResults":
                    return tabla.get("ResultRows", [])
    return []
