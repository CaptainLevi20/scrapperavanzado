from core.scrapers.families.superfinanciera.conceptos import _parse_pagina, _total_registros

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
