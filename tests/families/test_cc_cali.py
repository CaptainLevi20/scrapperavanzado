import datetime
import threading

import requests
import responses

from core.scrapers.families.cc_cali import (
    _INDICE,
    _SOURCE,
    _fecha,
    _paginas_de_anio,
    _filas,
    _titulo,
    ScrapCcCali,
)
from core.scrapers.registry import FAMILY_REGISTRY

_BASE = "https://www.ccc.org.co"
_UP = _BASE + "/wp-content/uploads/"


def _indice(*hrefs):
    # Copia del menú real del índice (pestañas por década, una <li> por año).
    lis = "".join(
        f'<li><a href="{h}" aria-label="Laudos - Será redirigido a una ventana nueva" tagrte="_blank">x</a></li>\n'
        for h in hrefs
    )
    return (
        "<html><body>"
        '<li role="presentation"><a href="#decada-1990" aria-controls="decada-1990" role="tab">1980 &#8211; 1999</a></li>'
        '<div role="tabpanel" class="tab-pane active" id="decada-2020"><ul class="menu-laudos">'
        f"{lis}</ul></div>"
        '<a href="/programas-y-servicios-empresariales/centro-de-conciliacion-arbitraje-y-amigable-composicion/arbitraje/laudos-arbitrales/">Laudos</a>'
        "</body></html>"
    ).encode("utf-8")


def _fila(n, archivo, texto):
    clase = "par" if n % 2 else "impar"
    return (
        f'<tr class="{clase}">\n<th>{n}</th>\n<td>\n'
        f'<a href="{_UP}{archivo}" target="_blank">{texto}</a>\n</td>\n</tr>\n'
    )


def _pagina(*filas):
    # Estructura real de una página de año: una table.tabla3 dentro de <article>;
    # fuera del artículo hay enlaces del pie (aquí, un PDF que no es laudo).
    return (
        "<html><body><header><a href='/wp-content/uploads/2020/01/RUT.pdf'>RUT</a></header>"
        '<article id="post-48506" class="post-48506 page type-page status-publish hentry">'
        '<table class="tabla3  table table-hover table-bordered" width="350"><tbody>\n'
        + "".join(_fila(i + 1, a, t) for i, (a, t) in enumerate(filas))
        + "</tbody></table></article>"
        "<footer><a href='/wp-content/uploads/2020/01/RUT-CCC.pdf'>RUT CCC</a></footer></body></html>"
    ).encode("utf-8")


_ANTIGUO = ("2026/08/CASA-INGLESA-LTDA-VS-ARMERAD-BETONG-VAGFORBATTINGAR.pdf",
            "Casa Inglesa Ltda. Vs. Armerad Betong Vagforbattingar")
_BARRIOS = ("2022/02/Ana-Rosa-Barrios-Vs-Hospital-Isaias-Duarte-Cancino-E.S.E..pdf",
            "Ana Rosa Barrios Vs. Hospital Isaías Duarte Cancino E.S.E.")
_SPIWAK = ("2022/02/Instalaciones-Hidraúlicas-y-Sanitarias-W.C.-Ltda.-Vs-Hotel-Spiwak-Chipichape-Cali-S.A..pdf",
           "Instalaciones Hidráulicas y Sanitarias W.C. Ltda. Vs. Hotel Spiwak Chipichape Cali S.A.")
_SPIWAK_ACL = ("2026/08/TRIBUNAL-DE-ARBITRAMENTO.pdf",
               "Instalaciones Hidráulicas y Sanitarias W.C. Ltda. Vs. Hotel Spiwak Chipichape Cali S.A. "
               "– Aclaración, corrección y adición al laudo")
_INSTALTUR = ("2026/08/LAUDO-INSTALTUR-10-08-2015.pdf",
              "Instalaciones Turísticas S.A. – Instaltur S.A. Vs. John Fredy Castaño Zuluaga")
_RAD = ("2024/07/LaudoArbitral_Rad_A-20201223-0803.pdf", "LaudoArbitral_Rad_A-20201223-0803")
_CEDENO = ("2024/07/031.-06-03-24-LAUDO-ARBITRAL-OSWALDO-CEDEÑO-REYES-Vs-POLLOS-BUCANERO-S.A..pdf",
           "031. 06-03-24 LAUDO ARBITRAL OSWALDO CEDEÑO REYES Vs POLLOS BUCANERO S.A.")
_FESM = ("2024/07/045.-Laudo-Arbitral-A-202210260876-FESM-vs-ATC.pdf",
         "045. Laudo Arbitral A-202210260876 FESM vs ATC")
_SV = ("2024/07/001.3-LaudoFirmadoConSV.pdf", "001.3 LaudoFirmadoConSV")
_ACTA25 = ("2025/10/0057-Acta-No.25-Laudo-18-09-2024.pdf", "0057. Acta No.25 Laudo 18-09-2024")


# ---------------------------------------------------------------- fechas


def test_fecha_formas_de_la_tabla():
    d = datetime.date
    assert _fecha("031. 06-03-24 LAUDO ARBITRAL OSWALDO") == d(2024, 3, 6)
    assert _fecha("0097.1.Laudo_Definitivo_23.01.24") == d(2024, 1, 23)
    assert _fecha("Laudo Cali 280624- VF") == d(2024, 6, 28)
    assert _fecha("LAUDO PAVIMENTOS VS MPIO CALI 03 02 2017") == d(2017, 2, 3)
    assert _fecha("Laudo SMI Technologies VS. Nexura International SAS. 26.10.2017.") == d(2017, 10, 26)
    assert _fecha("LAUDO DEFINITIVO CISA - DEPTO ABR 13_ 2020") == d(2020, 4, 13)
    assert _fecha("LAUDO-DEFINITIVO-CISA-DEPTO-ABR-13_-2020.pdf") == d(2020, 4, 13)
    assert _fecha("Laudo-Arbitral-Tribunal-Corema-vs-Mapfre-12-de-diciembre-de-2018-VERSION-FINAL-12-dic-8-am.pdf") \
        == d(2018, 12, 12)
    assert _fecha("LAUDO-INSTALTUR-10-08-2015.pdf") == d(2015, 8, 10)
    assert _fecha("0061. Laudo_12.03.2024") == d(2024, 3, 12)
    assert _fecha("0057. Acta No.25 Laudo 18-09-2024") == d(2024, 9, 18)


def test_fecha_no_confunde_numeros_sueltos():
    assert _fecha("Acuavalle 2010 Vs. Acuavalle S.A. E.S.P.") is None
    assert _fecha("0097.1.Laudo_Definitivo") is None
    assert _fecha("001.3 LaudoFirmadoConSV") is None
    assert _fecha("40.1. Laudo Arbitral Tribunal JGGG Vs. MF") is None
    assert _fecha("Empaques Catalina González Ltda. Vs. Almacenes La 14 S.A.") is None
    # El radicado no es una fecha suelta.
    assert _fecha("LaudoArbitral_Rad_A-20201223-0803") is None
    assert _fecha("045. Laudo Arbitral A-202210260876 FESM vs ATC") is None
    # Fechas imposibles.
    assert _fecha("Laudo 32-13-2020") is None
    assert _fecha("Laudo 999999") is None
    assert _fecha("") is None


# ---------------------------------------------------------------- títulos


def test_titulo_con_radicado_tal_cual():
    t, unverified = _titulo("LaudoArbitral_Rad_A-20201223-0803", "LaudoArbitral_Rad_A-20201223-0803.pdf",
                            None, 2022)
    assert (t, unverified) == ("LA_CCC_A-20201223-0803_2022", False)
    t, unverified = _titulo(_FESM[1], _FESM[0], None, 2024)
    assert (t, unverified) == ("LA_CCC_A-202210260876_2024", False)


def test_titulo_con_fecha_y_sin_radicado():
    t, unverified = _titulo(_CEDENO[1], _CEDENO[0], datetime.date(2024, 3, 6), 2024)
    assert (t, unverified) == ("LA_CCC_20240306_2024", False)


def test_titulo_de_respaldo_con_partes():
    t, unverified = _titulo(_BARRIOS[1], _BARRIOS[0], None, 2015)
    assert t == "LA_CCC_Ana_Rosa_Barrios_Vs_Hospital_Isaias_Duarte_Cancino_ESE_2015"
    assert unverified is True
    # El prefijo de numeración (001.3) no es número: no va en el título.
    t, unverified = _titulo(_SV[1], _SV[0], None, 2024)
    assert t == "LA_CCC_LaudoFirmadoConSV_2024"
    assert unverified is True
    # "Laudo arbitral"/"Tribunal" al principio se quitan.
    t, _ = _titulo("Laudo Arbitral – Semillas Valle S.A. Vs Hergon Agro S.A.S.", "x.pdf", None, 2016)
    assert t == "LA_CCC_Semillas_Valle_SA_Vs_Hergon_Agro_SAS_2016"
    t, _ = _titulo("TRIBUNAL CONSORCIO PATIO SUR VS METRO CALI S.A", "x.pdf", None, 2016)
    assert t == "LA_CCC_CONSORCIO_PATIO_SUR_VS_METRO_CALI_SA_2016"


def test_titulo_de_respaldo_corta_a_80_en_palabra_entera():
    t, _ = _titulo(_SPIWAK_ACL[1], _SPIWAK_ACL[0], None, 2015)
    cuerpo = t[len("LA_CCC_"):-len("_2015")]
    assert len(cuerpo) <= 80
    assert not cuerpo.endswith("_")
    assert cuerpo == "Instalaciones_Hidraulicas_y_Sanitarias_WC_Ltda_Vs_Hotel_Spiwak_Chipichape_Cali"


# ---------------------------------------------------------------- índice y páginas


def test_paginas_de_anio_desde_los_enlaces_del_indice():
    html = _indice("/laudos-2015/", "/laudos/laudos-2022/", "/laudos-1980-1996/", "/laudos-2015/")
    assert _paginas_de_anio(html.decode()) == [
        (_BASE + "/laudos-1980-1996/", 1980, 1996),
        (_BASE + "/laudos-2015/", 2015, 2015),
        (_BASE + "/laudos/laudos-2022/", 2022, 2022),
    ]


def test_filas_solo_de_la_tabla_del_articulo():
    filas = list(_filas(_pagina(_BARRIOS, _SPIWAK).decode(), _BASE + "/laudos-2015/"))
    assert [f["texto"] for f in filas] == [_BARRIOS[1], _SPIWAK[1]]
    assert filas[0]["href"] == _UP + _BARRIOS[0]


# ---------------------------------------------------------------- scrap()


def _sitio(paginas, fallan=()):
    """paginas: {ruta: [filas]}; el índice enlaza a todas, más las de `fallan`."""
    responses.add(responses.GET, _INDICE, body=_indice(*paginas, *fallan))
    for ruta, filas in paginas.items():
        responses.add(responses.GET, _BASE + ruta, body=_pagina(*filas))
    for ruta in fallan:
        responses.add(responses.GET, _BASE + ruta, status=500)


def _scrap(fini="1900-01-01", ffin="2100-12-31", **kw):
    avisos = []
    docs = ScrapCcCali().scrap(fini, ffin, on_progress=avisos.append, **kw)
    return docs, avisos


def test_registro_y_atributos():
    assert FAMILY_REGISTRY["cc_cali"] is ScrapCcCali
    assert _SOURCE == "Cámara de Comercio de Cali"
    assert ScrapCcCali.scheduled_min_lookback_days == 20_000
    assert ScrapCcCali.alerta_margen_dias is None
    assert ScrapCcCali.checks_for_republication is True


@responses.activate
def test_scrap_completo():
    _sitio({
        "/laudos-1980-1996/": [_ANTIGUO],
        "/laudos-2015/": [_BARRIOS, _INSTALTUR],
        "/laudos/laudos-2022/": [_RAD],
        "/laudos-2025/": [_ACTA25],
    })
    docs, avisos = _scrap()
    por_titulo = {d.title: d for d in docs}
    assert list(por_titulo) == [
        "LA_CCC_Casa_Inglesa_Ltda_Vs_Armerad_Betong_Vagforbattingar_1996",
        "LA_CCC_Ana_Rosa_Barrios_Vs_Hospital_Isaias_Duarte_Cancino_ESE_2015",
        "LA_CCC_20150810_2015",
        "LA_CCC_A-20201223-0803_2022",
        "LA_CCC_20240918_2024",
    ]
    antiguo = por_titulo["LA_CCC_Casa_Inglesa_Ltda_Vs_Armerad_Betong_Vagforbattingar_1996"]
    assert antiguo.f_public == antiguo.f_providencia == "1996-01-01"
    assert antiguo.title_unverified is True
    barrios = por_titulo["LA_CCC_Ana_Rosa_Barrios_Vs_Hospital_Isaias_Duarte_Cancino_ESE_2015"]
    assert barrios.f_public == "2015-01-01"
    assert barrios.title_unverified is True
    assert barrios.detalle == _BARRIOS[1]
    assert barrios.tipo == "Laudo arbitral"
    assert barrios.link == {"url": _UP + _BARRIOS[0], "method": "GET"}
    assert barrios.save_path.endswith("LA_CCC_Ana_Rosa_Barrios_Vs_Hospital_Isaias_Duarte_Cancino_ESE_2015(extension)")
    # Fecha sólo en el nombre del archivo: se toma.
    instaltur = por_titulo["LA_CCC_20150810_2015"]
    assert instaltur.f_public == "2015-08-10" and not instaltur.title_unverified
    # Radicado sin fecha: año de la página, 1 de enero.
    rad = por_titulo["LA_CCC_A-20201223-0803_2022"]
    assert rad.f_public == "2022-01-01" and not rad.title_unverified
    # Fecha del nombre de otro año que la página: manda el nombre, con aviso.
    acta = por_titulo["LA_CCC_20240918_2024"]
    assert acta.f_public == "2024-09-18"
    assert any("2025" in a and "2024" in a for a in avisos)
    assert any("1980-1996" in a for a in avisos)


@responses.activate
def test_titulo_repetido_lleva_sufijo_por_ruta_de_subida_sin_importar_el_orden():
    # La aclaración (subida en 2026/08) va primero en la tabla; el laudo
    # (subido en 2022/02) igual queda sin sufijo.
    _sitio({"/laudos-2015/": [_SPIWAK_ACL, _SPIWAK]})
    docs, avisos = _scrap()
    titulos = {d.link["url"]: d.title for d in docs}
    base = "LA_CCC_Instalaciones_Hidraulicas_y_Sanitarias_WC_Ltda_Vs_Hotel_Spiwak_Chipichape_Cali_2015"
    assert titulos[_UP + _SPIWAK[0]] == base
    assert titulos[_UP + _SPIWAK_ACL[0]] == base + "_2"
    assert any("repetido" in a for a in avisos)


@responses.activate
def test_sufijo_no_depende_del_rango_de_fechas():
    _sitio({"/laudos-2015/": [_SPIWAK, _SPIWAK_ACL]})
    docs, _ = _scrap()
    assert len(docs) == 2
    # Aunque sólo se pida 2015, la aclaración sigue siendo _2.
    docs, _ = _scrap(fini="2015-01-01", ffin="2015-01-01")
    assert sorted(d.title[-2:] for d in docs) == ["15", "_2"]


@responses.activate
def test_enlace_repetido_se_omite_con_aviso():
    _sitio({"/laudos-2015/": [_BARRIOS], "/laudos-2016/": [_BARRIOS]})
    docs, avisos = _scrap()
    assert len(docs) == 1
    assert any("enlace ya visto" in a for a in avisos)


@responses.activate
def test_filtro_por_fecha_sin_piso():
    _sitio({"/laudos-1980-1996/": [_ANTIGUO], "/laudos-2015/": [_BARRIOS, _INSTALTUR]})
    docs, _ = _scrap(fini="1990-01-01", ffin="1999-12-31")
    assert [d.f_public for d in docs] == ["1996-01-01"]
    docs, _ = _scrap(fini="2015-02-01", ffin="2015-12-31")
    assert [d.title for d in docs] == ["LA_CCC_20150810_2015"]


@responses.activate
def test_pagina_que_falla_avisa_y_sigue():
    _sitio({"/laudos-2015/": [_BARRIOS]}, fallan=("/laudos-2016/",))
    docs, avisos = _scrap()
    assert len(docs) == 1
    assert any("Error" in a and "2016" in a for a in avisos)


@responses.activate
def test_indice_sin_anios_avisa():
    responses.add(responses.GET, _INDICE, body=b"<html><body>Nada</body></html>")
    docs, avisos = _scrap()
    assert docs == []
    assert any("no se encontraron" in a for a in avisos)


@responses.activate
def test_indice_que_falla_avisa():
    responses.add(responses.GET, _INDICE, body=requests.ConnectionError("caído"))
    docs, avisos = _scrap()
    assert docs == []
    assert any("Error" in a for a in avisos)


@responses.activate
def test_stop_event_y_limit():
    _sitio({"/laudos-2015/": [_BARRIOS, _INSTALTUR, _SPIWAK]})
    docs, _ = _scrap(limit=2)
    assert len(docs) == 2
    ev = threading.Event()
    ev.set()
    antes = len(responses.calls)
    docs, _ = _scrap(stop_event=ev)
    assert docs == []
    assert len(responses.calls) == antes  # cancelado antes de pedir nada
