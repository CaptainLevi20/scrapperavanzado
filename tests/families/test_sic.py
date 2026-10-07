from core.scrapers.families.sic import (
    _BASE,
    _ficha,
    _filas_listado,
    _num_paginas,
)

# Marcado real del listado (recortado), 2026-10-07
_FILA = """
<div class="mb-2"><div style="width: 100%;"><div class="views-field views-field-nothing"><span class="field-content"><div class="normas--row shadow-sm p-3 mb-5 bg-body rounded">
	<div class="row">
		<div class="col-md-5">
<span class="text-secondary">Tipo de norma: <strong>Resoluciones  </strong></span>
		</div>
		<div class="col-md-7">
<span class="badge tag--pin label--pin mb-2 ms-2">Despacho de la Superintendencia </span>
		</div>
	</div>
<h2 class="field__label"><a href="{href}" hreflang="es">{titulo}</a></h2>
<div class="col-md-12">
<p> resumen </p>
</div>
</div></span></div></div></div>
"""


def _listado(filas, encabezado="Mostrando la página 1 de 8 páginas"):
    cuerpo = "".join(_FILA.format(href=h, titulo=t) for h, t in filas)
    return f"<html><body><main><div>{encabezado}</div>{cuerpo}</main></body></html>"


def test_filas_listado_extrae_href_y_titulo_limpio():
    html = _listado([
        ("/transparencia/normativa/resolucion-no-77121", "Resolución No. 77121 del 29 de septiembre de 2026 &quot;Por la cual se deroga&quot;"),
        ("/transparencia/normativa/circular-externa-010", "Circular\xa0Externa  010"),
    ])
    assert _filas_listado(html) == [
        ("/transparencia/normativa/resolucion-no-77121",
         'Resolución No. 77121 del 29 de septiembre de 2026 "Por la cual se deroga"'),
        ("/transparencia/normativa/circular-externa-010", "Circular Externa 010"),
    ]


def test_filas_listado_vacio():
    assert _filas_listado("<html><main>Sin resultados</main></html>") == []


def test_num_paginas_lee_el_encabezado():
    assert _num_paginas(_listado([("/a", "x")])) == 8
    assert _num_paginas(_listado([("/a", "x")], "Mostrando la página 1 de 379 páginas")) == 379


def test_num_paginas_sin_encabezado():
    assert _num_paginas(_listado([("/a", "x")], encabezado="")) == 1
    assert _num_paginas(_listado([], encabezado="")) == 0


# Marcado real de una ficha (recortado), 2026-10-07
_FICHA = """
<html><body><main>
<div class="sic--fecha1">
  <div class="field field--name-field-fecha-generacion field--type-datetime field--label-above">
    <div class="field__label">Fecha Expedición</div>
    <div class="field__item"><time datetime="2026-09-29T12:00:00Z" class="datetime">Sep 29, 2026</time></div>
  </div>
</div>
<div class="sic--fecha2">
  <div class="field field--name-field-fecha-publicacion field--type-datetime field--label-above">
    <div class="field__label">Fecha publicación</div>
    <div class="field__item"><time datetime="2026-09-30T12:00:00Z" class="datetime">Sep 30, 2026</time></div>
  </div>
</div>
{adjuntos}
<a href="https://sedeelectronica.sic.gov.co/sites/default/files/normativa/T%C3%A9rminos%20y%20condiciones%20-Sede%20Electr%C3%B3nica.pdf">Términos</a>
</main></body></html>
"""

_ADJUNTOS = """
<div class="sic--adjuntos">
  <div class="field field--name-field-archivo field--type-file field--label-above">
    <div class="field__label">Archivos adjuntos</div>
    <div class="field__items">
      {items}
    </div>
  </div>
</div>
"""

_ITEM = """<div class="field__item"><span class="file file--mime-application-pdf file--application-pdf">
  <a href="{href}" type="application/pdf" target="_blank">Documento<span class="visually-hidden"> (se abrirá en una nueva pestaña)</span></a>
  <p>(276.91 KB)</p></span></div>"""


def _html_ficha(*hrefs):
    adj = _ADJUNTOS.format(items="".join(_ITEM.format(href=h) for h in hrefs)) if hrefs else ""
    return _FICHA.format(adjuntos=adj)


def test_ficha_fechas_y_pdf():
    f = _ficha(_html_ficha("/sites/default/files/normativa/RESOLUCI%C3%93N%2077121%20DE%202026.pdf"))
    assert f.expedicion == "2026-09-29"
    assert f.publicacion == "2026-09-30"
    assert f.pdfs == [f"{_BASE}/sites/default/files/normativa/RESOLUCI%C3%93N%2077121%20DE%202026.pdf"]


def test_ficha_varios_adjuntos_en_orden_y_sin_duplicados():
    f = _ficha(_html_ficha("/sites/default/files/a.pdf", "/sites/default/files/b.pdf", "/sites/default/files/a.pdf"))
    assert f.pdfs == [f"{_BASE}/sites/default/files/a.pdf", f"{_BASE}/sites/default/files/b.pdf"]


def test_ficha_solo_enlace_externo_no_tiene_pdfs():
    # el enlace global "Términos y condiciones" está fuera de field-archivo y no cuenta
    html = _html_ficha().replace(
        "</main>",
        '<div class="sic--enlace"><a href="javascript:void(0)" onclick="showModal(\'https\\u003A\\/\\/www.mintrabajo.gov.co\\/x\')">Ingresa</a></div></main>',
    )
    f = _ficha(html)
    assert f.pdfs == []
    assert f.expedicion == "2026-09-29"


def test_ficha_sin_fechas():
    f = _ficha("<html><main><p>nada</p></main></html>")
    assert (f.expedicion, f.publicacion, f.pdfs) == (None, None, [])
