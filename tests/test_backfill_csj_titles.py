import pytest

from core.db import repository
from core.backfill_csj_titles import backfill, nuevo_titulo_csj
from core import backfill_csj_titles as bf


@pytest.mark.parametrize(
    "viejo, esperado",
    [
        ("CSJ_SCP_AP2260-2025(62924)_2026", "AP2260-2025(62924)"),
        ("CSJ_SCT_STL5177-2026_2024", "STL5177-2026"),
        ("CSJ_SCC_AC2794-2026 [2024-00858-00]_2024", "AC2794-2026 [2024-00858-00]"),
        # Título de relleno (código no reconocible): se quita el prefijo pero se
        # conserva el año como desempate.
        ("CSJ_SCL_doc_2024", "doc_2024"),
        # Sufijo de versión: se preserva al final.
        ("CSJ_SCP_AP1-2025_2026-v2", "AP1-2025-v2"),
    ],
)
def test_nuevo_titulo_quita_el_prefijo_y_el_anio(viejo, esperado):
    assert nuevo_titulo_csj(viejo) == esperado


@pytest.mark.parametrize("ya_migrado", ["AP2260-2025(62924)", "STL5177-2026", "doc_2024"])
def test_nuevo_titulo_devuelve_none_cuando_ya_no_lleva_prefijo(ya_migrado):
    assert nuevo_titulo_csj(ya_migrado) is None


@pytest.mark.parametrize("raro", ["", "CSJ_XXX_foo_2024", "otra cosa"])
def test_nuevo_titulo_devuelve_none_cuando_no_reconoce_el_formato(raro):
    assert nuevo_titulo_csj(raro) is None


def _fuente_csj(db_session):
    repository.create_source_family(db_session, key="corte_suprema", display_name="Corte Suprema de Justicia")
    return repository.create_source(
        db_session, family_key="corte_suprema", name="CSJ", family_params={}
    )


def test_backfill_actualiza_titulo_y_renombra_el_archivo_conservando_la_carpeta(db_session, monkeypatch):
    source = _fuente_csj(db_session)
    doc = repository.insert_document(
        db_session, doc_id="csj-1", source_id=source.id, title="CSJ_SCP_AP2260-2025(62924)_2026",
        storage_bucket="iurisync-test",
        storage_key="CSJ/SCP/CSJ_SCP_AP2260-2025(62924)_2026.pdf",
    )
    copiados = []
    monkeypatch.setattr(bf.storage_sync, "copy_object", lambda bucket, old, new: copiados.append((old, new)))
    monkeypatch.setattr(bf.storage_sync, "delete_object", lambda *a: None)

    resultado = backfill(db_session)

    refrescado = repository.get_document(db_session, doc.id)
    assert refrescado.title == "AP2260-2025(62924)"
    assert refrescado.storage_key == "CSJ/SCP/AP2260-2025(62924).pdf"
    assert copiados == [
        ("CSJ/SCP/CSJ_SCP_AP2260-2025(62924)_2026.pdf", "CSJ/SCP/AP2260-2025(62924).pdf")
    ]
    assert resultado["documentos_actualizados"] == 1


def test_backfill_es_idempotente(db_session, monkeypatch):
    source = _fuente_csj(db_session)
    repository.insert_document(
        db_session, doc_id="csj-2", source_id=source.id, title="CSJ_SCT_STL5177-2026_2024",
        storage_bucket="iurisync-test", storage_key="CSJ/SCT/CSJ_SCT_STL5177-2026_2024.pdf",
    )
    monkeypatch.setattr(bf.storage_sync, "copy_object", lambda *a: None)
    monkeypatch.setattr(bf.storage_sync, "delete_object", lambda *a: None)

    primera = backfill(db_session)
    segunda = backfill(db_session)

    assert primera["documentos_actualizados"] == 1
    assert segunda["documentos_actualizados"] == 0


def test_backfill_no_toca_documentos_de_otras_fuentes(db_session, monkeypatch):
    _fuente_csj(db_session)
    repository.create_source_family(db_session, key="constitucional", display_name="Corte Constitucional")
    otra = repository.create_source(
        db_session, family_key="constitucional", name="Corte Constitucional", family_params={}
    )
    doc = repository.insert_document(
        db_session, doc_id="otra-1", source_id=otra.id, title="CSJ_SCP_AP1-2025_2026",
        storage_bucket="iurisync-test", storage_key="Corte Constitucional/x/y.rtf",
    )
    monkeypatch.setattr(bf.storage_sync, "copy_object", lambda *a: None)
    monkeypatch.setattr(bf.storage_sync, "delete_object", lambda *a: None)

    resultado = backfill(db_session)

    assert repository.get_document(db_session, doc.id).title == "CSJ_SCP_AP1-2025_2026"
    assert resultado["documentos_actualizados"] == 0
