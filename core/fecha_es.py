import re
from datetime import date
from typing import Optional

_MESES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10,
    "noviembre": 11, "diciembre": 12,
}

# Día como dígito (opcionalmente entre paréntesis, como en "diez (10) de ...")
# seguido del mes y luego el primer número de 4 dígitos que aparezca (el año,
# que puede venir entre paréntesis tras "dos mil ...").
#
# El conector entre el día y el mes admite tres formas: la simple "de", la
# formal de los cierres judiciales colombianos "días del mes de" ("a los diez
# (10) días del mes de agosto ..."), y su ausencia total ("31 marzo de 2026",
# como escribe a veces la Superintendencia del Subsidio Familiar). El conector
# entre el mes y el año admite "de" o "del" ("... del año dos mil veintiséis
# (2026)").
#
# El día no puede ser el final de otro número: en "200.3-2-25-012 DE MARZO
# 2025" el 012 es el número de un acuerdo, no el día 12.
#
# El conector entre el mes y el año puede faltar ("06 DE MARZO 2017", "05 ENERO
# 2026": Cámara de Comercio de Armenia y Corporinoquia), pero solo si la fuente
# lo pide (anio_sin_conector=True): en general es peligroso, porque "Boletín
# No 12 Diciembre 2025" (MinSalud) se leería como el 12 de diciembre.
_DIA_Y_MES = (
    r"\(?\s*(?<!\d)(\d{1,2})\s*\)?\s+"
    r"(?:(?:d[ií]as?\s+del\s+mes\s+de|de)\s+)?"
    r"(enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|setiembre|octubre|noviembre|diciembre)"
)
_PATRON = re.compile(_DIA_Y_MES + r"\s+del?\s+[^\d]{0,40}?\(?\s*(\d{4})", re.IGNORECASE)
_PATRON_ANIO_SIN_CONECTOR = re.compile(
    _DIA_Y_MES + r"\s+(?:del?\s+)?[^\d]{0,40}?\(?\s*(\d{4})", re.IGNORECASE
)


def parse_fecha_providencia_es(texto: str, anio_sin_conector: bool = False) -> Optional[date]:
    """Extrae la primera fecha de providencia de un texto en español. Acepta el
    día en dígitos ("8 de mayo de 2026"), en letras con el número entre
    paréntesis ("diez (10) de agosto de dos mil veintiséis (2026)") y la forma
    formal de cierre ("a los diez (10) días del mes de agosto del año dos mil
    veintiséis (2026)"). Tolera saltos de línea. Devuelve None si no encuentra
    una fecha válida. Con anio_sin_conector=True acepta también el año sin "de"
    ("06 DE MARZO 2017"); ver el comentario de _PATRON."""
    if not texto:
        return None
    normalizado = re.sub(r"\s+", " ", texto)
    patron = _PATRON_ANIO_SIN_CONECTOR if anio_sin_conector else _PATRON
    for m in patron.finditer(normalizado):
        dia = int(m.group(1))
        mes = _MESES[m.group(2).lower()]
        anio = int(m.group(3))
        try:
            return date(anio, mes, dia)
        except ValueError:
            continue  # p. ej. "32 de mayo": sigue buscando una fecha válida
    return None
