from pathlib import Path

from core.cali_decretos import (
    es_pdf_valido,
    normalizar_numero,
    parse_pagina,
    resolver_anio,
    ruta_destino,
    _normalizar_url,
)

# One <tr> from a real paginador.php response, trimmed to two rows: one http PDF,
# one ftp PDF, plus the pager line page-1 responses carry.
_HTML = """
<table><thead><tr><th>TIPO</th></tr></thead><tbody>
<tr><td><center>DECRETO</center></td><td><center>0001</center></td>
<td><center>1974-01-02</center></td><td class='text-left'>Por el cual se impone una multa</td>
<td><a href="javascript:;" onMouseUp="MM_openBrWindow1('nota.php?cod=10860','descargar','')">Ver</a></td>
<td><center>1974</center></td><td><center>SECRETARIA GENERAL</center></td>
<td><button type='button' href="javascript:;" onMouseUp="MM_openBrWindow(10860,'http://www.cali.gov.co/aplicaciones/boletin_publicaciones/../boletin_publicaciones/imagenes_documentos_decretos/abc123.pdf','descargar','width=600,height=400')">Descargar</button></td></tr>
<tr><td><center>DECRETO</center></td><td><center>0001</center></td>
<td><center>1984-01-02</center></td><td class='text-left'>Otro</td>
<td><a href="javascript:;">Ver</a></td>
<td><center>1984</center></td><td><center>SECRETARIA GENERAL</center></td>
<td><button type='button' onMouseUp="MM_openBrWindow(23337,'ftp://ftp.cali.gov.co/DECRETOS/1984/DECRETO0001ENERO1984.pdf','descargar','width=600,height=400')">Descargar</button></td></tr>
</tbody>
<td colspan='10'><div><nav><ul class='pager'>
<li><a href='#'>Primero</a></li></ul></nav></div>
<b>71945 registros (filtrado de 71969 registros en total)</b>
<center><strong>Pagina 1/7195</strong></center></td></table>
"""


def test_parse_pagina_extracts_rows_pdf_urls_and_totals():
    pagina = parse_pagina(_HTML)
    assert len(pagina.filas) == 2
    assert pagina.filas[0].numero_raw == "0001"
    assert pagina.filas[0].fecha == "1974-01-02"
    assert pagina.filas[0].anio_raw == "1974"
    assert pagina.filas[0].pdf_url == (
        "https://www.cali.gov.co/aplicaciones/boletin_publicaciones/"
        "imagenes_documentos_decretos/abc123.pdf"
    )
    assert pagina.filas[1].pdf_url == "ftp://ftp.cali.gov.co/DECRETOS/1984/DECRETO0001ENERO1984.pdf"
    assert pagina.total_paginas == 7195
    assert pagina.total_registros == 71969


def test_parse_pagina_row_without_download_button_has_none_url():
    html = """
    <table><tbody><tr>
    <td>DECRETO</td><td>0005</td><td>1975-02-02</td><td>x</td><td>y</td><td>1975</td><td>SG</td>
    <td>sin boton</td></tr></tbody></table>
    """
    pagina = parse_pagina(html)
    assert len(pagina.filas) == 1
    assert pagina.filas[0].pdf_url is None
    assert pagina.total_paginas is None
    assert pagina.total_registros is None


def test_normalizar_numero():
    assert normalizar_numero("1") == "0001"
    assert normalizar_numero("0001") == "0001"
    assert normalizar_numero("1234") == "1234"
    assert normalizar_numero("12345") == "12345"
    assert normalizar_numero("0010A") == "0010A"
    assert normalizar_numero("13 bis") == "13-BIS"
    assert normalizar_numero("") is None
    assert normalizar_numero("—") is None
    assert normalizar_numero("   ") is None


def test_resolver_anio():
    assert resolver_anio("1996", "1996-01-02") == 1996
    assert resolver_anio("", "1996-01-02") == 1996
    assert resolver_anio("  ", "2019-12-31") == 2019
    assert resolver_anio("", "") is None
    assert resolver_anio("abcd", "no hay fecha") is None


def test_ruta_destino():
    base = Path("D:/DESCARGA")
    assert ruta_destino(base, "0010", 1987) == base / "DECRETOS" / "ALCACALI" / "1987" / "D_ALCACALI_0010_1987.pdf"
    assert ruta_destino(base, "0010", 1987, sufijo=2) == (
        base / "DECRETOS" / "ALCACALI" / "1987" / "D_ALCACALI_0010_1987_2.pdf"
    )


def test_es_pdf_valido():
    assert es_pdf_valido(b"%PDF", 5000) is True
    assert es_pdf_valido(b"<htm", 5000) is False
    assert es_pdf_valido(b"%PDF", 200) is False


def test_normalizar_url_collapses_dotdot_and_upgrades_http():
    assert _normalizar_url(
        "http://www.cali.gov.co/aplicaciones/boletin_publicaciones/../boletin_publicaciones/x/a.pdf"
    ) == "https://www.cali.gov.co/aplicaciones/boletin_publicaciones/x/a.pdf"
    # ftp URLs are left untouched
    assert _normalizar_url("ftp://ftp.cali.gov.co/x.pdf") == "ftp://ftp.cali.gov.co/x.pdf"
