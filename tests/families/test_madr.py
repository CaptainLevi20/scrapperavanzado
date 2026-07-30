from core.scrapers.registry import FAMILY_REGISTRY
from core.scrapers.families.madr import ScrapMADR, _normalize_title, _parse_fecha, _resto_tras_numero


def test_resto_tras_numero_strips_everything_up_to_and_including_the_number():
    assert _resto_tras_numero("DECRETO 0765 DEL 15 DE JULIO DEL 2026", "0765") == " DEL 15 DE JULIO DEL 2026"


def test_resto_tras_numero_avoids_reading_the_act_number_as_a_day():
    # Sin este recorte, "21" (los últimos dos dígitos de "2321") se leería
    # como un día válido y produciría "2023-09-21" en vez de "2023-09-01".
    assert _resto_tras_numero("LEY 2321 DE SEPTIEMBRE DE 2023", "2321") == " DE SEPTIEMBRE DE 2023"


def test_resto_tras_numero_returns_full_text_when_number_not_found():
    assert _resto_tras_numero("Documento sin número reconocible", "9999") == "Documento sin número reconocible"


def test_normalize_title_builds_canonical_code():
    assert _normalize_title("D", "765", "2026") == "D_MADR_0765_2026"


def test_normalize_title_pads_short_numbers_to_four_digits():
    assert _normalize_title("R", "179", "2026") == "R_MADR_0179_2026"


def test_normalize_title_uses_conpes_literal_instead_of_a_single_letter():
    assert _normalize_title("CONPES", "4076", "2022") == "CONPES_MADR_4076_2022"


def test_parse_fecha_dia_de_mes_del_anio():
    assert _parse_fecha(" DEL 15 DE JULIO DEL 2026") == "2026-07-15"


def test_parse_fecha_dia_mes_sin_conector_de():
    # Variante real sin "DE" entre día y mes: "DEL 27 JULIO DE 2026".
    assert _parse_fecha(" DEL 27 JULIO DE 2026") == "2026-07-27"


def test_parse_fecha_mes_dia_anio_orden_invertido():
    # Variante real con mes antes del día: "DE MAYO 4 DE 2026".
    assert _parse_fecha(" DE MAYO 4 DE 2026") == "2026-05-04"


def test_parse_fecha_mes_anio_sin_dia():
    assert _parse_fecha(" DE OCTUBRE DE 2023") == "2023-10-01"


def test_parse_fecha_solo_anio():
    assert _parse_fecha(" DE 2023") == "2023-01-01"


def test_parse_fecha_conpes_siempre_solo_anio():
    assert _parse_fecha(" DE 2022") == "2022-01-01"


def test_parse_fecha_returns_none_when_no_date_found():
    assert _parse_fecha("texto sin fecha reconocible") is None


def test_parse_fecha_is_case_insensitive():
    assert _parse_fecha(" del 19 de mayo de 2023") == "2023-05-19"


def test_parse_fecha_does_not_misread_trailing_act_number_digits_as_a_day():
    # Regresión del caso documentado en _resto_tras_numero: si a _parse_fecha
    # se le pasara el título completo en vez del resto ya recortado, "21" (de
    # "2321") se leería como día. Aquí se prueba directamente sobre el resto
    # ya recortado, que es como _extraer_articulos debe invocarlo siempre.
    resto = _resto_tras_numero("LEY 2321 DE SEPTIEMBRE DE 2023", "2321")
    assert _parse_fecha(resto) == "2023-09-01"


def test_madr_is_registered_under_its_family_key():
    import core.scrapers.families  # noqa: F401

    assert FAMILY_REGISTRY["madr"].__name__ == "ScrapMADR"


_ARTICULO_DECRETO_HTML = """
<div class="cnt_normas container-fluid p-0">
<article class="col-12 pb-5 item_norm"
    data-title="DECRETO 0765 DEL 15 DE JULIO DEL 2026"
    data-info="&quot;Por el cual se adicionan los decretos 1071 del 2015&quot;"
    data-year="2026"
    data-number="0765"
    data-link="t3://file?uid=14012"
    data-content="">
    <div class="cnt_item_norm">
        <h3>
            <a itemprop="url" href="/fileadmin/normatividad/decretos/DECRETO_No._0765_DEL_15_DE_JULIO_DE_2026.pdf">
                <span itemprop="headline">DECRETO 0765 DEL 15 DE JULIO DEL 2026</span>
            </a>
        </h3>
    </div>
</article>
</div>
"""


def test_extraer_articulos_parses_article_and_builds_canonical_title():
    scraper = ScrapMADR()
    docs = scraper._extraer_articulos(_ARTICULO_DECRETO_HTML, "Decreto", "D", "2026-01-01", "2026-12-31")

    assert len(docs) == 1
    doc = docs[0]
    assert doc.title == "D_MADR_0765_2026"
    assert doc.title_unverified is False
    assert doc.tipo == "Decreto"
    assert doc.f_public == "2026-07-15"
    assert doc.f_providencia is None
    assert doc.detalle == "Por el cual se adicionan los decretos 1071 del 2015"
    assert doc.link["url"] == (
        "https://www.minagricultura.gov.co/fileadmin/normatividad/decretos/"
        "DECRETO_No._0765_DEL_15_DE_JULIO_DE_2026.pdf"
    )
    assert doc.save_path == "Ministerio de Agricultura y Desarrollo Rural/2026-07-15/Decreto/D_MADR_0765_2026(extension)"


def test_extraer_articulos_filters_out_of_range_dates():
    scraper = ScrapMADR()
    docs = scraper._extraer_articulos(_ARTICULO_DECRETO_HTML, "Decreto", "D", "2020-01-01", "2020-12-31")

    assert docs == []


_ARTICULO_CONPES_SIN_DIA_HTML = """
<article class="col-12 pb-5 item_norm"
    data-title="CONPES 4076 DE 2022"
    data-info="Política Pública de equidad de género para las mujeres."
    data-year="2022"
    data-number="4076"
    data-link="t3://file?uid=281"
    data-content="">
    <div class="cnt_item_norm">
        <h3>
            <a itemprop="url" href="/fileadmin/normatividad/conpes/CONPES_4076_DE_2022.pdf">
                <span itemprop="headline">CONPES 4076 DE 2022</span>
            </a>
        </h3>
    </div>
</article>
"""


def test_extraer_articulos_conpes_uses_year_only_and_conpes_literal():
    scraper = ScrapMADR()
    docs = scraper._extraer_articulos(_ARTICULO_CONPES_SIN_DIA_HTML, "Conpes", "CONPES", "2022-01-01", "2022-12-31")

    assert len(docs) == 1
    doc = docs[0]
    assert doc.title == "CONPES_MADR_4076_2022"
    assert doc.f_public == "2022-01-01"


def test_extraer_articulos_marks_title_unverified_when_no_data_number():
    html = _ARTICULO_DECRETO_HTML.replace('data-number="0765"', 'data-number=""')
    scraper = ScrapMADR()
    docs = scraper._extraer_articulos(html, "Decreto", "D", "2026-01-01", "2026-12-31")

    assert len(docs) == 1
    assert docs[0].title == "DECRETO 0765 DEL 15 DE JULIO DEL 2026"
    assert docs[0].title_unverified is True


def test_extraer_articulos_sanitizes_title_unverified_for_save_path():
    html = _ARTICULO_DECRETO_HTML.replace('data-number="0765"', 'data-number=""').replace(
        'data-title="DECRETO 0765 DEL 15 DE JULIO DEL 2026"',
        'data-title="Documento/con &quot;caracteres&quot;: raros|del 15 de julio de 2026"',
    ).replace(
        '<span itemprop="headline">DECRETO 0765 DEL 15 DE JULIO DEL 2026</span>',
        '<span itemprop="headline">Documento/con "caracteres": raros|del 15 de julio de 2026</span>',
    )
    scraper = ScrapMADR()
    docs = scraper._extraer_articulos(html, "Decreto", "D", "2026-01-01", "2026-12-31")

    assert len(docs) == 1
    doc = docs[0]
    assert doc.title_unverified is True
    segmentos = doc.save_path.split("/")
    assert len(segmentos) == 4
    ultimo_segmento = segmentos[-1]
    assert not any(c in ultimo_segmento for c in '\\/*?:"<>|')


def test_extraer_articulos_skips_article_without_download_link():
    html = _ARTICULO_DECRETO_HTML.replace(
        '<a itemprop="url" href="/fileadmin/normatividad/decretos/DECRETO_No._0765_DEL_15_DE_JULIO_DE_2026.pdf">',
        '<a>',
    )
    scraper = ScrapMADR()
    docs = scraper._extraer_articulos(html, "Decreto", "D", "2026-01-01", "2026-12-31")

    assert docs == []


def test_extraer_articulos_skips_article_without_any_parseable_date():
    html = _ARTICULO_DECRETO_HTML.replace(
        'data-title="DECRETO 0765 DEL 15 DE JULIO DEL 2026"',
        'data-title="DECRETO SIN FECHA RECONOCIBLE"',
    ).replace(
        '<span itemprop="headline">DECRETO 0765 DEL 15 DE JULIO DEL 2026</span>',
        '<span itemprop="headline">DECRETO SIN FECHA RECONOCIBLE</span>',
    )
    scraper = ScrapMADR()
    docs = scraper._extraer_articulos(html, "Decreto", "D", "2026-01-01", "2026-12-31")

    assert docs == []
