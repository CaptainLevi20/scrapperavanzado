from core.scrapers.families.supersolidaria import (
    _anio_de_h2,
    _es_anexo,
    _extension_del_href,
    _fecha_concepto,
    _num_seccion,
    _prefijo_fecha_archivo,
    _safe_title,
    _titulo,
    _titulo_concepto,
)


def test_extension_del_href():
    assert _extension_del_href("/sites/default/files/data/20260520_circular_externa_101.pdf") == "pdf"
    assert _extension_del_href("/x/y/2._anexo.docx?a=1") == "docx"
    assert _extension_del_href("/x/y/matriz.XLSX") == "xlsx"
    assert _extension_del_href("/es/content/algo") == ""


def test_es_anexo():
    assert _es_anexo("Anexo - Circular Externa N° 101") is True
    assert _es_anexo("ANEXO técnico") is True
    assert _es_anexo("Matriz de Comentarios - Circular N° 101") is True
    assert _es_anexo("Matriz de Observaciones") is True
    assert _es_anexo("Circular Externa N° 101") is False
    assert _es_anexo("") is False


def test_num_seccion_resolucion_radicado_largo_ultimos_6():
    assert _num_seccion("R", "Resolución 2025430007935 del 30 de diciembre de 2025") == 7935
    assert _num_seccion("R", "Resolución 2026113001925 del 26 de marzo de 2026") == 1925


def test_num_seccion_resolucion_forma_corta():
    assert _num_seccion("R", "Resolución 745 de 2003") == 745


def test_num_seccion_circulares_y_cartas():
    assert _num_seccion("CE", "Circular Externa N° 102") == 102
    assert _num_seccion("CE", "Anexo - Circular Externa N° 101") == 101
    assert _num_seccion("CC", "Carta Circular N° 37") == 37
    assert _num_seccion("CJ", "Circular conjunta No. 067") == 67


def test_num_seccion_none_cuando_no_hay():
    assert _num_seccion("CJ", "ministro_del_trabajo_y_superintendente_de_la_economia_solidaria") is None
    assert _num_seccion("CE", "Circular Externa sin numero") is None


def test_anio_de_h2():
    assert _anio_de_h2("Circulares Externas 2024") == 2024
    assert _anio_de_h2("CIRCULARES EXTERNAS 2022") == 2022
    assert _anio_de_h2("\xa0CIRCULARES EXTERNAS 2021") == 2021
    assert _anio_de_h2("Resoluciones Generales 2016") == 2016
    assert _anio_de_h2("Cartas Circulares 2015") == 2015
    assert _anio_de_h2("Resoluciones Generales") is None
    assert _anio_de_h2("Otra cosa 2020") is None


def test_prefijo_fecha_archivo():
    assert _prefijo_fecha_archivo("/sites/default/files/data/20260520_circular_externa_101.pdf") == "2026-05-20"
    assert _prefijo_fecha_archivo("/x/circular-conjunta-nov-09_0.pdf") is None
    assert _prefijo_fecha_archivo("/x/20261332_algo.pdf") is None  # mes/día inválidos


def test_fecha_concepto():
    assert _fecha_concepto("/x/20260821_concepto_20261100232001.pdf", None) == "2026-08-21"
    assert _fecha_concepto("/x/concept_uni.pdf", "2025-05-16T00:00:00Z") == "2025-05-16"
    assert _fecha_concepto("/x/concept_uni.pdf", None) is None


def test_titulo_verificado_y_anexo():
    assert _titulo("CE", "Circular Externa", "Circular Externa N° 102", "2026", False) == ("CE_SES_0102_2026", False)
    assert _titulo("CE", "Circular Externa", "Anexo - Circular Externa N° 101", "2026", True) == ("CE_SES_0101_2026_A01", False)
    assert _titulo("R", "Resolución", "Resolución 2025430007935 del 30 de diciembre de 2025", "2025", False) == ("R_SES_7935_2025", False)


def test_titulo_fallback_sin_numero():
    t, unv = _titulo("CJ", "Circular Conjunta", "ministro_del_trabajo_y_superintendente", "2009", False)
    assert unv is True and t == "ministro_del_trabajo_y_superintendente"
    assert _titulo("CE", "Circular Externa", "   ", "2020", False) == ("documento", True)


def test_titulo_concepto():
    assert _titulo_concepto("/x/20260821_concepto_20261100232001.pdf", "irrelevante", "2026") == ("CTO_SES_20261100232001_2026", False)
    t, unv = _titulo_concepto("/x/20250516_concept_uni.pdf", "Concepto Unificado - Tratamiento", "2025")
    assert unv is True and t == "Concepto Unificado - Tratamiento"


def test_safe_title():
    assert _safe_title('a/b:c"  .') == "a-b-c-"
    assert len(_safe_title("z" * 200)) == 120
