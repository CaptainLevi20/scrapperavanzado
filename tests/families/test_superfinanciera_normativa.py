from core.scrapers.families.superfinanciera.normativa import _parse_indice, _parse_pagina_anio

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


def _pagina_anio_html():
    # Real recortado: una sola <table> con encabezados Número|Fecha|Descripción|Boletín*
    return """
    <table>
      <tr><th>Número</th><th>Fecha</th><th>Descripción</th><th>Boletín*</th></tr>
      <tr>
        <td><a href="/loader.php?lServicio=Tools2&lTipo=descargas&lFuncion=descargar&idFile=111">008</a></td>
        <td>Septiembre 01</td>
        <td>Imparte instrucciones sobre prospectos. <a href="/loader.php?idFile=222">Anexo</a>.</td>
        <td>831</td>
      </tr>
      <tr>
        <td><a href="/loader.php?idFile=333">007</a></td>
        <td>Agosto 26</td>
        <td>Mitiga efectos del Decreto 1171 de 2026.</td>
        <td>826</td>
      </tr>
    </table>
    """


def test_parse_pagina_anio_extrae_filas_y_anexos():
    filas = _parse_pagina_anio(_pagina_anio_html(), _BASE)

    assert len(filas) == 2
    assert filas[0].numero_raw == "008"
    assert filas[0].fecha_raw == "Septiembre 01"
    assert filas[0].descripcion.startswith("Imparte instrucciones sobre prospectos.")
    assert filas[0].anexos_urls == [f"{_BASE}/loader.php?idFile=222"]
    assert filas[1].numero_raw == "007"
    assert filas[1].anexos_urls == []
