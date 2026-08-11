import re
from datetime import date
from typing import Optional

_MESES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10,
    "noviembre": 11, "diciembre": 12,
}

# Día como dígito (opcionalmente entre paréntesis, como en "diez (10) de ...")
# seguido de "de {mes} de", y luego el primer número de 4 dígitos que aparezca
# (el año, que puede venir entre paréntesis tras "dos mil ...").
_PATRON = re.compile(
    r"\(?\s*(\d{1,2})\s*\)?\s+de\s+"
    r"(enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|setiembre|octubre|noviembre|diciembre)"
    r"\s+de\s+[^\d]{0,40}?\(?\s*(\d{4})",
    re.IGNORECASE,
)


def parse_fecha_providencia_es(texto: str) -> Optional[date]:
    """Extrae la primera fecha de providencia de un texto en español. Acepta el
    día en dígitos ("8 de mayo de 2026") o en letras con el número entre
    paréntesis ("diez (10) de agosto de dos mil veintiséis (2026)"). Tolera
    saltos de línea. Devuelve None si no encuentra una fecha válida."""
    if not texto:
        return None
    normalizado = re.sub(r"\s+", " ", texto)
    for m in _PATRON.finditer(normalizado):
        dia = int(m.group(1))
        mes = _MESES[m.group(2).lower()]
        anio = int(m.group(3))
        try:
            return date(anio, mes, dia)
        except ValueError:
            continue  # p. ej. "32 de mayo": sigue buscando una fecha válida
    return None
