from pathlib import Path

import pytest
import requests
from bs4 import BeautifulSoup

import core.scrapers.families.samai as samai_module
from core.scrapers.families.samai import (
    ScrapTribunales,
    SAMAI_CORPS,
    _especialidad_legible,
    _normalizar_clase,
    _normalizar_titulo,
)
from core.scrapers.registry import FAMILY_REGISTRY
from core.utils import compute_doc_id

_ROW_HTML = """
<tr>
  <td>0</td>
  <td>25001233300020260001200</td>
  <td>Juan Pérez</td>
  <td>3</td><td>4</td><td>5</td>
  <td>14/06/2026</td>
  <td>Auto que rechaza recurso de apelación</td>
  <td>8</td>
  <td><a class="btn-success" onclick="CargarVentana('https://samai.example.com/VerProvidencia?id=1')">Ver</a></td>
</tr>
"""


def test_samai_has_28_registered_tribunals():
    assert len(SAMAI_CORPS) == 28
    assert SAMAI_CORPS["1100103"] == "Consejo de Estado"


def test_samai_is_registered_under_its_family_key():
    import core.scrapers.families  # noqa: F401

    assert FAMILY_REGISTRY["samai"] is ScrapTribunales


def test_parse_row_builds_expected_rawdocmodel():
    row = BeautifulSoup(_ROW_HTML, "html.parser").find("tr")
    scraper = ScrapTribunales(corp_code="2500023", corp_name="Tribunal Administrativo de Cundinamarca")

    doc = scraper._parse_row(row, "2500023", "Tribunal Administrativo de Cundinamarca", "Sección Primera", "2026-06-15")

    # Tribunal Administrativo (no Consejo de Estado): título tipo Tribunal
    # Superior, "T_{CÓDIGO}_{radicado}" — nunca el bare radicado o el formato
    # con acrónimo de Consejo de Estado.
    assert doc.title == "T_CUND_25001233300020260001200"
    assert doc.tipo == "Auto"
    assert doc.detalle == "Auto que rechaza recurso de apelación"
    assert doc.especialidad == "5"  # columna "Clase" cruda (ver _ROW_HTML)
    assert doc.f_public == "2026-06-15"
    assert doc.f_providencia == "2026-06-14"
    assert doc.link["method"] == "jwt_indirect"
    assert doc.link["url"] == "https://samai.example.com/VerProvidencia?id=1"
    # Identity includes f_providencia (2026-06-14), not just the radicado —
    # the radicado alone identifies the case, not this specific actuación.
    assert doc.link["body"] == {"path": "2500023_25001233300020260001200_2026-06-14"}


def test_parse_row_returns_none_without_jwt_link():
    html = _ROW_HTML.replace('<a class="btn-success"', '<a class="btn-other"')
    row = BeautifulSoup(html, "html.parser").find("tr")
    scraper = ScrapTribunales(corp_code="2500023", corp_name="Tribunal Administrativo de Cundinamarca")
    assert scraper._parse_row(row, "2500023", "Tribunal Administrativo de Cundinamarca", "Sección Primera", "2026-06-15") is None


# --- tipo: normalización de mayúsculas ---------------------------------------
#
# SAMAI no es consistente con las mayúsculas de la primera palabra de la
# actuación ("Auto", "AUTO", "aUTO" aparecen todas para el mismo tipo de
# documento) — sin normalizar, un filtro por tipo en la interfaz se salta
# silenciosamente las variantes que no coinciden exactamente.


def test_parse_row_normalizes_all_caps_tipo():
    row_html = _ROW_HTML.replace(
        "Auto que rechaza recurso de apelación", "AUTO QUE RECHAZA RECURSO DE APELACIÓN"
    )
    row = BeautifulSoup(row_html, "html.parser").find("tr")
    scraper = ScrapTribunales(corp_code="2500023", corp_name="Tribunal Administrativo de Cundinamarca")

    doc = scraper._parse_row(row, "2500023", "Tribunal Administrativo de Cundinamarca", "Sección Primera", "2026-06-15")

    assert doc.tipo == "Auto"


def test_parse_row_normalizes_lowercase_tipo():
    row_html = _ROW_HTML.replace(
        "Auto que rechaza recurso de apelación", "auto que rechaza recurso de apelación"
    )
    row = BeautifulSoup(row_html, "html.parser").find("tr")
    scraper = ScrapTribunales(corp_code="2500023", corp_name="Tribunal Administrativo de Cundinamarca")

    doc = scraper._parse_row(row, "2500023", "Tribunal Administrativo de Cundinamarca", "Sección Primera", "2026-06-15")

    assert doc.tipo == "Auto"


def test_parse_row_normalizes_mixed_case_tipo():
    row_html = _ROW_HTML.replace(
        "Auto que rechaza recurso de apelación", "aUTO que rechaza recurso de apelación"
    )
    row = BeautifulSoup(row_html, "html.parser").find("tr")
    scraper = ScrapTribunales(corp_code="2500023", corp_name="Tribunal Administrativo de Cundinamarca")

    doc = scraper._parse_row(row, "2500023", "Tribunal Administrativo de Cundinamarca", "Sección Primera", "2026-06-15")

    assert doc.tipo == "Auto"


def test_parse_row_merges_autos_plural_into_auto():
    # Confirmado con el usuario: "Autos" es la misma tipología que "Auto",
    # SAMAI simplemente no es consistente con el singular/plural — a
    # diferencia de otras variantes de tipo, esta sí se fusiona
    # explícitamente (ver _TIPO_ALIAS).
    row_html = _ROW_HTML.replace(
        "Auto que rechaza recurso de apelación", "Autos que rechazan recurso de apelación"
    )
    row = BeautifulSoup(row_html, "html.parser").find("tr")
    scraper = ScrapTribunales(corp_code="2500023", corp_name="Tribunal Administrativo de Cundinamarca")

    doc = scraper._parse_row(row, "2500023", "Tribunal Administrativo de Cundinamarca", "Sección Primera", "2026-06-15")

    assert doc.tipo == "Auto"


def test_parse_row_merges_all_caps_autos_into_auto():
    row_html = _ROW_HTML.replace(
        "Auto que rechaza recurso de apelación", "AUTOS QUE RECHAZAN RECURSO DE APELACIÓN"
    )
    row = BeautifulSoup(row_html, "html.parser").find("tr")
    scraper = ScrapTribunales(corp_code="2500023", corp_name="Tribunal Administrativo de Cundinamarca")

    doc = scraper._parse_row(row, "2500023", "Tribunal Administrativo de Cundinamarca", "Sección Primera", "2026-06-15")

    assert doc.tipo == "Auto"


def test_scrap_section_filters_dates_outside_range(monkeypatch):
    scraper = ScrapTribunales(corp_code="2500023", corp_name="Tribunal Administrativo de Cundinamarca")

    soup3 = BeautifulSoup(
        '<select id="MainContent_LstUEstados">'
        '<option value="15/06/2026 0:00:00">15/06/2026</option>'
        '<option value="15/01/2020 0:00:00">15/01/2020</option>'
        "</select>",
        "html.parser",
    )

    monkeypatch.setattr(scraper, "_step4a_check_all", lambda *a, **k: soup3)
    monkeypatch.setattr(
        scraper,
        "_step4b_consultar",
        lambda *a, **k: f'<table id="MainContent_GvProvidencias"><tr><th>h</th></tr>{_ROW_HTML}</table>',
    )

    from datetime import datetime

    docs = scraper._scrap_section(
        session=None,
        soup3=soup3,
        corp_code="2500023",
        corp_name="Tribunal Administrativo de Cundinamarca",
        sec_code="SEC1",
        sec_name="Sección Primera",
        fini_dt=datetime(2026, 6, 1),
        ffin_dt=datetime(2026, 6, 30),
        stop_event=None,
        on_progress=None,
    )

    # only the 15/06/2026 date is in range; the 2020 one is filtered out before any HTTP call
    assert len(docs) == 1
    assert docs[0].f_public == "2026-06-15"


def test_scrap_swallows_exceptions_and_returns_empty_list(monkeypatch):
    scraper = ScrapTribunales(corp_code="2500023", corp_name="Tribunal Administrativo de Cundinamarca")
    monkeypatch.setattr(scraper, "_scrap_corp", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("sitio caído")))

    messages = []
    docs = scraper.scrap(fini="2026-06-01", ffin="2026-06-30", on_progress=messages.append)

    assert docs == []
    assert any("Error en" in m for m in messages)


def test_samai_checks_for_republication_like_rama_judicial():
    # SAMAI relists the same "estado" row under a new date when the
    # notification wasn't claimed — same document, same file, just published
    # again. This must be treated as a possible republication (version
    # history, previewable), not silently ignored.
    scraper = ScrapTribunales("1100103", "Consejo de Estado")
    assert scraper.checks_for_republication is True


def test_samai_doc_id_is_stable_across_relisting_dates_for_the_same_actuacion():
    # Same actuación (same f_providencia, the real decision date) relisted
    # under a different "estado" date must produce the SAME doc_id — that's a
    # true republication (notification wasn't claimed), not a new document.
    # This test only varies the listing date (estado_fecha_str); the row's
    # own f_providencia (2026-06-14, from _ROW_HTML) doesn't change.
    scraper = ScrapTribunales("1100103", "Consejo de Estado")
    row = BeautifulSoup(_ROW_HTML, "html.parser").find("tr")

    doc_first_listing = scraper._parse_row(row, "1100103", "Consejo de Estado", "Sección Primera", "2026-07-15")
    doc_relisting = scraper._parse_row(row, "1100103", "Consejo de Estado", "Sección Primera", "2026-07-28")

    doc_id_1 = compute_doc_id(doc_first_listing, include_publication_date=scraper.doc_id_uses_publication_date)
    doc_id_2 = compute_doc_id(doc_relisting, include_publication_date=scraper.doc_id_uses_publication_date)
    assert doc_id_1 == doc_id_2


def test_samai_doc_id_differs_for_distinct_actuaciones_sharing_a_radicado():
    # A radicado identifies the whole *case*, not one document — the same
    # case accumulates many distinct actuaciones over time (real cases found:
    # "Auto que rechaza demanda" on 2026-07-27 vs "Auto que inadmite demanda"
    # on 2026-07-14, same radicado). These must NOT collapse into one
    # document just because they share a radicado; f_providencia (row 6,
    # "Fecha Providencia") is what actually distinguishes them.
    scraper = ScrapTribunales("1100103", "Consejo de Estado")
    row_html_otra_actuacion = _ROW_HTML.replace("14/06/2026", "20/06/2026")
    row_1 = BeautifulSoup(_ROW_HTML, "html.parser").find("tr")
    row_2 = BeautifulSoup(row_html_otra_actuacion, "html.parser").find("tr")

    doc_1 = scraper._parse_row(row_1, "1100103", "Consejo de Estado", "Sección Primera", "2026-07-15")
    doc_2 = scraper._parse_row(row_2, "1100103", "Consejo de Estado", "Sección Primera", "2026-07-15")

    assert doc_1.f_providencia != doc_2.f_providencia
    doc_id_1 = compute_doc_id(doc_1, include_publication_date=scraper.doc_id_uses_publication_date)
    doc_id_2 = compute_doc_id(doc_2, include_publication_date=scraper.doc_id_uses_publication_date)
    assert doc_id_1 != doc_id_2


# --- título: {radicado}({acrónimo de la clase de proceso}) --------------------
#
# Catálogo y reglas de normalización dictados por el usuario a partir de datos
# reales de Consejo de Estado (ver core/scrapers/families/samai.py).


_CONSEJO_ESTADO = "1100103"


def test_normalizar_titulo_appends_acronym_for_known_clase():
    assert _normalizar_titulo("11001-03-28-000-2026-00329-00", "ACCIONES DE CUMPLIMIENTO", _CONSEJO_ESTADO) == (
        "11001-03-28-000-2026-00329-00(ACU)"
    )


def test_normalizar_titulo_strips_ley_prefix_before_matching():
    # "LEY 1437 NULIDAD" y "Nulidad" son la misma clase — deben caer en el mismo
    # acrónimo aunque una traiga el código de ley y la otra no.
    assert _normalizar_titulo("11001-03-24-000-2015-00065-00", "LEY 1437 NULIDAD", _CONSEJO_ESTADO) == (
        "11001-03-24-000-2015-00065-00(N)"
    )
    assert _normalizar_titulo("11001-03-24-000-2015-00065-00", "Nulidad", _CONSEJO_ESTADO) == (
        "11001-03-24-000-2015-00065-00(N)"
    )


def test_normalizar_titulo_strips_accion_de_prefix_before_matching():
    # "ACCION DE NULIDAD" debe caer en el mismo acrónimo que "Nulidad", no
    # quedarse como una clase aparte solo por el prefijo "Acción de".
    assert _normalizar_clase("ACCION DE NULIDAD") == _normalizar_clase("Nulidad")
    assert _normalizar_titulo("05001-23-33-000-2026-00810-01", "ACCION DE NULIDAD", _CONSEJO_ESTADO) == (
        "05001-23-33-000-2026-00810-01(N)"
    )


def test_normalizar_titulo_strips_articulo_decision_reference():
    assert _normalizar_titulo(
        "11001-03-24-000-2020-00002-00", "NULIDAD RELATIVA ARTÍCULO 172 DECISION 486", _CONSEJO_ESTADO
    ) == "11001-03-24-000-2020-00002-00(NR)"
    assert _normalizar_titulo(
        "11001-03-24-000-2020-00002-00", "NULIDAD ABSOLUTA ARTÍCULO 172 DECISION 486", _CONSEJO_ESTADO
    ) == "11001-03-24-000-2020-00002-00(NA)"


def test_normalizar_titulo_is_accent_and_case_insensitive():
    assert _normalizar_titulo("r1", "reparación directa", _CONSEJO_ESTADO) == "r1(RD)"
    assert _normalizar_titulo("r1", "REPARACION DIRECTA", _CONSEJO_ESTADO) == "r1(RD)"


def test_normalizar_titulo_merges_clases_the_user_confirmed_are_the_same():
    # Confirmado con el usuario: aunque el texto es distinto, son la misma clase.
    assert _normalizar_titulo("r1", "CONFLICTOS DE COMPETENCIA JUDICIAL", _CONSEJO_ESTADO) == "r1(CCO)"
    assert _normalizar_titulo("r1", "Protección de los derechos e intereses colectivos", _CONSEJO_ESTADO) == "r1(PDIC)"
    # "Acción de grupo" y "reparación de perjuicios causados a un grupo" son
    # clases distintas (confirmado con el usuario) — no deben compartir sigla.
    assert _normalizar_titulo("r1", "Acción de grupo", _CONSEJO_ESTADO) == "r1(AG)"
    assert _normalizar_titulo(
        "r1", "LEY 1437 REPARACION DE PERJUICIOS CAUSADOS A UN GRUPO", _CONSEJO_ESTADO
    ) == "r1(RPAG)"


def test_normalizar_titulo_falls_back_to_bare_radicado_for_unknown_clase():
    # Clase que no está en el catálogo (todavía no vista en los datos reales) —
    # se deja el radicado solo, sin acrónimo, hasta que se defina su sigla.
    assert _normalizar_titulo("11001-03-24-000-2026-99999-00", "Una clase nunca vista", _CONSEJO_ESTADO) == (
        "11001-03-24-000-2026-99999-00"
    )


# --- título de Tribunal Administrativo: T_{CÓDIGO}_{radicado segmentado} ------
#
# A diferencia de Consejo de Estado, un Tribunal Administrativo NUNCA lleva el
# acrónimo de la clase — su título debe imitar el de Tribunales Superiores
# (rama_judicial), no el de Consejo de Estado.


def test_normalizar_titulo_for_tribunal_administrativo_mirrors_tribunal_superior_format():
    titulo = _normalizar_titulo(
        "05001-23-33-000-2018-01895-00", "Nulidad y restablecimiento del derecho", "0500123"
    )
    assert titulo == "T_ANTI_05001_23_33_000_2018_01895_00"


def test_normalizar_titulo_for_tribunal_administrativo_ignores_the_clase_entirely():
    # La clase no debe afectar en nada el título de un Tribunal Administrativo,
    # a diferencia de Consejo de Estado — ni siquiera para agregar un acrónimo.
    sin_acronimo = _normalizar_titulo("13001-23-33-000-2026-00400-00", "Una clase nunca vista", "1300123")
    con_acronimo = _normalizar_titulo("13001-23-33-000-2026-00400-00", "Nulidad", "1300123")
    assert sin_acronimo == con_acronimo == "T_BOLI_13001_23_33_000_2026_00400_00"


def test_normalizar_titulo_for_tribunal_administrativo_never_matches_consejo_de_estado_format():
    # Requisito del usuario: el nombre de un Tribunal Administrativo no debe
    # parecerse al de Consejo de Estado (radicado(ACRÓNIMO)).
    from core.utils import is_samai_case_title

    titulo = _normalizar_titulo("05001-23-33-000-2018-01895-00", "Nulidad", "0500123")
    assert is_samai_case_title(titulo) is False


def test_normalizar_titulo_for_tribunal_administrativo_matches_tribunal_superior_pattern():
    from core.utils import is_radicado_title

    titulo = _normalizar_titulo("05001-23-33-000-2018-01895-00", "Nulidad", "0500123")
    assert is_radicado_title(titulo) is True


# --- "(ESCRITURAL)"/"(ORAL)"/"S. ORAL": ruido de trámite, no de clase ------
#
# Confirmado con el usuario el 2026-08-04: a diferencia de "(R)" (que en al
# menos un caso — "TUTELA 2 INSTANCIA (R)" — sí obtuvo su propia sigla, T2,
# distinta de "TUTELA"), escritural/oral nunca cambia la clase. Se quita de
# forma genérica en vez de agregar cada combinación al catálogo una por una.


def test_normalizar_clase_strips_escritural_suffix():
    assert _normalizar_clase("REPARACION DIRECTA (ESCRITURAL)") == "REPARACION DIRECTA"


def test_normalizar_clase_strips_oral_suffix_in_various_forms():
    assert _normalizar_clase("CUMPLIMIENTO (ORAL)") == "CUMPLIMIENTO"
    assert _normalizar_clase("CUMPLIMIENTO S. ORAL") == "CUMPLIMIENTO"
    assert _normalizar_clase("CUMPLIMIENTO ORAL") == "CUMPLIMIENTO"


def test_normalizar_clase_does_not_strip_oral_as_substring_of_electoral():
    # "ORAL" solo se quita como palabra completa (\bORAL\b) — "ELECTORAL"
    # contiene la letras "ORAL" pero no como palabra separada, y NULIDAD
    # ELECTORAL es una clase real y distinta (sigla NE) que no debe romperse.
    assert _normalizar_clase("NULIDAD ELECTORAL") == "NULIDAD ELECTORAL"
    assert _normalizar_clase("ELECTORAL CON SUSPENSION PROVISIONAL") == "ELECTORAL CON SUSPENSION PROVISIONAL"
    assert _normalizar_clase("ELECTORALES") == "ELECTORALES"


def test_especialidad_legible_resolves_unseen_clase_with_escritural_suffix():
    # Este texto exacto nunca apareció en la revisión del catálogo — la
    # generalización debe resolverlo igual, sin necesidad de agregarlo.
    assert _especialidad_legible("REPARACION DIRECTA (ESCRITURAL)") == "Reparación directa"
    # Mayúscula/minúscula mixta (como la reportó el usuario) no cambia nada —
    # _normalizar_clase ya mayusculiza todo antes de buscar en el catálogo.
    assert _especialidad_legible("rEPARACION DIRECTA (ESCRITURAL)") == "Reparación directa"


def test_normalizar_titulo_and_especialidad_are_case_law_code_insensitive():
    # "LEY 1437 NULIDAD Y RESTABLECIMIENTO DEL DERECHO" y "Nulidad y
    # restablecimiento del derecho" son la misma clase, pero el sitio no
    # siempre lo escribe igual — la columna Especialidad/Proceso debe mostrar
    # siempre la misma forma limpia, sin importar cuál trajo el sitio.
    assert _especialidad_legible("LEY 1437 NULIDAD Y RESTABLECIMIENTO DEL DERECHO") == (
        "Nulidad y restablecimiento del derecho"
    )
    assert _especialidad_legible("Nulidad y restablecimiento del derecho") == (
        "Nulidad y restablecimiento del derecho"
    )


def test_especialidad_legible_falls_back_to_raw_text_for_unknown_clase():
    # No hay forma de "limpiar" una clase que no está en el catálogo — se deja
    # el texto tal cual llegó del sitio.
    assert _especialidad_legible("Una clase nunca vista") == "Una clase nunca vista"


# --- catálogo ampliado el 2026-08-04: 51 clases nuevas de Tribunales --------
# Administrativos, confirmadas una por una con el usuario a partir del run
# real de los 27 tribunales (8,797 documentos). Cada caso cubre el texto
# crudo exacto que trajo SAMAI, no una forma ya simplificada.


def test_catalogo_ampliado_toda_sigla_nueva_tiene_nombre_legible():
    # Chequeo de completitud: toda sigla que aparece como valor en
    # _CLASE_ACRONIMOS debe tener una entrada en _ACRONIMO_A_NOMBRE — si no,
    # _especialidad_legible cae de vuelta al texto crudo aunque el acrónimo
    # sí se haya resuelto, y la columna Especialidad/Proceso mostraría un
    # dato inconsistente con el resto del catálogo.
    from core.scrapers.families.samai import _ACRONIMO_A_NOMBRE, _CLASE_ACRONIMOS

    for clase, acronimo in _CLASE_ACRONIMOS.items():
        assert acronimo in _ACRONIMO_A_NOMBRE, f"'{clase}' -> '{acronimo}' no tiene nombre legible"


@pytest.mark.parametrize(
    "clase_cruda,nombre_esperado",
    [
        ("EJECUTIVOS", "Ejecutivo"),
        ("PROCESO EJECUTIVO", "Ejecutivo"),
        ("ACCION EJECUTIVA", "Ejecutivo"),
        ("ACCIONES EJECUTIVOS", "Ejecutivo"),
        ("PROPIEDAD INDUSTRIAL", "Propiedad industrial"),
        ("NUL. Y REST. CON SUSPENSIÓN PROVISIONAL", "Nulidad y restablecimiento del derecho con suspensión provisional"),
        # "LEY 1437 ..." se quita antes de matchear, y el punto final de
        # "COLEC." lo quita el .strip(" -.") de _normalizar_clase.
        ("LEY 1437 PROTECCION DERECHOS E INTERESES COLEC.", "Protección de los derechos e intereses colectivos"),
        ("PROTECCIÓN DE DERECHOS E INTERESES COLECTIVOS", "Protección de los derechos e intereses colectivos"),
        ("VALIDEZ DE ACTOS ADMINISTRATIVOS", "Validez de actos administrativos"),
        ("ACCIONES POPULARES (R)", "Acciones populares"),
        ("ACCIONES POPULARES (ESCRITURAL)", "Acciones populares"),
        ("INSISTENCIA DE RESERVA", "Insistencia de reserva"),
        ("OBJECIONES", "Objeciones"),
        ("OBJECIONES A PROYECTOS DE ACUERDO", "Objeciones"),
        ("OBJECION", "Objeciones"),
        ("ACCIONES DE OBJECION A PROYECTOS", "Objeciones"),
        ("NULIDAD SIN SUSPENSION PROVISIONAL", "Nulidad sin suspensión provisional"),
        ("ACCIONES CONSTITUCIONALES", "Acciones constitucionales"),
        # Confirmado con el usuario: para este texto exacto manda RPAG, aunque
        # "Acción de grupo" (AG) sola sea una clase distinta.
        ("REPARACION DE LOS PERJUICIOS CAUSADOS A UN GRUPO (ACCION DE GRUPO)", "Reparación de perjuicios causados a un grupo"),
        ("IMPEDIMENTO O RECUSACIÓN", "Impedimento o recusación"),
        ("INCIDENTE DE IMPEDIMENTO", "Impedimento o recusación"),
        ("RECUSACIÓN", "Impedimento o recusación"),
        ("OBSERVACIONES CONSTITUCIONALES Y LEGALES S. ORAL", "Observaciones constitucionales y legales"),
        ("EXPROPIACION POR VIA ADMINISTRATIVA", "Expropiación por vía administrativa"),
        ("EXPROPIACIÓN", "Expropiación por vía administrativa"),
        ("APELACIÓN (ESCRITURAL)", "Apelación"),
        ("CONTROVERSIAS CONTRACTUALES (ESCRITURAL)", "Controversias contractuales"),
        ("CONTROVERSIA CONTRACTUAL", "Controversias contractuales"),
        ("ACCION CONTRACTUAL CON SUSPENSION PROVISIONAL", "Acción contractual con suspensión provisional"),
        ("ACCION DE TUTELA 2 INSTANCIA (R)", "Tutela 2da instancia"),
        ("ACCIONES DE TUTELA (R)", "Tutela"),
        ("EXEQUIBILIDAD", "Exequibilidad"),
        ("IMPUGNACIÓN TUTELA", "Impugnación tutela"),
        ("ACCION DE DEFINICION DE COMPETENCIAS", "Acción de definición de competencias"),
        ("ACCIONES DE DEFINICION DE COMPETENCIA", "Acción de definición de competencias"),
        ("CONTROL INMEDIATO DE LEGALIDAD", "Control inmediato de legalidad"),
        ("ELECTORAL CON SUSPENSION PROVISIONAL", "Electoral con suspensión provisional"),
        ("INCIDENTE DE REGULACION DE PERJUICIOS", "Incidente de regulación de perjuicios"),
        ("JUICIOS VARIOS", "Juicios varios"),
        ("NULIDAD Y RESTABLECIMIENTO DEL DERECHO (ESCRITURAL)", "Nulidad y restablecimiento del derecho"),
        ("REVISION DE ACUERDOS Y DECRETOS", "Revisión de acuerdos y decretos"),
        ("REVISION DE LEGALIDAD", "Revisión de legalidad"),
        ("REVISION JURIDICA", "Revisión jurídica"),
        ("CONCILIACION PREJUDICIAL", "Conciliación"),
        ("CONCILIACION EXTRAJUDICIAL", "Conciliación extrajudicial"),
        ("OBSERVACION", "Observaciones"),
        ("ASUNTOS AGRARIOS", "Asuntos agrarios"),
        ("APELACION SENTENCIA EJECUTIVO", "Apelación de sentencia ejecutivo"),
        ("RESTITUCION DE INMUEBLE", "Restitución de inmueble"),
        ("IMPUGNACION ACCION CUMPLIMIENTO", "Impugnación acción de cumplimiento"),
        ("DISCIPLINARIOS", "Disciplinarios"),
        ("ACCION SIMPLE DE NULIDAD", "Nulidad"),
    ],
)
def test_especialidad_legible_resolves_new_tribunal_administrativo_clases(clase_cruda, nombre_esperado):
    assert _especialidad_legible(clase_cruda) == nombre_esperado


def test_parse_row_stores_readable_clase_de_proceso_in_especialidad():
    row_html = (
        "<tr><td>0</td><td>25001233300020260001200</td><td>Juan Pérez</td>"
        "<td>3</td><td>4</td><td>LEY 1437 NULIDAD Y RESTABLECIMIENTO DEL DERECHO</td>"
        "<td>14/06/2026</td><td>Auto que rechaza recurso de apelación</td><td>8</td>"
        '<td><a class="btn-success" onclick="CargarVentana(\'https://samai.example.com/VerProvidencia?id=1\')">Ver</a></td></tr>'
    )
    row = BeautifulSoup(row_html, "html.parser").find("tr")
    scraper = ScrapTribunales(corp_code="1100103", corp_name="Consejo de Estado")

    doc = scraper._parse_row(row, "1100103", "Consejo de Estado", "Sección Primera", "2026-06-15")

    assert doc.especialidad == "Nulidad y restablecimiento del derecho"
    assert doc.title == "25001233300020260001200(NRD)"


def test_parse_row_uses_clase_column_to_build_the_polished_title():
    row_html = (
        "<tr><td>0</td><td>25001233300020260001200</td><td>Juan Pérez</td>"
        "<td>3</td><td>4</td><td>ACCIONES DE CUMPLIMIENTO</td>"
        "<td>14/06/2026</td><td>Auto que rechaza recurso de apelación</td><td>8</td>"
        '<td><a class="btn-success" onclick="CargarVentana(\'https://samai.example.com/VerProvidencia?id=1\')">Ver</a></td></tr>'
    )
    row = BeautifulSoup(row_html, "html.parser").find("tr")
    scraper = ScrapTribunales(corp_code="1100103", corp_name="Consejo de Estado")

    doc = scraper._parse_row(row, "1100103", "Consejo de Estado", "Sección Primera", "2026-06-15")

    assert doc.title == "25001233300020260001200(ACU)"


# --- número extra entre paréntesis (primera página del PDF) -----------------
#
# Algunos documentos de Consejo de Estado traen, junto al radicado en su
# primera página, un número entre paréntesis que no aparece en la tabla de
# resultados de SAMAI (ej. "Radicación  25000-...-01 (30146)"). Cuando
# aparece, se añade al título entre el radicado y la sigla de clase.

from core.scrapers.families.samai import (
    _TITULO_CE_RE,
    _numero_extra_desde_texto,
    _complementar_titulo_con_numero,
)


def test_titulo_ce_re_splits_radicado_and_acronimo():
    match = _TITULO_CE_RE.match("25000-23-37-000-2021-00423-01(NRD)")
    assert match.group(1) == "25000-23-37-000-2021-00423-01"
    assert match.group(2) == "(NRD)"


def test_titulo_ce_re_handles_title_without_acronimo():
    match = _TITULO_CE_RE.match("11001-03-24-000-2026-99999-00")
    assert match.group(1) == "11001-03-24-000-2026-99999-00"
    assert match.group(2) is None


def test_titulo_ce_re_does_not_match_tribunal_administrativo_titles():
    assert _TITULO_CE_RE.match("T_CUND_25001233300020260001200") is None


def test_numero_extra_desde_texto_finds_number_right_after_radicado():
    texto = "Radicación  25000-23-37-000-2021-00423-01 (30146)\nDemandante..."
    assert _numero_extra_desde_texto(texto, "25000-23-37-000-2021-00423-01") == "30146"


def test_numero_extra_desde_texto_returns_none_when_absent():
    texto = "Radicación  25000-23-37-000-2021-00423-01\nDemandante..."
    assert _numero_extra_desde_texto(texto, "25000-23-37-000-2021-00423-01") is None


def test_numero_extra_desde_texto_ignores_unrelated_parenthetical_numbers():
    # El (30146) aparece en el texto pero NO justo después del radicado —
    # no debe confundirse con el dato que buscamos.
    texto = "Ver más en (30146) — Radicación 25000-23-37-000-2021-00423-01 sin número"
    assert _numero_extra_desde_texto(texto, "25000-23-37-000-2021-00423-01") is None


def test_numero_extra_desde_texto_finds_numero_ano_format():
    # Confirmado con datos reales: no siempre es solo dígitos — a veces trae
    # un año pegado con guion (ej. "66001-...-01 (3104-2023)").
    texto = "Radicación:  66001-23-33-000-2017-00141-01 (3104-2023) \nDemandante..."
    assert _numero_extra_desde_texto(texto, "66001-23-33-000-2017-00141-01") == "3104-2023"


def test_numero_extra_desde_texto_strips_dot_from_digits_with_dot_format():
    # Confirmado con datos reales: algunos documentos usan un punto como
    # separador de miles en el PDF (ej. "(74.604)") — se quita, nunca es un
    # decimal en este dominio, para que el título final quede "(74604)".
    texto = "Radicación:  11001-03-15-000-2025-04868-00 (74.604) \nDemandante..."
    assert _numero_extra_desde_texto(texto, "11001-03-15-000-2025-04868-00") == "74604"


def test_numero_extra_desde_texto_ignores_content_without_any_digit():
    # Confirmado con datos reales: a veces lo que aparece entre paréntesis es
    # "(principal)" — indica "cuaderno principal", no es un número de caso, y
    # no debe agregarse al título.
    texto = "Radicación:  11001-03-28-000-2026-00085-00 (principal) \nDemandante..."
    assert _numero_extra_desde_texto(texto, "11001-03-28-000-2026-00085-00") is None


def test_numero_extra_desde_texto_finds_number_when_pdf_uses_spaces_instead_of_dashes():
    # Confirmado con datos reales: el radicado dentro del PDF no siempre usa
    # guion como separador — a veces aparece con espacios entre segmentos
    # ("11001 03 25 000 2025 00135 00"), mismos dígitos exactos, solo cambia
    # el separador (no es un radicado distinto, a diferencia del caso de
    # typos donde los dígitos sí difieren).
    texto = "Radicación: 11001 03 25 000 2025 00135 00 (1017-2025) \nDemandante..."
    assert _numero_extra_desde_texto(texto, "11001-03-25-000-2025-00135-00") == "1017-2025"


def test_complementar_titulo_con_numero_inserts_between_radicado_and_acronimo():
    assert _complementar_titulo_con_numero("25000-23-37-000-2021-00423-01(NRD)", "30146") == (
        "25000-23-37-000-2021-00423-01(30146)(NRD)"
    )


def test_complementar_titulo_con_numero_appends_when_no_acronimo():
    assert _complementar_titulo_con_numero("11001-03-24-000-2026-99999-00", "30146") == (
        "11001-03-24-000-2026-99999-00(30146)"
    )


def test_complementar_titulo_con_numero_is_idempotent_with_acronimo():
    # Calling it twice (e.g. if resolve_unverified_document ever ran on an
    # already-complemented title) must not double-append the number.
    ya_complementado = "25000-23-37-000-2021-00423-01(30146)(NRD)"
    assert _complementar_titulo_con_numero(ya_complementado, "30146") == ya_complementado


def test_complementar_titulo_con_numero_is_idempotent_without_acronimo():
    ya_complementado = "11001-03-24-000-2026-99999-00(30146)"
    assert _complementar_titulo_con_numero(ya_complementado, "30146") == ya_complementado


def test_complementar_titulo_con_numero_is_idempotent_for_numero_ano_format():
    # El guard de "ya complementado" debe reconocer también los formatos
    # número-año y dígitos-con-punto, no solo dígitos puros.
    ya_complementado = "66001-23-33-000-2017-00141-01(3104-2023)(NRD)"
    assert _complementar_titulo_con_numero(ya_complementado, "3104-2023") == ya_complementado


def test_complementar_titulo_con_numero_inserts_numero_ano_format_verbatim():
    assert _complementar_titulo_con_numero("66001-23-33-000-2017-00141-01(NRD)", "3104-2023") == (
        "66001-23-33-000-2017-00141-01(3104-2023)(NRD)"
    )


# --- title_unverified flag y resolve_unverified_document ----------------------


def test_parse_row_flags_title_unverified_only_for_consejo_de_estado():
    row = BeautifulSoup(_ROW_HTML, "html.parser").find("tr")

    ce_scraper = ScrapTribunales("1100103", "Consejo de Estado")
    ce_doc = ce_scraper._parse_row(row, "1100103", "Consejo de Estado", "Sección Primera", "2026-06-15")
    assert ce_doc.title_unverified is True

    tribunal_scraper = ScrapTribunales("2500023", "Tribunal Administrativo de Cundinamarca")
    tribunal_doc = tribunal_scraper._parse_row(
        row, "2500023", "Tribunal Administrativo de Cundinamarca", "Sección Primera", "2026-06-15"
    )
    assert tribunal_doc.title_unverified is False


def test_resolve_unverified_document_appends_extra_number_when_found_on_first_page(monkeypatch):
    monkeypatch.setattr(
        samai_module,
        "_extraer_texto_primera_pagina",
        lambda *_a, **_k: "Radicación  25000-23-37-000-2021-00423-01 (30146)",
    )

    class _Doc:
        title = "25000-23-37-000-2021-00423-01(NRD)"

    doc = _Doc()
    scraper = ScrapTribunales("1100103", "Consejo de Estado")
    scraper.resolve_unverified_document(doc, Path("fake.pdf"), "application/pdf")

    assert doc.title == "25000-23-37-000-2021-00423-01(30146)(NRD)"


def test_resolve_unverified_document_appends_number_when_title_has_no_acronimo(monkeypatch):
    monkeypatch.setattr(
        samai_module,
        "_extraer_texto_primera_pagina",
        lambda *_a, **_k: "Radicación  11001-03-24-000-2026-99999-00 (30146)",
    )

    class _Doc:
        title = "11001-03-24-000-2026-99999-00"

    doc = _Doc()
    scraper = ScrapTribunales("1100103", "Consejo de Estado")
    scraper.resolve_unverified_document(doc, Path("fake.pdf"), "application/pdf")

    assert doc.title == "11001-03-24-000-2026-99999-00(30146)"


def test_resolve_unverified_document_leaves_title_unchanged_when_number_not_found(monkeypatch):
    monkeypatch.setattr(
        samai_module,
        "_extraer_texto_primera_pagina",
        lambda *_a, **_k: "Radicación  25000-23-37-000-2021-00423-01",
    )

    class _Doc:
        title = "25000-23-37-000-2021-00423-01(NRD)"

    doc = _Doc()
    scraper = ScrapTribunales("1100103", "Consejo de Estado")
    scraper.resolve_unverified_document(doc, Path("fake.pdf"), "application/pdf")

    assert doc.title == "25000-23-37-000-2021-00423-01(NRD)"


def test_resolve_unverified_document_is_defensive_about_read_failures(monkeypatch, caplog):
    def _raise(*_a, **_k):
        raise RuntimeError("archivo corrupto")

    monkeypatch.setattr(samai_module, "_extraer_texto_primera_pagina", _raise)

    class _Doc:
        title = "25000-23-37-000-2021-00423-01(NRD)"

    doc = _Doc()
    scraper = ScrapTribunales("1100103", "Consejo de Estado")
    with caplog.at_level("WARNING", logger="core.scrapers.families.samai"):
        scraper.resolve_unverified_document(doc, Path("fake.pdf"), "application/pdf")  # no debe lanzar

    assert doc.title == "25000-23-37-000-2021-00423-01(NRD)"


# --- _fetch: qué fallas de red se reintentan -------------------------------
#
# SAMAI es un sitio ASP.NET viejo, no una API estable — antes solo se
# reintentaba requests.exceptions.Timeout; un corte de conexión a medio
# request o un 5xx de su propio servidor se propagaban de inmediato y esa
# fecha/sección se perdía sin segundo intento.


def test_fetch_retries_after_connection_error_then_succeeds(monkeypatch):
    monkeypatch.setattr(samai_module.time, "sleep", lambda *_a, **_k: None)
    scraper = ScrapTribunales("2500023", "Tribunal Administrativo de Cundinamarca")
    calls = {"n": 0}

    class _Resp:
        def raise_for_status(self):
            return None

    def _fn():
        calls["n"] += 1
        if calls["n"] == 1:
            raise requests.exceptions.ConnectionError("conexión cortada a medio request")
        return _Resp()

    result = scraper._fetch(_fn)

    assert calls["n"] == 2
    assert isinstance(result, _Resp)


def test_fetch_retries_after_5xx_http_error_then_succeeds(monkeypatch):
    monkeypatch.setattr(samai_module.time, "sleep", lambda *_a, **_k: None)
    scraper = ScrapTribunales("2500023", "Tribunal Administrativo de Cundinamarca")
    calls = {"n": 0}

    class _FailResp:
        status_code = 503

        def raise_for_status(self):
            raise requests.exceptions.HTTPError("503 Service Unavailable", response=self)

    class _OkResp:
        def raise_for_status(self):
            return None

    def _fn():
        calls["n"] += 1
        return _FailResp() if calls["n"] == 1 else _OkResp()

    result = scraper._fetch(_fn)

    assert calls["n"] == 2
    assert isinstance(result, _OkResp)


def test_fetch_does_not_retry_a_4xx_http_error():
    # Un 404 es una respuesta real del servidor, no un corte transitorio —
    # reintentarlo no cambiaría el resultado, así que debe propagarse de
    # inmediato sin gastar un segundo intento.
    scraper = ScrapTribunales("2500023", "Tribunal Administrativo de Cundinamarca")
    calls = {"n": 0}

    class _NotFoundResp:
        status_code = 404

        def raise_for_status(self):
            raise requests.exceptions.HTTPError("404 Not Found", response=self)

    def _fn():
        calls["n"] += 1
        return _NotFoundResp()

    with pytest.raises(requests.exceptions.HTTPError):
        scraper._fetch(_fn)

    assert calls["n"] == 1


def test_fetch_still_retries_on_timeout(monkeypatch):
    # Comportamiento preexistente — no debe romperse al ampliar la lista de
    # fallas reintentables.
    monkeypatch.setattr(samai_module.time, "sleep", lambda *_a, **_k: None)
    scraper = ScrapTribunales("2500023", "Tribunal Administrativo de Cundinamarca")
    calls = {"n": 0}

    class _Resp:
        def raise_for_status(self):
            return None

    def _fn():
        calls["n"] += 1
        if calls["n"] == 1:
            raise requests.exceptions.Timeout("se agotó el tiempo")
        return _Resp()

    result = scraper._fetch(_fn)

    assert calls["n"] == 2
    assert isinstance(result, _Resp)


def test_fetch_does_not_retry_twice_on_persistent_connection_error(monkeypatch):
    monkeypatch.setattr(samai_module.time, "sleep", lambda *_a, **_k: None)
    scraper = ScrapTribunales("2500023", "Tribunal Administrativo de Cundinamarca")
    calls = {"n": 0}

    def _fn():
        calls["n"] += 1
        raise requests.exceptions.ConnectionError("conexión cortada a medio request")

    with pytest.raises(requests.exceptions.ConnectionError):
        scraper._fetch(_fn)

    assert calls["n"] == 2


def test_resolve_unverified_document_ignores_tribunal_administrativo_title_format(monkeypatch):
    monkeypatch.setattr(
        samai_module,
        "_extraer_texto_primera_pagina",
        lambda *_a, **_k: "cualquier texto con (30146) en la página",
    )

    class _Doc:
        title = "T_CUND_25001233300020260001200"

    doc = _Doc()
    scraper = ScrapTribunales("2500023", "Tribunal Administrativo de Cundinamarca")
    scraper.resolve_unverified_document(doc, Path("fake.pdf"), "application/pdf")

    assert doc.title == "T_CUND_25001233300020260001200"
