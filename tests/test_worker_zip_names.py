from datetime import date
from types import SimpleNamespace

from worker.tasks import _entradas_zip


def _doc(title, storage_key, source_id=1, f_providencia=None, f_public=None, tipo=None,
         version_no=1, doc_id=1, storage_bucket="bucket"):
    return SimpleNamespace(id=doc_id, title=title, storage_key=storage_key, storage_bucket=storage_bucket,
                           source_id=source_id, f_providencia=f_providencia, f_public=f_public,
                           tipo=tipo, version_no=version_no)


def _version(storage_key, version_no, storage_bucket="bucket"):
    return SimpleNamespace(storage_key=storage_key, storage_bucket=storage_bucket, version_no=version_no,
                           file_size_bytes=None)


def _arcnames(docs, fam, counts, fuentes, versions_by_doc=None):
    """Solo las rutas dentro del ZIP — es lo que estas pruebas verifican."""
    return [e.arcname for e in _entradas_zip(docs, versions_by_doc or {}, fam, counts, fuentes)]


def test_entradas_zip_incluye_carpeta_fuente_fecha_tipo():
    docs = [_doc("T-1", "a.pdf", f_public=date(2026, 8, 15), tipo="Sentencia")]
    fam = {1: "constitucional"}
    fuentes = {1: "Corte Constitucional"}
    assert _arcnames(docs, fam, {}, fuentes) == ["Corte Constitucional/2026-08-15/Sentencia/T-1.pdf"]


def test_entradas_zip_usa_respaldos_cuando_faltan_datos():
    docs = [_doc("T-1", "a.pdf", f_public=None, tipo=None)]
    fam = {1: "constitucional"}
    assert _arcnames(docs, fam, {}, {}) == ["Sin fuente/Sin fecha/Sin tipo/T-1.pdf"]


def test_entradas_zip_desambigua_colisiones_dentro_de_la_misma_carpeta():
    docs = [
        _doc("T-1", "a.pdf", f_public=date(2026, 8, 15), tipo="Sentencia", doc_id=1),
        _doc("T-1", "b.pdf", f_public=date(2026, 8, 15), tipo="Sentencia", doc_id=2),
    ]
    fam = {1: "constitucional"}
    fuentes = {1: "Corte Constitucional"}
    assert _arcnames(docs, fam, {}, fuentes) == [
        "Corte Constitucional/2026-08-15/Sentencia/T-1.pdf",
        "Corte Constitucional/2026-08-15/Sentencia/T-1 (2).pdf",
    ]


def test_entradas_zip_misma_base_en_carpetas_distintas_no_se_desambigua():
    """Dos documentos con el mismo nombre canónico pero de fuentes distintas
    caen en carpetas distintas — no hace falta (ni debe) agregarles '(2)'."""
    docs = [
        _doc("T-1", "a.pdf", source_id=1, f_public=date(2026, 8, 15), tipo="Sentencia", doc_id=1),
        _doc("T-1", "b.pdf", source_id=2, f_public=date(2026, 8, 15), tipo="Sentencia", doc_id=2),
    ]
    fam = {1: "constitucional", 2: "constitucional"}
    fuentes = {1: "Corte Constitucional", 2: "Consejo de Estado"}
    assert _arcnames(docs, fam, {}, fuentes) == [
        "Corte Constitucional/2026-08-15/Sentencia/T-1.pdf",
        "Consejo de Estado/2026-08-15/Sentencia/T-1.pdf",
    ]


def test_entradas_zip_caso_con_otra_actuacion_lleva_fecha_completa():
    docs = [_doc("11001-03-28-000-2026-00300-00", "a.pdf", f_providencia=date(2026, 7, 31),
                  f_public=date(2026, 7, 31), tipo="Auto")]
    fam = {1: "samai"}
    fuentes = {1: "Consejo de Estado"}
    counts = {"11001-03-28-000-2026-00300-00": 2}
    assert _arcnames(docs, fam, counts, fuentes) == [
        "Consejo de Estado/2026-07-31/Auto/11001-03-28-000-2026-00300-00_20260731.pdf"
    ]


def test_entradas_zip_caso_sin_otra_actuacion_lleva_solo_el_anio():
    """Regresión: T_SANT_68001_33_33_007_2025_00290_02 (reportado en
    producción) no tiene otra actuación registrada — el ZIP no debe llevar la
    fecha completa en su nombre, solo el año."""
    docs = [_doc("T_SANT_68001_33_33_007_2025_00290_02", "a.pdf", f_providencia=date(2026, 8, 6),
                  f_public=date(2026, 8, 6), tipo="Auto")]
    fam = {1: "rama_judicial"}
    fuentes = {1: "Rama Judicial"}
    assert _arcnames(docs, fam, {}, fuentes) == [
        "Rama Judicial/2026-08-06/Auto/T_SANT_68001_33_33_007_2025_00290_02_2026.pdf"
    ]


def test_entradas_zip_versiones_archivadas_van_en_la_misma_carpeta_con_sufijo_v():
    """Cada versión archivada de un documento útil entra al ZIP en la misma
    carpeta Fuente/Fecha/Tipo que el vigente, con el nombre canónico de versión
    ('-v{n}'). El vigente ya es la versión más alta."""
    docs = [_doc("T-1", "vig.pdf", f_public=date(2026, 8, 15), tipo="Sentencia", version_no=3, doc_id=7)]
    fam = {1: "constitucional"}
    fuentes = {1: "Corte Constitucional"}
    versions_by_doc = {7: [_version("v2.pdf", 2), _version("v1.pdf", 1)]}
    entradas = _entradas_zip(docs, versions_by_doc, fam, {}, fuentes)
    assert [(e.arcname, e.storage_key, e.document_id) for e in entradas] == [
        ("Corte Constitucional/2026-08-15/Sentencia/T-1-v3.pdf", "vig.pdf", 7),
        ("Corte Constitucional/2026-08-15/Sentencia/T-1-v2.pdf", "v2.pdf", 7),
        ("Corte Constitucional/2026-08-15/Sentencia/T-1-v1.pdf", "v1.pdf", 7),
    ]
