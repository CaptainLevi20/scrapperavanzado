from datetime import date
from types import SimpleNamespace

from worker.tasks import _nombres_zip


def _doc(title, storage_key, source_id=1, f_providencia=None, version_no=1):
    return SimpleNamespace(title=title, storage_key=storage_key, source_id=source_id,
                           f_providencia=f_providencia, f_public=None, version_no=version_no)


def test_nombres_zip_desambigua_colisiones():
    docs = [_doc("T-1", "a.pdf"), _doc("T-1", "b.pdf")]
    fam = {1: "constitucional"}
    assert _nombres_zip(docs, fam, {}) == ["T-1.pdf", "T-1 (2).pdf"]


def test_nombres_zip_caso_con_otra_actuacion_lleva_fecha_completa():
    docs = [_doc("11001-03-28-000-2026-00300-00", "a.pdf", f_providencia=date(2026, 7, 31))]
    fam = {1: "samai"}
    counts = {"11001-03-28-000-2026-00300-00": 2}
    assert _nombres_zip(docs, fam, counts) == ["11001-03-28-000-2026-00300-00_20260731.pdf"]


def test_nombres_zip_caso_sin_otra_actuacion_lleva_solo_el_anio():
    """Regresión: T_SANT_68001_33_33_007_2025_00290_02 (reportado en
    producción) no tiene otra actuación registrada — el ZIP no debe llevar la
    fecha completa en su nombre, solo el año."""
    docs = [_doc("T_SANT_68001_33_33_007_2025_00290_02", "a.pdf", f_providencia=date(2026, 8, 6))]
    fam = {1: "rama_judicial"}
    assert _nombres_zip(docs, fam, {}) == ["T_SANT_68001_33_33_007_2025_00290_02_2026.pdf"]
