from datetime import date
from types import SimpleNamespace

from core.naming import (
    construir_nombre,
    es_familia_con_actuaciones,
    nombre_archivo_documento,
    nombre_archivo_version,
    nombre_documento,
    nombre_version,
)


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


def _doc(**kw):
    base = dict(title="rad-1", f_providencia=None, f_public=None, version_no=1, storage_key="x.pdf")
    base.update(kw)
    return SimpleNamespace(**base)


def test_nombre_documento_caso_usa_f_providencia():
    d = _doc(title="11001-03-28-000-2026-00300-00", f_providencia=date(2026, 7, 31), version_no=1)
    assert nombre_documento(d, "samai") == "11001-03-28-000-2026-00300-00_20260731"


def test_nombre_documento_caso_respaldo_f_public_cuando_no_hay_providencia():
    d = _doc(title="T_BTA_11001_31_03_022_2019_00814_02", f_providencia=None, f_public=date(2026, 8, 10), version_no=1)
    assert nombre_documento(d, "rama_judicial") == "T_BTA_11001_31_03_022_2019_00814_02_20260810"


def test_nombre_documento_no_caso_ignora_fecha():
    d = _doc(title="T-123-24", f_providencia=date(2026, 7, 31), version_no=1)
    assert nombre_documento(d, "constitucional") == "T-123-24"


def test_nombre_documento_vigente_con_varias_versiones():
    d = _doc(title="T-123-24", version_no=2)
    assert nombre_documento(d, "constitucional") == "T-123-24_v2"


def test_nombre_version_usa_su_propio_numero_y_la_fecha_del_documento():
    d = _doc(title="11001-03-28-000-2026-00300-00", f_providencia=date(2026, 7, 31), version_no=2)
    v = SimpleNamespace(version_no=1, storage_key="v1.pdf")
    assert nombre_version(d, v, "samai") == "11001-03-28-000-2026-00300-00_20260731_v1"


def test_nombre_archivo_agrega_extension_del_storage_key():
    d = _doc(title="T-123-24", version_no=1, storage_key="carpeta/archivo.rtf")
    assert nombre_archivo_documento(d, "constitucional") == "T-123-24.rtf"


def test_nombre_archivo_version_agrega_extension_del_storage_key_de_la_version():
    d = _doc(title="11001-03-28-000-2026-00300-00", f_providencia=date(2026, 7, 31), version_no=2)
    v = SimpleNamespace(version_no=1, storage_key="a/b/v1.pdf")
    assert nombre_archivo_version(d, v, "samai") == "11001-03-28-000-2026-00300-00_20260731_v1.pdf"
