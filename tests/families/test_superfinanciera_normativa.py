from core.scrapers.families.superfinanciera.normativa import _parse_indice

_BASE = "https://www.superfinanciera.gov.co"


def _indice_html():
    # Estructura real recortada: una tabla con una fila de encabezados y filas
    # de años; cada celda de año trae un <a> cuyo texto es el año.
    return """
    <table>
      <tr><th>Circulares Externas (1)</th><th>Cartas Circulares (2)</th><th>Resoluciones (3)</th></tr>
      <tr>
        <td><a href="/publicaciones/10115974/circulares-externas-2026/">2026</a></td>
        <td><a href="/10115975">2026</a></td>
        <td><a href="/publicaciones/10115976/resoluciones-2026/">2026</a></td>
      </tr>
      <tr>
        <td><a href="/publicaciones/10115459/circulares-externas-2025/">2025</a></td>
        <td><a href="/10115460">2025</a></td>
        <td><a href="/10115461">2025</a></td>
      </tr>
    </table>
    """


def test_parse_indice_agrupa_por_columna_y_anio():
    idx = _parse_indice(_indice_html(), _BASE)

    assert set(idx.keys()) == {"Circulares Externas", "Cartas Circulares", "Resoluciones"}
    assert idx["Circulares Externas"][2026] == f"{_BASE}/publicaciones/10115974/circulares-externas-2026/"
    assert idx["Circulares Externas"][2025] == f"{_BASE}/publicaciones/10115459/circulares-externas-2025/"
    assert idx["Cartas Circulares"][2026] == f"{_BASE}/10115975"
    assert idx["Resoluciones"][2025] == f"{_BASE}/10115461"
