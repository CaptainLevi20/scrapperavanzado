import responses

from core.scrapers.families.mindeporte import (
    ScrapMinDeporte,
    _anos_enlazados,
    _extraer_articulos,
    _normalize_title,
    _parse_fecha,
    _resto_tras_numero,
    _tiene_pagina_siguiente,
)
from core.scrapers.registry import FAMILY_REGISTRY


def test_mindeporte_is_registered_under_its_family_key():
    import core.scrapers.families  # noqa: F401

    assert FAMILY_REGISTRY["mindeporte"].__name__ == "ScrapMinDeporte"


# --- _resto_tras_numero / _normalize_title -------------------------------

def test_resto_tras_numero_strips_up_to_and_including_the_number():
    assert _resto_tras_numero("Resolución 000634 del 22 de agosto de 2025", "000634") == " del 22 de agosto de 2025"


def test_resto_tras_numero_returns_full_text_when_number_not_found():
    assert _resto_tras_numero("Documento sin número", "9999") == "Documento sin número"


def test_normalize_title_builds_canonical_code():
    assert _normalize_title("R", "634", "2025") == "R_MDEPORTE_0634_2025"


def test_normalize_title_pads_short_numbers_to_four_digits():
    assert _normalize_title("D", "6", "1996") == "D_MDEPORTE_0006_1996"


def test_normalize_title_uses_conpes_literal_instead_of_a_single_letter():
    assert _normalize_title("CONPES", "3248", "2003") == "CONPES_MDEPORTE_3248_2003"


# --- _parse_fecha: 5 niveles de cascada ------------------------------------

def test_parse_fecha_dia_de_mes_de_anio():
    assert _parse_fecha(" del 22 de agosto de 2025") == "2025-08-22"


def test_parse_fecha_dia_mes_sin_conector_de():
    assert _parse_fecha(" del 24 julio 2025") == "2025-07-24"


def test_parse_fecha_dia_mes_anio_sin_conector_antes_del_anio():
    # Real ejemplo (Circular 023): "15 de noviembre 2024" — sin "de"/"del"
    # entre el mes y el año, el único de los 4 niveles de madr que no cubre.
    assert _parse_fecha(": ... - 15 de noviembre 2024") == "2024-11-15"


def test_parse_fecha_mes_dia_anio_orden_invertido():
    assert _parse_fecha(" de mayo 4 de 2026") == "2026-05-04"


def test_parse_fecha_mes_anio_sin_dia():
    assert _parse_fecha(" de 2023") == "2023-01-01"  # "Decreto 1306 de 2023" -> resto tras numero: " de 2023"


def test_parse_fecha_solo_anio():
    assert _parse_fecha(" de 1996") == "1996-01-01"


def test_parse_fecha_returns_none_when_no_date_found():
    assert _parse_fecha("texto sin fecha reconocible") is None


def test_parse_fecha_is_case_insensitive():
    assert _parse_fecha(" DEL 22 DE AGOSTO DE 2025") == "2025-08-22"


def test_parse_fecha_falls_back_to_month_start_on_calendar_impossible_date():
    assert _parse_fecha(" del 31 de abril de 2024") == "2024-04-01"


def test_parse_fecha_ignores_trailing_free_text_after_full_date():
    # Real ejemplo: "Decreto 780 de 2016 Sector Salud y Protección Social"
    resto = _resto_tras_numero("Decreto 780 de 2016 Sector Salud y Protección Social", "780")
    assert _parse_fecha(resto) == "2016-01-01"


# --- _extraer_articulos: bloque real -------------------------------------

_ARTICULO_RESOLUCION_HTML = """
<div class="grid gap-4 grid-cols-1">
<article class="w-full overflow-hidden transition-colors border border-gray-200 shadow-sm bg-gray-50 rounded-xl">
    <div class="flex w-full gap-4 p-4">
        <div class="flex flex-col justify-center flex-1 min-w-0 gap-1">
            <a href="/transparencia-y-acceso-a-informacion-publica/2-normativa/2-1-normatividad/normatividad-general-y-reglamentaria/resoluciones/2025/resolucion-000634-del-22-de-agosto-de-2025"
                id="resolucion-000634-del-22-de-agosto-de-2025" target="" class="block visited:text-visited-gray">
                <p class="text-base font-semibold leading-tight break-words text-govco-dark-blue">
                    Resolución 000634 del 22 de agosto de 2025
                </p>
                <p class="mt-1 text-sm leading-tight text-gray-600"><p>&quot;Por la cual se conforma y adopta el Comité Institucional de Coordinación de Control Interno&quot;.</p></p>
                <p class="mt-1 text-xs text-gray-400">martes, marzo 24 de 2026</p>
            </a>
            <ul class="mt-2 ml-4 text-sm italic text-gray-600 list-disc">
                <li>
                    <a href="https://www.mindeporte.gov.co/files/a160c1e9/a160c2bb/Resolucion-000634-del-22-agosto-2025.pdf"
                        target="_blank" class="break-words hover:underline dark:text-slate-900">
                        Clic aquí para consultarla
                        <i class="pl-2 fas fa-file-pdf"></i>
                    </a>
                </li>
            </ul>
        </div>
    </div>
</article>
</div>
"""


def test_extraer_articulos_parses_resolucion_and_builds_canonical_title():
    docs = _extraer_articulos(
        _ARTICULO_RESOLUCION_HTML, "Resolución", "R", "2025-01-01", "2025-12-31", "Ministerio del Deporte"
    )

    assert len(docs) == 1
    doc = docs[0]
    assert doc.title == "R_MDEPORTE_0634_2025"
    assert doc.title_unverified is False
    assert doc.tipo == "Resolución"
    assert doc.f_public == "2025-08-22"
    assert doc.f_providencia == "2025-08-22"
    assert doc.detalle == "Por la cual se conforma y adopta el Comité Institucional de Coordinación de Control Interno."
    assert doc.link["url"] == "https://www.mindeporte.gov.co/files/a160c1e9/a160c2bb/Resolucion-000634-del-22-agosto-2025.pdf"
    assert doc.save_path == "Ministerio del Deporte/2025-08-22/Resolución/R_MDEPORTE_0634_2025(extension)"


def test_extraer_articulos_filters_out_of_range_dates():
    docs = _extraer_articulos(
        _ARTICULO_RESOLUCION_HTML, "Resolución", "R", "2020-01-01", "2020-12-31", "Ministerio del Deporte"
    )
    assert docs == []


_ARTICULO_DECRETO_SIN_DIA_HTML = """
<article class="w-full overflow-hidden">
    <div class="flex w-full gap-4 p-4">
        <div class="flex flex-col justify-center flex-1 min-w-0 gap-1">
            <a href="/.../normograma/decretos/decreto-1306-de-2023" id="decreto-1306-de-2023" target="" class="block">
                <p class="text-base font-semibold leading-tight break-words text-govco-dark-blue">
                    Decreto 1306 de 2023
                </p>
                <p class="mt-1 text-sm leading-tight text-gray-600"><p>&quot;Por el cual se modifican los artículos 2.9.2.3 y 2.9.4.4 del Decreto 1085 de 2015&quot;.</p></p>
                <p class="mt-1 text-xs text-gray-400">viernes, septiembre 29 de 2023</p>
            </a>
            <ul class="mt-2 ml-4 text-sm italic text-gray-600 list-disc">
                <li>
                    <a href="https://www.mindeporte.gov.co/files/a08e433a/a08e457a/DECRETO-1306-DEL-10-DE-AGOSTO-DE-2023.pdf" target="_blank">
                        DECRETO-1306-DEL-10-DE-AGOSTO-DE-2023.pdf
                    </a>
                </li>
            </ul>
        </div>
    </div>
</article>
"""


def test_extraer_articulos_decreto_without_day_uses_year_only():
    docs = _extraer_articulos(
        _ARTICULO_DECRETO_SIN_DIA_HTML, "Decreto", "D", "2023-01-01", "2023-12-31", "Ministerio del Deporte"
    )

    assert len(docs) == 1
    doc = docs[0]
    assert doc.title == "D_MDEPORTE_1306_2023"
    assert doc.f_public == "2023-01-01"
    # El "1085 de 2015" referenciado en el detalle no debe ganarle a la fecha
    # real del propio decreto (2023), que aparece primero en el título.
    assert doc.f_providencia == "2023-01-01"


_ARTICULO_CIRCULAR_CON_FECHA_HTML = """
<article class="w-full overflow-hidden">
    <div class="flex w-full gap-4 p-4">
        <div class="flex flex-col justify-center flex-1 min-w-0 gap-1">
            <a href="/.../normograma/circulares/circular-interna-no-031" id="circular-031" target="" class="block">
                <p class="text-base font-semibold leading-tight break-words text-govco-dark-blue">
                    Circular interna No. 031: Lineamientos en relación con la radicación de solicitudes de numeración de resoluciones ante la Oficina Asesora Jurídica del Ministerio del Deporte - 22 de diciembre de 2025
                </p>
                <p class="mt-1 text-xs text-gray-400">lunes, diciembre 29 de 2025</p>
            </a>
            <ul class="mt-2 ml-4 text-sm italic text-gray-600 list-disc">
                <li>
                    <a href="https://www.mindeporte.gov.co/files/a0b6/CIRCULAR-INTERNA-031-DEL-22-DE-DICIEMBRE-2025.pdf" target="_blank">
                        Clic aquí para consultarla
                    </a>
                </li>
            </ul>
        </div>
    </div>
</article>
"""


def test_extraer_articulos_circular_has_no_separate_detalle_and_parses_trailing_date():
    docs = _extraer_articulos(
        _ARTICULO_CIRCULAR_CON_FECHA_HTML, "Circular", "C", "2025-01-01", "2025-12-31", "Ministerio del Deporte"
    )

    assert len(docs) == 1
    doc = docs[0]
    assert doc.title == "C_MDEPORTE_0031_2025"
    assert doc.detalle is None
    assert doc.f_providencia == "2025-12-22"


_ARTICULO_CIRCULAR_SIN_FECHA_HTML = """
<article class="w-full overflow-hidden">
    <div class="flex w-full gap-4 p-4">
        <div class="flex flex-col justify-center flex-1 min-w-0 gap-1">
            <a href="/.../normograma/circulares/circular-interna-no-017" id="circular-017" target="" class="block">
                <p class="text-base font-semibold leading-tight break-words text-govco-dark-blue">
                    Circular interna No. 017: Lineamientos frente al reporte y actualización de la información en el Sistema e-KOGUI
                </p>
                <p class="mt-1 text-xs text-gray-400">lunes, enero 12 de 2026</p>
            </a>
            <ul class="mt-2 ml-4 text-sm italic text-gray-600 list-disc">
                <li>
                    <a href="https://www.mindeporte.gov.co/files/circular-017.pdf" target="_blank">Clic aquí para consultarla</a>
                </li>
            </ul>
        </div>
    </div>
</article>
"""


def test_extraer_articulos_discards_item_without_parseable_date():
    docs = _extraer_articulos(
        _ARTICULO_CIRCULAR_SIN_FECHA_HTML, "Circular", "C", "2000-01-01", "2026-12-31", "Ministerio del Deporte"
    )
    assert docs == []


_ARTICULO_DIRECTIVA_PRESIDENCIAL_HTML = """
<article class="w-full overflow-hidden">
    <div class="flex w-full gap-4 p-4">
        <div class="flex flex-col justify-center flex-1 min-w-0 gap-1">
            <a href="/.../normograma/directivas/directiva-presidencial-no-2" id="dir-2" target="" class="block">
                <p class="text-base font-semibold leading-tight break-words text-govco-dark-blue">
                    Directiva Presidencial No 2 del 2 de abril de 2019
                </p>
                <p class="mt-1 text-xs text-gray-400">martes, abril 9 de 2019</p>
            </a>
            <ul class="mt-2 ml-4 text-sm italic text-gray-600 list-disc">
                <li><a href="https://www.mindeporte.gov.co/files/directiva-2.pdf" target="_blank">Clic aquí</a></li>
            </ul>
        </div>
    </div>
</article>
"""


def test_extraer_articulos_directiva_presidencial_finds_number_after_prefix():
    docs = _extraer_articulos(
        _ARTICULO_DIRECTIVA_PRESIDENCIAL_HTML, "Directiva", "DIR", "2019-01-01", "2019-12-31", "Ministerio del Deporte"
    )

    assert len(docs) == 1
    doc = docs[0]
    assert doc.title == "DIR_MDEPORTE_0002_2019"
    assert doc.f_providencia == "2019-04-02"


_ARTICULO_ACUERDO_SIN_NO_HTML = """
<article class="w-full overflow-hidden">
    <div class="flex w-full gap-4 p-4">
        <div class="flex flex-col justify-center flex-1 min-w-0 gap-1">
            <a href="/.../normograma/acuerdos/acuerdo-6-de-1996" id="acuerdo-6" target="" class="block">
                <p class="text-base font-semibold leading-tight break-words text-govco-dark-blue">
                    Acuerdo 6 de 1996
                </p>
                <p class="mt-1 text-xs text-gray-400">lunes, enero 12 de 2026</p>
            </a>
            <ul class="mt-2 ml-4 text-sm italic text-gray-600 list-disc">
                <li><a href="https://www.mindeporte.gov.co/files/acuerdo-6.pdf" target="_blank">Clic aquí</a></li>
            </ul>
        </div>
    </div>
</article>
"""


def test_extraer_articulos_acuerdo_without_no_prefix():
    docs = _extraer_articulos(
        _ARTICULO_ACUERDO_SIN_NO_HTML, "Acuerdo", "A", "1996-01-01", "1996-12-31", "Ministerio del Deporte"
    )

    assert len(docs) == 1
    assert docs[0].title == "A_MDEPORTE_0006_1996"


_ARTICULO_SIN_ENLACE_HTML = """
<article class="w-full overflow-hidden">
    <div class="flex w-full gap-4 p-4">
        <div class="flex flex-col justify-center flex-1 min-w-0 gap-1">
            <a href="/.../resoluciones/2025/resolucion-000634" id="resolucion-000634" target="" class="block">
                <p class="text-base font-semibold leading-tight break-words text-govco-dark-blue">
                    Resolución 000634 del 22 de agosto de 2025
                </p>
            </a>
            <ul class="mt-2 ml-4 text-sm italic text-gray-600 list-disc"></ul>
        </div>
    </div>
</article>
"""


def test_extraer_articulos_skips_item_without_download_link():
    docs = _extraer_articulos(
        _ARTICULO_SIN_ENLACE_HTML, "Resolución", "R", "2025-01-01", "2025-12-31", "Ministerio del Deporte"
    )
    assert docs == []


# --- paginación: rel="next" y años enlazados -------------------------------

_PAGINA_CON_SIGUIENTE_HTML = """
<div>
    <a href="...?page=2" rel="next" aria-label="Next &raquo;">Siguiente</a>
</div>
"""

_PAGINA_SIN_SIGUIENTE_HTML = "<div>Mostrando 1 a 7 de 7 resultados</div>"


def test_tiene_pagina_siguiente_true_when_rel_next_present():
    assert _tiene_pagina_siguiente(_PAGINA_CON_SIGUIENTE_HTML) is True


def test_tiene_pagina_siguiente_false_when_absent():
    assert _tiene_pagina_siguiente(_PAGINA_SIN_SIGUIENTE_HTML) is False


_RESOLUCIONES_ROOT_HTML = """
<div>
    <a href="/transparencia-y-acceso-a-informacion-publica/2-normativa/2-1-normatividad/normatividad-general-y-reglamentaria/resoluciones/2015">2015</a>
    <a href="/transparencia-y-acceso-a-informacion-publica/2-normativa/2-1-normatividad/normatividad-general-y-reglamentaria/resoluciones/2024">2024</a>
    <a href="/transparencia-y-acceso-a-informacion-publica/2-normativa/2-1-normatividad/normatividad-general-y-reglamentaria/resoluciones/2025">2025</a>
    <a href="/transparencia-y-acceso-a-informacion-publica/2-normativa/2-1-normatividad/normatividad-general-y-reglamentaria/procesos-judiciales/2018">2018 (otra sección, no debe colarse)</a>
</div>
"""


def test_anos_enlazados_extracts_only_resoluciones_years():
    assert _anos_enlazados(_RESOLUCIONES_ROOT_HTML) == [2015, 2024, 2025]


# --- scrap(): flujo completo con responses ---------------------------------

_BASE = "https://www.mindeporte.gov.co"
_NORM = (
    "/transparencia-y-acceso-a-informacion-publica/2-normativa/2-1-normatividad/"
    "normatividad-general-y-reglamentaria"
)


def _articulo(slug: str, titulo: str, pdf: str) -> str:
    return f"""
    <article class="w-full overflow-hidden">
        <div class="flex w-full gap-4 p-4">
            <div class="flex flex-col justify-center flex-1 min-w-0 gap-1">
                <a href="/{slug}" id="{slug}" target="" class="block">
                    <p class="text-base font-semibold leading-tight break-words text-govco-dark-blue">{titulo}</p>
                </a>
                <ul class="mt-2 ml-4 text-sm italic text-gray-600 list-disc">
                    <li><a href="{pdf}" target="_blank">Clic aquí</a></li>
                </ul>
            </div>
        </div>
    </article>
    """


def _registrar_todas_las_categorias_vacias(fuera_de=()):
    """Registra respuestas vacías para las 7 categorías, salvo las indicadas
    en `fuera_de` (que el propio test registra con su propio contenido)."""
    from core.scrapers.families.mindeporte import _CATEGORIAS

    for slug in _CATEGORIAS:
        if slug in fuera_de:
            continue
        responses.add(responses.GET, f"{_BASE}{_NORM}/{slug}", body="<div>vacío</div>")


@responses.activate
def test_scrap_flat_category_cuts_pagination_on_out_of_range_date():
    pagina1 = _articulo("decreto-855", "Decreto 855 del 30 de julio de 2025", f"{_BASE}/files/d855.pdf")
    pagina1 += '<a href="?page=2" rel="next">Siguiente</a>'
    pagina2 = _articulo("decreto-viejo", "Decreto 100 de 2015", f"{_BASE}/files/d100.pdf")

    responses.add(responses.GET, f"{_BASE}{_NORM}/normograma/decretos", body=pagina1)
    responses.add(responses.GET, f"{_BASE}{_NORM}/normograma/decretos?page=2", body=pagina2)
    _registrar_todas_las_categorias_vacias(fuera_de=("normograma/decretos", "resoluciones"))
    responses.add(responses.GET, f"{_BASE}{_NORM}/resoluciones", body="<div>sin años</div>")

    scraper = ScrapMinDeporte()
    docs = scraper.scrap(fini="2025-01-01", ffin="2025-12-31")

    assert [d.title for d in docs] == ["D_MDEPORTE_0855_2025"]
    # Se pidió page=2 (para descubrir que ya es muy viejo) pero no una page=3.
    urls_pedidas = [c.request.url for c in responses.calls]
    assert f"{_BASE}{_NORM}/normograma/decretos?page=2" in urls_pedidas
    assert f"{_BASE}{_NORM}/normograma/decretos?page=3" not in urls_pedidas


@responses.activate
def test_scrap_resoluciones_only_visits_years_within_range():
    responses.add(responses.GET, f"{_BASE}{_NORM}/resoluciones", body=_RESOLUCIONES_ROOT_HTML)

    pagina_2024 = _articulo("res-2024", "Resolución 000010 del 5 de enero de 2024", f"{_BASE}/files/r2024.pdf")
    responses.add(responses.GET, f"{_BASE}{_NORM}/resoluciones/2024", body=pagina_2024)

    _registrar_todas_las_categorias_vacias(fuera_de=("resoluciones",))

    scraper = ScrapMinDeporte()
    docs = scraper.scrap(fini="2024-01-01", ffin="2024-12-31")

    assert [d.title for d in docs] == ["R_MDEPORTE_0010_2024"]
    urls_pedidas = [c.request.url for c in responses.calls]
    assert f"{_BASE}{_NORM}/resoluciones/2015" not in urls_pedidas
    assert f"{_BASE}{_NORM}/resoluciones/2025" not in urls_pedidas


@responses.activate
def test_scrap_continues_when_one_category_fails():
    responses.add(responses.GET, f"{_BASE}{_NORM}/resoluciones", body="<div>sin años</div>")
    responses.add(responses.GET, f"{_BASE}{_NORM}/normograma/decretos", status=500)

    pagina_leyes = _articulo("ley-1", "Ley 100 del 1 de enero de 2024", f"{_BASE}/files/ley100.pdf")
    responses.add(responses.GET, f"{_BASE}{_NORM}/normograma/leyes", body=pagina_leyes)

    _registrar_todas_las_categorias_vacias(fuera_de=("resoluciones", "normograma/decretos", "normograma/leyes"))

    scraper = ScrapMinDeporte()
    docs = scraper.scrap(fini="2024-01-01", ffin="2024-12-31")

    assert [d.title for d in docs] == ["L_MDEPORTE_0100_2024"]


@responses.activate
def test_scrap_respects_stop_event():
    import threading

    stop_event = threading.Event()
    stop_event.set()

    scraper = ScrapMinDeporte()
    docs = scraper.scrap(fini="2024-01-01", ffin="2024-12-31", stop_event=stop_event)

    assert docs == []
    assert len(responses.calls) == 0
