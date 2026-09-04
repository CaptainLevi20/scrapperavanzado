from core.scrapers.families.superfinanciera.normativa import (
    _parse_indice, _parse_pagina_anio, _fecha_iso, _titulo, _fila_a_docs, _FilaNormativa,
)

_BASE = "https://www.superfinanciera.gov.co"
_SOURCE = "Superintendencia Financiera de Colombia"


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
    assert filas[0].numero_link == f"{_BASE}/loader.php?lServicio=Tools2&lTipo=descargas&lFuncion=descargar&idFile=111"
    assert filas[0].fecha_raw == "Septiembre 01"
    assert filas[0].descripcion.startswith("Imparte instrucciones sobre prospectos.")
    assert filas[0].anexos_urls == [f"{_BASE}/loader.php?idFile=222"]
    assert filas[1].numero_raw == "007"
    assert filas[1].anexos_urls == []


def test_fecha_iso_arma_la_fecha_con_el_anio_de_la_pagina():
    assert _fecha_iso("Septiembre 01", 2026) == "2026-09-01"
    assert _fecha_iso("Diciembre 30", 2020) == "2020-12-30"
    assert _fecha_iso("sin fecha", 2026) is None


def test_titulo_canonico_por_tipo():
    assert _titulo("C", "8", 2026) == ("C_SF_0008_2026", False)
    assert _titulo("CCIR", "20", 2026) == ("CCIR_SF_0020_2026", False)
    assert _titulo("R", "1215", 2020) == ("R_SF_1215_2020", False)
    assert _titulo("C", "s/n", 2026) == ("s/n", True)


def test_fila_a_docs_documento_madre_y_anexos():
    fila = _FilaNormativa(
        numero_raw="8",
        numero_link="https://www.superfinanciera.gov.co/loader.php?idFile=111",
        fecha_raw="Septiembre 01",
        descripcion="Imparte instrucciones.",
        anexos_urls=["https://www.superfinanciera.gov.co/loader.php?idFile=222",
                     "https://www.superfinanciera.gov.co/loader.php?idFile=223"],
    )
    docs = _fila_a_docs(
        fila,
        tipo="Circular Externa",
        sigla="C",
        anio=2026,
        numero_link="https://www.superfinanciera.gov.co/loader.php?idFile=111",
        fini="2026-01-01",
        ffin="2026-12-31",
        source=_SOURCE,
        on_progress=lambda m: None,
    )

    assert [d.title for d in docs] == ["C_SF_0008_2026", "C_SF_0008_2026_A01", "C_SF_0008_2026_A02"]
    madre = docs[0]
    assert madre.tipo == "Circular Externa"
    assert madre.f_public == "2026-09-01"
    assert madre.f_providencia == "2026-09-01"
    assert madre.detalle == "Imparte instrucciones."
    assert madre.link == {"url": "https://www.superfinanciera.gov.co/loader.php?idFile=111", "method": "GET"}
    assert madre.save_path == "Superintendencia Financiera de Colombia/2026-09-01/Circular Externa/C_SF_0008_2026(extension)"
    anexo1 = docs[1]
    assert anexo1.tipo == "Circular Externa"
    assert anexo1.f_public == "2026-09-01"
    assert anexo1.link == {"url": "https://www.superfinanciera.gov.co/loader.php?idFile=222", "method": "GET"}
    assert anexo1.save_path == "Superintendencia Financiera de Colombia/2026-09-01/Circular Externa/C_SF_0008_2026_A01(extension)"


def test_fila_a_docs_fuera_de_rango_se_descarta():
    fila = _FilaNormativa("8", "https://x/loader.php?idFile=1", "Septiembre 01", "x", [])
    docs = _fila_a_docs(
        fila, tipo="Circular Externa", sigla="C", anio=2026,
        numero_link="https://x/loader.php?idFile=1",
        fini="2026-01-01", ffin="2026-06-30", source=_SOURCE, on_progress=lambda m: None,
    )
    assert docs == []


def test_fila_a_docs_sin_numero_marca_unverified_y_no_emite_anexos():
    fila = _FilaNormativa("s/n", "https://x/loader.php?idFile=1", "Septiembre 01", "x",
                          ["https://x/loader.php?idFile=222"])
    docs = _fila_a_docs(
        fila, tipo="Circular Externa", sigla="C", anio=2026,
        numero_link="https://x/loader.php?idFile=1",
        fini="2026-01-01", ffin="2026-12-31", source=_SOURCE, on_progress=lambda m: None,
    )
    assert len(docs) == 1
    assert docs[0].title_unverified is True


def test_fila_a_docs_fecha_no_parseable_usa_primero_de_enero_y_avisa():
    avisos = []
    fila = _FilaNormativa("8", "https://x/loader.php?idFile=1", "??", "x", [])
    docs = _fila_a_docs(
        fila, tipo="Circular Externa", sigla="C", anio=2026,
        numero_link="https://x/loader.php?idFile=1",
        fini="2026-01-01", ffin="2026-12-31", source=_SOURCE, on_progress=avisos.append,
    )
    assert docs[0].f_public == "2026-01-01"
    assert any("Error" not in a and "01-01" not in a for a in avisos) or avisos  # hay al menos un aviso
