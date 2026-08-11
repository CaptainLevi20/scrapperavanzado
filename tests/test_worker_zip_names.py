from datetime import date
from types import SimpleNamespace

from worker.tasks import _nombres_zip


def _doc(title, storage_key, source_id=1, f_providencia=None, version_no=1):
    return SimpleNamespace(title=title, storage_key=storage_key, source_id=source_id,
                           f_providencia=f_providencia, f_public=None, version_no=version_no)


def test_nombres_zip_desambigua_colisiones():
    docs = [_doc("T-1", "a.pdf"), _doc("T-1", "b.pdf")]
    fam = {1: "constitucional"}
    assert _nombres_zip(docs, fam) == ["T-1.pdf", "T-1 (2).pdf"]


def test_nombres_zip_caso_lleva_fecha():
    docs = [_doc("11001-03-28-000-2026-00300-00", "a.pdf", f_providencia=date(2026, 7, 31))]
    fam = {1: "samai"}
    assert _nombres_zip(docs, fam) == ["11001-03-28-000-2026-00300-00_20260731.pdf"]
