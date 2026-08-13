import responses
from responses import matchers

from core.scrapers.registry import FAMILY_REGISTRY
from core.scrapers.families.minambiente import (
    ScrapMinAmbiente,
    _normalize_title,
    _parse_fecha,
    _parse_fecha_concepto,
    _parse_publicado,
    _resto_tras_numero,
)

_AJAX_URL = "https://www.minambiente.gov.co/wp-admin/admin-ajax.php"


def test_resto_tras_numero_strips_everything_up_to_and_including_the_number():
    assert _resto_tras_numero("Decreto 0766 del 15 julio de 2026", "0766") == " del 15 julio de 2026"


def test_resto_tras_numero_returns_full_text_when_number_not_found():
    assert _resto_tras_numero("Documento sin número reconocible", "9999") == "Documento sin número reconocible"


def test_normalize_title_builds_canonical_code():
    assert _normalize_title("D", "766", "2026") == "D_MADS_0766_2026"


def test_normalize_title_pads_short_numbers_to_four_digits():
    assert _normalize_title("A", "127", "2026") == "A_MADS_0127_2026"


def test_normalize_title_uses_conpes_literal_instead_of_a_single_letter():
    assert _normalize_title("CONPES", "4088", "2022") == "CONPES_MADS_4088_2022"


def test_normalize_title_circular_uses_the_radicado_code_as_is():
    # El código de Circular no es un entero corto (mezcla dígitos y letras),
    # así que no se le aplica int()/zfill como al resto de categorías.
    assert _normalize_title("C", "10002026E4000041", "2026") == "C_MADS_10002026E4000041_2026"


def test_parse_fecha_dia_de_mes_del_anio():
    assert _parse_fecha(" del 15 julio de 2026") == "2026-07-15"


def test_parse_fecha_dia_mes_del_anio_con_de_intermedio():
    # Real: "Decreto 1248 de 26 de julio del 2023"
    assert _parse_fecha(" de 26 de julio del 2023") == "2023-07-26"


def test_parse_fecha_mes_anio_sin_dia():
    assert _parse_fecha(" de octubre de 2024") == "2024-10-01"


def test_parse_fecha_solo_anio():
    assert _parse_fecha(" de 2023") == "2023-01-01"


def test_parse_fecha_returns_none_when_no_date_found():
    assert _parse_fecha("texto sin fecha reconocible") is None


def test_parse_fecha_falls_back_to_month_start_on_calendar_impossible_date():
    assert _parse_fecha(" del 31 de abril de 2024") == "2024-04-01"


def test_parse_publicado_parses_spanish_month_day_year():
    assert _parse_publicado("Publicado: agosto 11, 2026") == "2026-08-11"


def test_parse_publicado_returns_none_when_absent():
    assert _parse_publicado("sin fecha aquí") is None


def test_parse_fecha_concepto_parses_dd_mm_yyyy():
    assert _parse_fecha_concepto("12/08/2025") == "2025-08-12"


def test_parse_fecha_concepto_returns_none_for_invalid_calendar_date():
    assert _parse_fecha_concepto("31/02/2025") is None


def test_minambiente_is_registered_under_its_family_key():
    import core.scrapers.families  # noqa: F401

    assert FAMILY_REGISTRY["minambiente"].__name__ == "ScrapMinAmbiente"


_BOX_DECRETO_HTML = """
<div class="row box-docgd">
  <div class="col-md-2">
    <div class="box-archivo">
      <a class="url-archivo" href="https://www.minambiente.gov.co/wp-content/uploads/2026/07/DECRETO-0766.pdf"></a>
    </div>
  </div>
  <div class="col-md-10">
    <div><a class="documento-normativa" target="_blank"
         href="https://www.minambiente.gov.co/wp-content/uploads/2026/07/DECRETO-0766.pdf"
         title="Decreto 0766 del 15 julio de 2026">Decreto 0766 del 15 julio de 2026</a></div>
    <div><p class="descripcion-archivo">"Por el cual se reglamenta el uso del recurso hídrico"</p></div>
    <div><span class="txt-peque-archivo">Publicado: julio 16, 2026</span></div>
  </div>
</div>
"""


def test_extraer_normas_parses_block_and_builds_canonical_title():
    scraper = ScrapMinAmbiente()
    docs = scraper._extraer_normas(_BOX_DECRETO_HTML, "Decreto", "D", "2026-01-01", "2026-12-31")

    assert len(docs) == 1
    doc = docs[0]
    assert doc.title == "D_MADS_0766_2026"
    assert doc.title_unverified is False
    assert doc.tipo == "Decreto"
    assert doc.f_providencia == "2026-07-15"
    assert doc.f_public == "2026-07-16"
    assert doc.detalle == "Por el cual se reglamenta el uso del recurso hídrico"


# Estructura real del sitio (confirmada con fetch contra minambiente.gov.co):
# hay DOS <span class="txt-peque-archivo"> por bloque — el primero, dentro de
# .box-archivo, es el peso del archivo (casi siempre vacío); el que trae
# "Publicado: ..." está más abajo. Regresión: bloque.find() con solo el
# selector de clase se quedaba con el primero (vacío).
_BOX_RESOLUCION_CON_SPAN_VACIO_HTML = """
<div class="row box-docgd">
  <div class="col-md-1">
    <div class="box-archivo">
      <a class="url-archivo" href="https://www.minambiente.gov.co/wp-content/uploads/2026/08/RES-0970.zip"></a>
      <span class="peso-archivo txt-peque-archivo"></span>
    </div>
  </div>
  <div class="col-md-11">
    <div><a class="documento-normativa"
         href="https://www.minambiente.gov.co/wp-content/uploads/2026/08/RES-0970.zip"
         title="Resolución 0970 de 2026">Resolución 0970 de 2026</a></div>
    <div><p class="descripcion-archivo">"Por medio de la cual se modifica la Resolución 0221 de 2025"</p></div>
    <div><span class="txt-peque-archivo">Publicado: agosto 5, 2026</span></div>
  </div>
</div>
"""


def test_extraer_normas_skips_empty_leading_span_to_find_publicado():
    scraper = ScrapMinAmbiente()
    docs = scraper._extraer_normas(_BOX_RESOLUCION_CON_SPAN_VACIO_HTML, "Resolución", "R", "2026-01-01", "2026-12-31")

    assert len(docs) == 1
    assert docs[0].f_public == "2026-08-05"
    assert docs[0].f_providencia == "2026-01-01"  # el título no trae día/mes, solo año


def test_extraer_normas_filters_by_providencia_not_publicado():
    # f_providencia (15 jul 2026) queda fuera del rango pedido aunque
    # f_public (16 jul 2026, un día después) sí caería dentro de un rango
    # que solo incluyera el 16 — confirma que el filtro usa f_providencia.
    scraper = ScrapMinAmbiente()
    docs = scraper._extraer_normas(_BOX_DECRETO_HTML, "Decreto", "D", "2026-07-16", "2026-07-16")

    assert docs == []


def test_extraer_normas_marks_title_unverified_when_no_number_found():
    html = _BOX_DECRETO_HTML.replace(
        'title="Decreto 0766 del 15 julio de 2026">Decreto 0766 del 15 julio de 2026</a>',
        'title="Circular de medidas y recomendaciones">Circular de medidas y recomendaciones</a>',
    )
    scraper = ScrapMinAmbiente()
    docs = scraper._extraer_normas(html, "Circular", "C", "2020-01-01", "2030-12-31")

    assert docs == []  # sin número y sin fecha reconocible en el título -> sin fecha para filtrar, se omite


_BOX_RESOLUCION_RUIDO_HTML = """
<div class="row box-docgd">
  <div class="col-md-10">
    <div><a class="documento-normativa" href="https://www.minambiente.gov.co/wp-content/uploads/2021/09/RES-0953.pdf"
         title="Actualizada &#8211; Res 0953 del 03 de Septiembre de 2021">Actualizada &#8211; Res 0953 del 03 de Septiembre de 2021</a></div>
    <div><span class="txt-peque-archivo">Publicado: septiembre 4, 2021</span></div>
  </div>
</div>
"""


def test_extraer_normas_finds_first_digit_run_despite_leading_noise():
    scraper = ScrapMinAmbiente()
    docs = scraper._extraer_normas(_BOX_RESOLUCION_RUIDO_HTML, "Resolución", "R", "2021-01-01", "2021-12-31")

    assert len(docs) == 1
    assert docs[0].title == "R_MADS_0953_2021"
    assert docs[0].f_providencia == "2021-09-03"


_BOX_LEY_SOLO_ANIO_HTML = """
<div class="row box-docgd">
  <div class="col-md-10">
    <div><a class="documento-normativa" href="https://www.minambiente.gov.co/wp-content/uploads/2023/01/LEY-2294.pdf"
         title="Ley 2294 de 2023">Ley 2294 de 2023</a></div>
    <div><span class="txt-peque-archivo">Publicado: enero 5, 2023</span></div>
  </div>
</div>
"""


def test_extraer_normas_year_only_falls_back_to_january_first():
    scraper = ScrapMinAmbiente()
    docs = scraper._extraer_normas(_BOX_LEY_SOLO_ANIO_HTML, "Ley", "L", "2023-01-01", "2023-12-31")

    assert len(docs) == 1
    assert docs[0].title == "L_MADS_2294_2023"
    assert docs[0].f_providencia == "2023-01-01"


_BOX_CONPES_HTML = """
<div class="row box-docgd">
  <div class="col-md-10">
    <div><a class="documento-normativa" href="https://www.minambiente.gov.co/wp-content/uploads/2022/01/CONPES-4088.pdf"
         title="Conpes 4088 de 2022">Conpes 4088 de 2022</a></div>
    <div><span class="txt-peque-archivo">Publicado: enero 10, 2022</span></div>
  </div>
</div>
"""


def test_extraer_normas_conpes_uses_conpes_literal():
    scraper = ScrapMinAmbiente()
    docs = scraper._extraer_normas(_BOX_CONPES_HTML, "Conpes", "CONPES", "2022-01-01", "2022-12-31")

    assert len(docs) == 1
    assert docs[0].title == "CONPES_MADS_4088_2022"


_BOX_CIRCULAR_CON_CODIGO_HTML = """
<div class="row box-docgd">
  <div class="col-md-10">
    <div><a class="documento-normativa" href="https://www.minambiente.gov.co/wp-content/uploads/2026/07/CIRC-10002026E4000041.pdf"
         title="Circular 10002026E4000041 del 23 de julio de 2026">Circular 10002026E4000041 del 23 de julio de 2026</a></div>
    <div><span class="txt-peque-archivo">Publicado: julio 24, 2026</span></div>
  </div>
</div>
"""


def test_extraer_normas_circular_uses_radicado_code_not_first_digit_run():
    scraper = ScrapMinAmbiente()
    docs = scraper._extraer_normas(_BOX_CIRCULAR_CON_CODIGO_HTML, "Circular", "C", "2026-01-01", "2026-12-31")

    assert len(docs) == 1
    doc = docs[0]
    assert doc.title == "C_MADS_10002026E4000041_2026"
    assert doc.title_unverified is False
    assert doc.f_providencia == "2026-07-23"


_BOX_CIRCULAR_SIN_CODIGO_HTML = """
<div class="row box-docgd">
  <div class="col-md-10">
    <div><a class="documento-normativa" href="https://www.minambiente.gov.co/wp-content/uploads/2022/01/CIRC-NIRO.pdf"
         title="Circular de medidas y recomendaciones frente al fenómeno de El Niño">Circular de medidas y recomendaciones frente al fenómeno de El Niño</a></div>
  </div>
</div>
"""


def test_extraer_normas_circular_without_code_or_date_is_dropped():
    scraper = ScrapMinAmbiente()
    docs = scraper._extraer_normas(_BOX_CIRCULAR_SIN_CODIGO_HTML, "Circular", "C", "2000-01-01", "2030-12-31")

    assert docs == []


_CONCEPTOS_HTML = """
<div class="row box-docgd">
  <div class="col-md-11">
    <div><a class="documento-normativa" href="https://www.minambiente.gov.co/wp-content/uploads/2025/08/Conceptos-CSV.csv"
         title="Conceptos 2025">Conceptos 2025</a></div>
    <div><p class="descripcion-archivo"><table class="table table-bordered">
      <tbody>
        <tr><td>N°</td><td>Fecha</td><td>Rad. Salida</td><td>Tema</td><td>Descarga</td></tr>
        <tr>
          <td>178</td>
          <td>12/08/2025</td>
          <td>concep_028506</td>
          <td>Cesion Permisos De Emision</td>
          <td><a href="https://www.minambiente.gov.co/wp-content/uploads/2025/08/concep_250812_028506.pdf">concep_250812_028506</a></td>
        </tr>
        <tr>
          <td>177</td>
          <td>31/02/2025</td>
          <td>concep_028271</td>
          <td>Fecha invalida, se descarta</td>
          <td><a href="https://www.minambiente.gov.co/wp-content/uploads/2025/08/concep_bad.pdf">x</a></td>
        </tr>
      </tbody>
    </table></p></div>
  </div>
</div>
"""


def test_extraer_conceptos_parses_table_rows_and_ignores_top_level_csv_link():
    scraper = ScrapMinAmbiente()
    docs = scraper._extraer_conceptos(_CONCEPTOS_HTML, "2025-01-01", "2025-12-31")

    assert len(docs) == 1
    doc = docs[0]
    assert doc.title == "CONCEPTO_MADS_concep_028506"
    assert doc.tipo == "Concepto"
    assert doc.f_providencia == "2025-08-12"
    assert doc.f_public == "2025-08-12"  # duplicado: Conceptos solo tiene una fecha real
    assert doc.detalle == "Cesion Permisos De Emision"
    assert doc.link["url"] == (
        "https://www.minambiente.gov.co/wp-content/uploads/2025/08/concep_250812_028506.pdf"
    )
    assert "Conceptos-CSV" not in doc.link["url"]


_CONCEPTOS_ANIO_VACIO_HTML = """
<div class="card conceptos2026">
  <div id="paginar-varios" class="mads-paginacion_container_normativa_9621049">
    <div class="cvf-pagination-content">
      <style>.card.conceptos2026{display:none;}</style>
    </div>
  </div>
</div>
"""


def test_extraer_conceptos_empty_year_placeholder_produces_no_documents():
    scraper = ScrapMinAmbiente()
    docs = scraper._extraer_conceptos(_CONCEPTOS_ANIO_VACIO_HTML, "2020-01-01", "2030-12-31")

    assert docs == []


def _matcher(term_id: int):
    return matchers.urlencoded_params_matcher(
        {"page": "1", "area1": str(term_id), "action": "normativa_paginacion-load-posts-2"}
    )


@responses.activate
def test_scrap_aggregates_across_categories_and_conceptos():
    responses.add(responses.POST, _AJAX_URL, body=_BOX_DECRETO_HTML, match=[_matcher(48)])
    responses.add(responses.POST, _AJAX_URL, body=_BOX_LEY_SOLO_ANIO_HTML, match=[_matcher(47)])
    responses.add(responses.POST, _AJAX_URL, body="", match=[_matcher(46)])
    responses.add(responses.POST, _AJAX_URL, body="", match=[_matcher(58)])
    responses.add(responses.POST, _AJAX_URL, body=_BOX_CONPES_HTML, match=[_matcher(61)])
    responses.add(responses.POST, _AJAX_URL, body=_BOX_CIRCULAR_CON_CODIGO_HTML, match=[_matcher(60)])
    responses.add(responses.POST, _AJAX_URL, body=_CONCEPTOS_HTML, match=[_matcher(962)])

    scraper = ScrapMinAmbiente()
    docs = scraper.scrap(fini="2020-01-01", ffin="2026-12-31")

    assert {d.title for d in docs} == {
        "D_MADS_0766_2026",
        "L_MADS_2294_2023",
        "CONPES_MADS_4088_2022",
        "C_MADS_10002026E4000041_2026",
        "CONCEPTO_MADS_concep_028506",
    }


@responses.activate
def test_scrap_continues_past_a_failing_category():
    responses.add(responses.POST, _AJAX_URL, status=500, match=[_matcher(48)])
    responses.add(responses.POST, _AJAX_URL, body=_BOX_LEY_SOLO_ANIO_HTML, match=[_matcher(47)])
    responses.add(responses.POST, _AJAX_URL, body="", match=[_matcher(46)])
    responses.add(responses.POST, _AJAX_URL, body="", match=[_matcher(58)])
    responses.add(responses.POST, _AJAX_URL, body=_BOX_CONPES_HTML, match=[_matcher(61)])
    responses.add(responses.POST, _AJAX_URL, body=_BOX_CIRCULAR_CON_CODIGO_HTML, match=[_matcher(60)])
    responses.add(responses.POST, _AJAX_URL, body=_CONCEPTOS_HTML, match=[_matcher(962)])

    progreso = []
    scraper = ScrapMinAmbiente()
    docs = scraper.scrap(fini="2020-01-01", ffin="2026-12-31", on_progress=progreso.append)

    assert "D_MADS_0766_2026" not in {d.title for d in docs}
    assert {d.title for d in docs} == {
        "L_MADS_2294_2023",
        "CONPES_MADS_4088_2022",
        "C_MADS_10002026E4000041_2026",
        "CONCEPTO_MADS_concep_028506",
    }
    assert any("Error" in m and "Decreto" in m for m in progreso)


@responses.activate
def test_scrap_respects_limit():
    responses.add(responses.POST, _AJAX_URL, body=_BOX_DECRETO_HTML, match=[_matcher(48)])
    responses.add(responses.POST, _AJAX_URL, body=_BOX_LEY_SOLO_ANIO_HTML, match=[_matcher(47)])
    responses.add(responses.POST, _AJAX_URL, body="", match=[_matcher(46)])
    responses.add(responses.POST, _AJAX_URL, body="", match=[_matcher(58)])
    responses.add(responses.POST, _AJAX_URL, body=_BOX_CONPES_HTML, match=[_matcher(61)])
    responses.add(responses.POST, _AJAX_URL, body=_BOX_CIRCULAR_CON_CODIGO_HTML, match=[_matcher(60)])
    responses.add(responses.POST, _AJAX_URL, body=_CONCEPTOS_HTML, match=[_matcher(962)])

    scraper = ScrapMinAmbiente()
    docs = scraper.scrap(fini="2020-01-01", ffin="2026-12-31", limit=1)

    assert len(docs) == 1


def test_filters_by_publication_date_stays_at_default_false():
    assert ScrapMinAmbiente.filters_by_publication_date is False


def test_doc_id_uses_publication_date_is_disabled():
    # "Publicado:" puede re-timestampear el mismo archivo por reindexado del
    # CMS del sitio — el doc_id no debe depender de ese campo o un reindexado
    # duplicaría el documento en la base de datos.
    assert ScrapMinAmbiente.doc_id_uses_publication_date is False


def test_extraer_normas_falls_back_to_providencia_when_publicado_field_is_missing():
    html = _BOX_DECRETO_HTML.replace(
        '<div><span class="txt-peque-archivo">Publicado: julio 16, 2026</span></div>', ""
    )
    scraper = ScrapMinAmbiente()
    docs = scraper._extraer_normas(html, "Decreto", "D", "2026-01-01", "2026-12-31")

    assert len(docs) == 1
    assert docs[0].f_public == "2026-07-15"
    assert docs[0].f_providencia == "2026-07-15"
