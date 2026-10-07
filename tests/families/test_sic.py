from core.scrapers.families.sic import (
    _BASE,
    _CLAS_CIR,
    _CLAS_DOC,
    _CLAS_RES,
    _CLAS_TCU,
    _TIPO_CIR,
    _TIPO_CTO,
    _TIPO_REL,
    _TIPO_RES,
    _TIPO_TCU,
    _clasificar,
    _crudo,
    _safe_title,
    _titulo,
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


def test_clasificar_resoluciones_incluye_nombramientos():
    assert _clasificar(_CLAS_RES, 'Resolución No. 77121 del 29 de septiembre de 2026 "Por la cual se deroga"') == _TIPO_RES
    assert _clasificar(_CLAS_RES, "Resolución No. 29705 de 2026 PROFESIONAL U. 2044-07 G.T. REGULACIÓN - OFICINA ASESORA JURÍDICA") == _TIPO_RES


def test_clasificar_descarta_proyectos():
    assert _clasificar(_CLAS_RES, "Proyecto de Resolución “Por la cual se adicionan incisos”") is None
    assert _clasificar(_CLAS_CIR, "Proyecto de Circular Externa la cual tiene como asunto") is None


def test_clasificar_descarta_otra_entidad_por_la_cabeza_del_titulo():
    assert _clasificar(_CLAS_RES, "Resolución 7356 de 2024 de la Comisión de Regulación de Comunicaciones, “Por la cual”") is None
    assert _clasificar(_CLAS_RES, "Resolución 0612 de 2024 del Ministerio de Comercio Industria y Turismo, “Por la cual”") is None
    assert _clasificar(_CLAS_RES, 'Resolución 862 de 2023 de la Dirección de Regulación del Ministerio de Comercio, "Por la cual"') is None
    assert _clasificar(_CLAS_CIR, "Circular Externa 1 de 2023 - De la Agencia Nacional de Defensa Jurídica del Estado, “Lineamientos”") is None


def test_clasificar_no_descarta_sic_que_cita_un_ministerio_en_su_epigrafe():
    assert _clasificar(_CLAS_RES, 'Resolución No. 1111 del 24 de enero de 2025 "Por medio de la cual se fija la tasa del Ministerio de Comercio"') == _TIPO_RES
    assert _clasificar(_CLAS_RES, 'Resolución No 122 de 2025 de la Superintendencia de Industria y Comercio, "Por la cual"') == _TIPO_RES
    assert _clasificar(_CLAS_RES, "Resolución 1059 por la cual se reglamenta lo del Ministerio") == _TIPO_RES


def test_clasificar_titulos_circular_unica():
    assert _clasificar(_CLAS_TCU, "Título X - Actualizado el 30 de enero de 2026.") == _TIPO_TCU
    assert _clasificar(_CLAS_TCU, 'Resolución No. 62932 de 2025 "Por la cual se adiciona"') == _TIPO_RES


def test_clasificar_doctrina():
    assert _clasificar(_CLAS_DOC, "Concepto 15-159447 del 25 de agosto de 2015") == _TIPO_CTO
    assert _clasificar(_CLAS_DOC, "RELATORÍA RESOLUCIÓN 27305 - 10-07-2019 - CONCONCRETO") == _TIPO_REL
    assert _clasificar(_CLAS_DOC, "Resolución No. 3839 del 4 de febrero de 2015") == _TIPO_RES
    for otro in (
        "Sentencia Expediente Radicación 2007 00102 02 del 16 de febrero de 2017 Consejo Estado",
        "Radicado No. 2016-01884-01 del 12 de octubre de 2016 Consejo Superior de la Judicatura",
        "Informe de gestión 2016", "Acta 3 de 2016", "Estudio de mercado", "Auto 123",
    ):
        assert _clasificar(_CLAS_DOC, otro) is None, otro


def test_titulo_resolucion():
    assert _titulo(_TIPO_RES, 'Resolución No. 77121 del 29 de septiembre de 2026 "Por la cual"', "2026-09-29") == ("R_SIC_77121_2026", False)
    assert _titulo(_TIPO_RES, "RESOLUCIÓN 000610 DE 13 DE ABRIL DE 2026", "2026-04-13") == ("R_SIC_0610_2026", False)
    assert _titulo(_TIPO_RES, "Resolución Número 122 de 2025", "2025-01-10") == ("R_SIC_0122_2025", False)
    assert _titulo(_TIPO_RES, "Resolución N° 4.231 de 2024", "2024-02-22") == ("R_SIC_4231_2024", False)


def test_titulo_circular_todas_con_c():
    assert _titulo(_TIPO_CIR, "Circular Externa No 4 de 2024 de la Superintendencia", "2024-05-02") == ("C_SIC_0004_2024", False)
    assert _titulo(_TIPO_CIR, "Circular Interna No. 006 del 17 de marzo de 2025", "2025-03-17") == ("C_SIC_0006_2025", False)
    assert _titulo(_TIPO_CIR, "Circular Conjunta 010 de 2026", "2026-02-08") == ("C_SIC_0010_2026", False)
    assert _titulo(_TIPO_CIR, "Circular 011 de 2020", "2020-07-01") == ("C_SIC_0011_2020", False)
    assert _titulo(_TIPO_CIR, "Circular Externa 001 del 2026", "2026-01-15") == ("C_SIC_0001_2026", False)


def test_titulo_circular_sin_numero_queda_sin_verificar():
    assert _titulo(_TIPO_CIR, "Circular Única de Calidad Turística", "2026-02-06") == ("Circular Única de Calidad Turística", True)


def test_titulo_circular_unica_romano_y_fecha_de_version():
    assert _titulo(_TIPO_TCU, "Título X - Actualizado el 30 de enero de 2026.", "2026-01-30") == ("TCU_SIC_X_20260130", False)
    assert _titulo(_TIPO_TCU, "TÍTULO II", "2021-03-23") == ("TCU_SIC_II_20210323", False)
    assert _titulo(_TIPO_TCU, "Titulo I.", "2022-09-29") == ("TCU_SIC_I_20220929", False)
    assert _titulo(_TIPO_TCU, "Título X Propiedad Industrial", "2022-01-17") == ("TCU_SIC_X_20220117", False)


def test_titulo_concepto_radicado():
    assert _titulo(_TIPO_CTO, "Concepto 15-159447 del 25 de agosto de 2015", "2015-08-25") == ("CTO_SIC_15-159447", False)
    assert _titulo(_TIPO_CTO, "Concepto 17 49443 del 28 de marzo de 2017", "2017-03-28") == ("CTO_SIC_17-49443", False)
    assert _titulo(_TIPO_CTO, "Concepto sobre publicidad", "2016-01-01") == ("Concepto sobre publicidad", True)


def test_titulo_relatoria():
    assert _titulo(_TIPO_REL, "RELATORÍA RESOLUCIÓN 27305 - 10-07-2019 - CONCONCRETO", "2019-07-10") == ("REL_SIC_27305_2019", False)
    assert _titulo(_TIPO_REL, "RELATORÍA RESOLUCIÓN 56158 DEL 31-08-2021 - RESUELVE RECURSO - ASE", "2021-08-31") == ("REL_SIC_56158_2021", False)


def test_crudo_y_safe_title():
    assert _crudo("  ") == "documento"
    assert _crudo("x" * 200) == "x" * 120
    assert _crudo("Título final. ") == "Título final"
    assert _safe_title('Resolución "X": a/b') == "Resolución -X-- a-b"
