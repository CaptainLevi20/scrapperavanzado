import responses
from core.scrapers.families.superfinanciera.conceptos import (
    _parse_pagina,
    _total_registros,
    _titulo_concepto,
    _registro_a_doc,
    _RegistroConcepto,
    scrap_conceptos,
    _BUSCAR_URL,
)

_BASE = "https://www.superfinanciera.gov.co"


def _registro_html(concepto, titulo, resumen, id_file):
    return f"""
    <table class="registro">
      <tr><td class="td1">Concepto:</td><td>{concepto}</td></tr>
      <tr><td class="td1">Autor Corporativo:</td><td>Colombia. Superintendencia Financiera de Colombia</td></tr>
      <tr><td class="td1">Título de la norma:</td><td>{titulo}</td></tr>
      <tr><td class="td1">Documento fuente:</td><td>Superintendencia Financiera de Colombia. Conceptos 2021</td></tr>
      <tr><td class="td1">Resumen:</td><td>{resumen}</td></tr>
      <tr><td class="td1">Temas/Materias:</td><td>SERVICIOS FINANCIEROS</td></tr>
      <tr><td class="td1">Acceso web (URL):</td>
          <td><a href="/loader.php?lServicio=Tools2&lTipo=descargas&lFuncion=descargar&idFile={id_file}">Archivo de texto</a></td></tr>
    </table>
    """


def _pagina_html(registros, total=3431):
    cuerpo = "".join(registros)
    return f"""
    <html><body>
      <div>Mostrando del 1 al 25 de {total} registros</div>
      {cuerpo}
      <form name="continuar" action="buscar_integrada.php" method="post">
        <input type="hidden" name="Expresion" value="$">
        <input type="hidden" name="base" value="juris">
        <input type="hidden" name="Opcion" value="libre">
        <input type="hidden" name="coleccion" value="ac|Doctrina y conceptos|TM_">
        <input type="hidden" name="count" value="25">
        <input type="hidden" name="pagina" value="1">
        <input type="hidden" name="desde" value="1">
      </form>
    </body></html>
    """


def test_parse_pagina_extrae_campos_del_registro():
    html = _pagina_html([
        _registro_html("2020311455 - 001 del 5 de febrero de 2021", "AFP. Régimen de inversiones", "Límite del 5%.", "1051137"),
    ])
    regs = _parse_pagina(html, _BASE)

    assert len(regs) == 1
    r = regs[0]
    assert r.radicado == "2020311455"
    assert r.consecutivo == "001"
    assert r.fecha_texto == "5 de febrero de 2021"
    assert r.titulo_norma == "AFP. Régimen de inversiones"
    assert r.resumen == "Límite del 5%."
    assert r.archivo_url == f"{_BASE}/loader.php?lServicio=Tools2&lTipo=descargas&lFuncion=descargar&idFile=1051137"


def test_total_registros():
    assert _total_registros(_pagina_html([], total=3431)) == 3431
    assert _total_registros("<div>sin nada</div>") is None


_SOURCE = "Superintendencia Financiera de Colombia"


def test_titulo_concepto_toma_anio_y_numero_del_radicado():
    assert _titulo_concepto("2026019914", "001") == "CTO_SF_0019914_2026"
    assert _titulo_concepto("2020311455", "1") == "CTO_SF_0311455_2020"


def test_titulo_concepto_sufija_el_consecutivo_solo_si_no_es_1():
    assert _titulo_concepto("1998045919", "1") == "CTO_SF_0045919_1998"
    assert _titulo_concepto("1998045919", "4") == "CTO_SF_0045919_1998_04"
    assert _titulo_concepto("1998045919", "004") == "CTO_SF_0045919_1998_04"


def _reg(concepto_ok=True, id_file="1051137"):
    if concepto_ok:
        return _RegistroConcepto(
            "2020311455", "001", "5 de febrero de 2021", "AFP. Régimen de inversiones",
            "Límite del 5%.", f"https://x/loader.php?idFile={id_file}", "2020311455 - 001 del 5 de febrero de 2021",
        )
    return _RegistroConcepto(
        None, None, "texto sin forma de concepto", "Un título temático", "Resumen.",
        f"https://x/loader.php?idFile={id_file}", "texto sin forma de concepto",
    )


def test_registro_a_doc_arma_el_documento():
    doc = _registro_a_doc(_reg(), "2021-01-01", "2021-12-31", _SOURCE, lambda m: None)
    assert doc.title == "CTO_SF_0311455_2020"
    assert doc.tipo == "Concepto"
    assert doc.f_public == "2021-02-05"
    assert doc.f_providencia == "2021-02-05"
    assert doc.detalle == "AFP. Régimen de inversiones — Límite del 5%."
    assert doc.link == {"url": "https://x/loader.php?idFile=1051137", "method": "GET"}
    assert doc.save_path == "Superintendencia Financiera de Colombia/2021-02-05/Concepto/CTO_SF_0311455_2020(extension)"
    assert doc.title_unverified is False


def test_registro_a_doc_fuera_de_rango_es_none():
    assert _registro_a_doc(_reg(), "2021-03-01", "2021-12-31", _SOURCE, lambda m: None) is None


def test_registro_a_doc_sin_concepto_parseable_usa_titulo_crudo_y_unverified():
    reg = _RegistroConcepto(
        None, None, "8 de mayo de 2026 algo", "Un título temático", "Resumen.",
        "https://x/loader.php?idFile=9", "raw",
    )
    doc = _registro_a_doc(reg, "2026-01-01", "2026-12-31", _SOURCE, lambda m: None)
    assert doc.title_unverified is True
    assert doc.title == "Un título temático"
    assert doc.f_public == "2026-05-08"


def test_registro_a_doc_radicado_corto_no_se_confia_como_anio():
    # Un radicado de 6 dígitos matchea _CONCEPTO_RE pero radicado[:4] = "1234"
    # no es un año: no debe producir un CTO_SF_..._1234 "verificado".
    reg = _RegistroConcepto(
        "123456", "001", "5 de febrero de 2021", "AFP. Régimen de inversiones",
        "Límite del 5%.", "https://x/loader.php?idFile=1", "123456 - 001 del 5 de febrero de 2021",
    )
    doc = _registro_a_doc(reg, "2021-01-01", "2021-12-31", _SOURCE, lambda m: None)
    assert doc.title_unverified is True
    assert not doc.title.startswith("CTO_SF_")
    assert doc.title == "AFP. Régimen de inversiones"


def test_registro_a_doc_radicado_con_anio_absurdo_no_se_confia():
    reg = _RegistroConcepto(
        "300012345678", "001", "5 de febrero de 2021", "Título temático",
        "Resumen.", "https://x/loader.php?idFile=1", "300012345678 - 001 del 5 de febrero de 2021",
    )
    doc = _registro_a_doc(reg, "2021-01-01", "2021-12-31", _SOURCE, lambda m: None)
    assert doc.title_unverified is True
    assert not doc.title.startswith("CTO_SF_")


def test_registro_a_doc_sin_fecha_se_descarta_con_aviso():
    avisos = []
    reg = _RegistroConcepto(None, None, "sin fecha aquí", "T", "R", "https://x/loader.php?idFile=9", "raw")
    assert _registro_a_doc(reg, "2026-01-01", "2026-12-31", _SOURCE, avisos.append) is None
    assert avisos


@responses.activate
def test_scrap_conceptos_recorre_todas_las_paginas_y_filtra_por_fecha():
    # total 50 -> 2 páginas de 25 (pero mandamos pocos registros por simplicidad)
    pagina1 = _pagina_html([
        _registro_html("2021012412 - 003 del 23 de febrero de 2021", "Almacenes", "R1", "111"),
        _registro_html("2019009999 - 001 del 1 de marzo de 2019", "Viejo", "R2", "222"),
    ], total=50)
    pagina2 = _pagina_html([
        _registro_html("2021041211 - 001 del 1 de marzo de 2021", "Broker", "R3", "333"),
    ], total=50)
    responses.add(responses.POST, _BUSCAR_URL, body=pagina1)   # primera consulta
    responses.add(responses.POST, _BUSCAR_URL, body=pagina2)   # página 2

    docs = scrap_conceptos("2021-01-01", "2021-12-31", _SOURCE, on_progress=lambda m: None)

    titles = sorted(d.title for d in docs)
    assert titles == ["CTO_SF_0012412_2021_03", "CTO_SF_0041211_2021"]  # el de 2019 queda fuera de rango
    # se hicieron 2 POST (primera + página 2)
    assert len(responses.calls) == 2


@responses.activate
def test_scrap_conceptos_sin_texto_de_total_emite_error():
    # La respuesta no trae "de N registros" ni ninguna <table class="registro">:
    # una miss total del parser no puede verse igual que "0 conceptos nuevos".
    responses.add(responses.POST, _BUSCAR_URL, body="<html><body>formato inesperado</body></html>")
    avisos = []

    docs = scrap_conceptos("2021-01-01", "2021-12-31", _SOURCE, on_progress=avisos.append)

    assert docs == []
    assert any("Error" in a for a in avisos)


@responses.activate
def test_scrap_conceptos_reintenta_una_pagina_fallida_y_sigue():
    pagina1 = _pagina_html([
        _registro_html("2021012412 - 001 del 23 de febrero de 2021", "A", "Res", "111"),
    ], total=50)
    responses.add(responses.POST, _BUSCAR_URL, body=pagina1)
    responses.add(responses.POST, _BUSCAR_URL, status=500)  # página 2, primer intento
    responses.add(responses.POST, _BUSCAR_URL, status=500)  # página 2, reintento
    avisos = []

    docs = scrap_conceptos("2021-01-01", "2021-12-31", _SOURCE, on_progress=avisos.append)

    assert [d.title for d in docs] == ["CTO_SF_0012412_2021"]
    assert any("Error" in a for a in avisos)
