from datetime import date
from types import SimpleNamespace

import pytest

from core.naming import (
    codigo_ley_decreto,
    construir_nombre,
    es_codigo_ley_decreto,
    es_familia_con_actuaciones,
    nombre_archivo_documento,
    nombre_archivo_version,
    nombre_documento,
    nombre_version,
)


def test_sin_actuaciones_una_version():
    assert construir_nombre("T-123-24", None, es_caso=False, tiene_actuaciones=False, version_no=1, total_versiones=1) == "T-123-24"


def test_sin_actuaciones_republicado():
    assert construir_nombre("T-123-24", None, es_caso=False, tiene_actuaciones=False, version_no=1, total_versiones=2) == "T-123-24-v1"
    assert construir_nombre("T-123-24", None, es_caso=False, tiene_actuaciones=False, version_no=2, total_versiones=2) == "T-123-24-v2"


def test_caso_con_varias_actuaciones_usa_fecha_completa():
    n = construir_nombre(
        "11001-03-28-000-2026-00300-00", date(2026, 7, 31), es_caso=True, tiene_actuaciones=True,
        version_no=1, total_versiones=1,
    )
    assert n == "11001-03-28-000-2026-00300-00_20260731"


def test_caso_sin_actuaciones_todavia_usa_solo_el_anio():
    """Regresión: un documento con título de caso pero SIN otras actuaciones
    registradas (ej. T_CUND_25269_33_33_001_2025_00051_01, reportado en
    producción) no debe llevar la fecha completa — solo el año, hasta que
    exista una segunda actuación que sí requiera desambiguar por fecha."""
    n = construir_nombre(
        "T_CUND_25269_33_33_001_2025_00051_01", date(2026, 3, 15), es_caso=True, tiene_actuaciones=False,
        version_no=1, total_versiones=1,
    )
    assert n == "T_CUND_25269_33_33_001_2025_00051_01_2026"


def test_caso_con_actuaciones_y_version():
    n = construir_nombre(
        "11001-03-28-000-2026-00300-00", date(2026, 7, 31), es_caso=True, tiene_actuaciones=True,
        version_no=1, total_versiones=2,
    )
    assert n == "11001-03-28-000-2026-00300-00_20260731-v1"


def test_caso_sin_fecha_no_agrega_sufijo_fecha():
    assert construir_nombre("rad-x", None, es_caso=True, tiene_actuaciones=True, version_no=1, total_versiones=1) == "rad-x"
    assert construir_nombre("rad-x", None, es_caso=True, tiene_actuaciones=False, version_no=1, total_versiones=1) == "rad-x"


def test_sin_caso_ignora_actuaciones_y_fecha():
    # es_caso=False: tiene_actuaciones no debería importar — nunca se agrega fecha.
    n = construir_nombre("T-123-24", date(2026, 7, 31), es_caso=False, tiene_actuaciones=True, version_no=1, total_versiones=1)
    assert n == "T-123-24"


def test_familia_samai_con_titulo_de_radicado_es_caso():
    assert es_familia_con_actuaciones("samai", "11001-03-28-000-2026-00300-00") is True


def test_familia_rama_judicial_con_titulo_de_radicado_es_caso():
    assert es_familia_con_actuaciones("rama_judicial", "T_BTA_11001_31_03_022_2019_00814_02") is True


def test_familia_sin_actuaciones_no_es_caso():
    assert es_familia_con_actuaciones("constitucional", "T-123-24") is False


def test_familia_desconocida_o_none_no_es_caso():
    assert es_familia_con_actuaciones(None, "cualquier-cosa") is False


def _doc(**kw):
    base = dict(title="rad-1", f_providencia=None, f_public=None, version_no=1, storage_key="x.pdf")
    base.update(kw)
    return SimpleNamespace(**base)


def test_nombre_documento_caso_con_actuaciones_usa_f_providencia_completa():
    d = _doc(title="11001-03-28-000-2026-00300-00", f_providencia=date(2026, 7, 31), version_no=1)
    assert nombre_documento(d, "samai", tiene_actuaciones=True) == "11001-03-28-000-2026-00300-00_20260731"


def test_nombre_documento_caso_sin_actuaciones_usa_solo_el_anio():
    d = _doc(title="T_CUND_25269_33_33_001_2025_00051_01", f_providencia=date(2026, 3, 15), version_no=1)
    assert nombre_documento(d, "rama_judicial", tiene_actuaciones=False) == "T_CUND_25269_33_33_001_2025_00051_01_2026"


def test_nombre_documento_caso_respaldo_f_public_cuando_no_hay_providencia():
    d = _doc(title="T_BTA_11001_31_03_022_2019_00814_02", f_providencia=None, f_public=date(2026, 8, 10), version_no=1)
    assert nombre_documento(d, "rama_judicial", tiene_actuaciones=True) == "T_BTA_11001_31_03_022_2019_00814_02_20260810"


def test_nombre_documento_no_caso_ignora_fecha():
    d = _doc(title="T-123-24", f_providencia=date(2026, 7, 31), version_no=1)
    assert nombre_documento(d, "constitucional", tiene_actuaciones=False) == "T-123-24"


def test_nombre_documento_vigente_con_varias_versiones():
    d = _doc(title="T-123-24", version_no=2)
    assert nombre_documento(d, "constitucional", tiene_actuaciones=False) == "T-123-24-v2"


def test_nombre_version_usa_su_propio_numero_y_la_fecha_del_documento():
    d = _doc(title="11001-03-28-000-2026-00300-00", f_providencia=date(2026, 7, 31), version_no=2)
    v = SimpleNamespace(version_no=1, storage_key="v1.pdf")
    assert nombre_version(d, v, "samai", tiene_actuaciones=True) == "11001-03-28-000-2026-00300-00_20260731-v1"


def test_nombre_archivo_agrega_extension_del_storage_key():
    d = _doc(title="T-123-24", version_no=1, storage_key="carpeta/archivo.rtf")
    assert nombre_archivo_documento(d, "constitucional", tiene_actuaciones=False) == "T-123-24.rtf"


def test_nombre_archivo_documento_sin_actuaciones_agrega_solo_el_anio():
    d = _doc(title="T_CUND_25269_33_33_001_2025_00051_01", f_providencia=date(2026, 3, 15), storage_key="a/b.pdf")
    assert nombre_archivo_documento(d, "rama_judicial", tiene_actuaciones=False) == "T_CUND_25269_33_33_001_2025_00051_01_2026.pdf"


def test_nombre_archivo_version_agrega_extension_del_storage_key_de_la_version():
    d = _doc(title="11001-03-28-000-2026-00300-00", f_providencia=date(2026, 7, 31), version_no=2)
    v = SimpleNamespace(version_no=1, storage_key="a/b/v1.pdf")
    assert nombre_archivo_version(d, v, "samai", tiene_actuaciones=True) == "11001-03-28-000-2026-00300-00_20260731-v1.pdf"


@pytest.mark.parametrize(
    "letra, numero, anio, esperado",
    [
        ("L", "2277", "2022", "L2277022"),   # ejemplo del usuario
        ("L", "715", "2001", "L0715001"),    # número rellenado a 4 dígitos
        ("D", "111", "1996", "D011196"),     # 1900-1999 -> año 2 dígitos
        ("L", "100", "1993", "L010093"),
        ("D", "6", "2000", "D0006000"),
        ("L", "57", "1888", "L0057888"),     # 1800-1899 -> año 3 dígitos
    ],
)
def test_codigo_ley_decreto_formato(letra, numero, anio, esperado):
    assert codigo_ley_decreto(letra, numero, anio) == esperado


@pytest.mark.parametrize("letra", ["R", "C", "A", "LEST", "ACTOLEG", "CONPES", "DIRECTIVA"])
def test_codigo_ley_decreto_devuelve_none_para_otros_tipos(letra):
    assert codigo_ley_decreto(letra, "123", "2024") is None


@pytest.mark.parametrize("titulo", ["L2277022", "D011196", "L0057888"])
def test_es_codigo_ley_decreto_reconoce_el_formato_nuevo(titulo):
    assert es_codigo_ley_decreto(titulo) is True


@pytest.mark.parametrize("titulo", ["L_MA_2277_2022", "R_ME_0715_2001", "LEST_MI_1751_2015", "", "L", "L12"])
def test_es_codigo_ley_decreto_rechaza_lo_demas(titulo):
    assert es_codigo_ley_decreto(titulo) is False
