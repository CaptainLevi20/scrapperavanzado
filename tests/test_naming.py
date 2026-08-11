from datetime import date

from core.naming import construir_nombre, es_familia_con_actuaciones


def test_sin_actuaciones_una_version():
    assert construir_nombre("T-123-24", None, es_caso=False, version_no=1, total_versiones=1) == "T-123-24"


def test_sin_actuaciones_republicado():
    assert construir_nombre("T-123-24", None, es_caso=False, version_no=1, total_versiones=2) == "T-123-24_v1"
    assert construir_nombre("T-123-24", None, es_caso=False, version_no=2, total_versiones=2) == "T-123-24_v2"


def test_con_actuaciones():
    n = construir_nombre("11001-03-28-000-2026-00300-00", date(2026, 7, 31), es_caso=True, version_no=1, total_versiones=1)
    assert n == "11001-03-28-000-2026-00300-00_20260731"


def test_con_actuaciones_y_version():
    n = construir_nombre("11001-03-28-000-2026-00300-00", date(2026, 7, 31), es_caso=True, version_no=1, total_versiones=2)
    assert n == "11001-03-28-000-2026-00300-00_20260731_v1"


def test_con_actuaciones_sin_fecha_no_agrega_sufijo_fecha():
    assert construir_nombre("rad-x", None, es_caso=True, version_no=1, total_versiones=1) == "rad-x"


def test_familia_samai_con_titulo_de_radicado_es_caso():
    assert es_familia_con_actuaciones("samai", "11001-03-28-000-2026-00300-00") is True


def test_familia_rama_judicial_con_titulo_de_radicado_es_caso():
    assert es_familia_con_actuaciones("rama_judicial", "T_BTA_11001_31_03_022_2019_00814_02") is True


def test_familia_sin_actuaciones_no_es_caso():
    assert es_familia_con_actuaciones("constitucional", "T-123-24") is False


def test_familia_desconocida_o_none_no_es_caso():
    assert es_familia_con_actuaciones(None, "cualquier-cosa") is False
