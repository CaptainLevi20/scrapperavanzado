import pytest

from core.db import repository
from core.backfill_ministerios_siglas import backfill, nuevo_titulo
from core import backfill_ministerios_siglas as bf


@pytest.mark.parametrize(
    "titulo, vieja, nueva, esperado",
    [
        ("D_MADR_0765_2026", "MADR", "MA", "D_MA_0765_2026"),
        ("CONPES_MDEPORTE_3248_2003", "MDEPORTE", "MDEP", "CONPES_MDEP_3248_2003"),
        ("R_MEN_20664_2026", "MEN", "ME", "R_ME_20664_2026"),
        ("C_MINJUSTICIA_CIR26-0000002_2026", "MINJUSTICIA", "MJ", "C_MJ_CIR26-0000002_2026"),
        # Sufijo de versión: se conserva (queda dentro del "resto").
        ("D_MININT_1028_2026-v2", "MININT", "MI", "D_MI_1028_2026-v2"),
    ],
)
def test_nuevo_titulo_cambia_solo_el_token_de_la_sigla(titulo, vieja, nueva, esperado):
    assert nuevo_titulo(titulo, vieja, nueva) == esperado


@pytest.mark.parametrize(
    "titulo, vieja, nueva",
    [
        ("D_MA_0765_2026", "MADR", "MA"),   # ya migrado
        ("basura sin forma", "MADR", "MA"),
        ("", "MADR", "MA"),
        ("D_MADS_0001_2026", "MADR", "MA"),  # otra sigla, no matchea
    ],
)
def test_nuevo_titulo_devuelve_none_cuando_no_aplica(titulo, vieja, nueva):
    assert nuevo_titulo(titulo, vieja, nueva) is None


def _fuente(db_session, family_key, name):
    repository.create_source_family(db_session, key=family_key, display_name=name)
    return repository.create_source(db_session, family_key=family_key, name=name, family_params={})


def test_backfill_actualiza_titulo_y_renombra_conservando_la_carpeta(db_session, monkeypatch):
    source = _fuente(db_session, "madr", "Ministerio de Agricultura y Desarrollo Rural")
    doc = repository.insert_document(
        db_session, doc_id="madr-1", source_id=source.id, title="D_MADR_0765_2026",
        storage_bucket="iurisync-test",
        storage_key="Ministerio de Agricultura y Desarrollo Rural/2026-07-15/Decreto/D_MADR_0765_2026.pdf",
    )
    copiados = []
    monkeypatch.setattr(bf.storage_sync, "copy_object", lambda bucket, old, new: copiados.append((old, new)))
    monkeypatch.setattr(bf.storage_sync, "delete_object", lambda *a: None)

    resultado = backfill(db_session)

    refrescado = repository.get_document(db_session, doc.id)
    assert refrescado.title == "D_MA_0765_2026"
    assert refrescado.storage_key == (
        "Ministerio de Agricultura y Desarrollo Rural/2026-07-15/Decreto/D_MA_0765_2026.pdf"
    )
    assert copiados == [
        (
            "Ministerio de Agricultura y Desarrollo Rural/2026-07-15/Decreto/D_MADR_0765_2026.pdf",
            "Ministerio de Agricultura y Desarrollo Rural/2026-07-15/Decreto/D_MA_0765_2026.pdf",
        )
    ]
    assert resultado["madr"]["documentos_actualizados"] == 1


def test_backfill_es_idempotente(db_session, monkeypatch):
    source = _fuente(db_session, "mintrabajo", "Ministerio del Trabajo")
    repository.insert_document(
        db_session, doc_id="mt-1", source_id=source.id, title="D_MINTRABAJO_1040_2026",
        storage_bucket="iurisync-test", storage_key="Ministerio del Trabajo/2026-01-01/Decreto/D_MINTRABAJO_1040_2026.pdf",
    )
    monkeypatch.setattr(bf.storage_sync, "copy_object", lambda *a: None)
    monkeypatch.setattr(bf.storage_sync, "delete_object", lambda *a: None)

    primera = backfill(db_session)
    segunda = backfill(db_session)

    assert primera["mintrabajo"]["documentos_actualizados"] == 1
    assert segunda["mintrabajo"]["documentos_actualizados"] == 0


def test_backfill_no_toca_familias_sin_cambio_ni_otras_fuentes(db_session, monkeypatch):
    minambiente = _fuente(db_session, "minambiente", "Ministerio de Ambiente y Desarrollo Sostenible")
    constitucional = _fuente(db_session, "constitucional", "Corte Constitucional")
    d_amb = repository.insert_document(
        db_session, doc_id="amb-1", source_id=minambiente.id, title="D_MADS_0001_2026",
        storage_bucket="iurisync-test", storage_key="x/D_MADS_0001_2026.pdf",
    )
    d_cc = repository.insert_document(
        db_session, doc_id="cc-1", source_id=constitucional.id, title="ST-065-24",
        storage_bucket="iurisync-test", storage_key="y/ST-065-24.rtf",
    )
    monkeypatch.setattr(bf.storage_sync, "copy_object", lambda *a: None)
    monkeypatch.setattr(bf.storage_sync, "delete_object", lambda *a: None)

    backfill(db_session)

    assert repository.get_document(db_session, d_amb.id).title == "D_MADS_0001_2026"
    assert repository.get_document(db_session, d_cc.id).title == "ST-065-24"


def test_backfill_omite_documentos_que_colisionarian_en_la_misma_clave(db_session, monkeypatch):
    # Dos documentos madr con el mismo título y la misma ruta (mismo decreto
    # listado en dos URLs distintas -> dos doc_id, mismo storage_key): ambos
    # calcularían la misma clave nueva. Renombrar los dos haría que el segundo
    # copy_object sobrescriba el archivo del primero.
    source = _fuente(db_session, "madr", "Ministerio de Agricultura y Desarrollo Rural")
    key_col = "Ministerio de Agricultura y Desarrollo Rural/2026-07-15/Decreto/D_MADR_0765_2026.pdf"
    a = repository.insert_document(
        db_session, doc_id="madr-col-a", source_id=source.id, title="D_MADR_0765_2026",
        storage_bucket="iurisync-test", storage_key=key_col,
    )
    b = repository.insert_document(
        db_session, doc_id="madr-col-b", source_id=source.id, title="D_MADR_0765_2026",
        storage_bucket="iurisync-test", storage_key=key_col,
    )
    ok = repository.insert_document(
        db_session, doc_id="madr-ok", source_id=source.id, title="R_MADR_0179_2026",
        storage_bucket="iurisync-test",
        storage_key="Ministerio de Agricultura y Desarrollo Rural/2026-07-15/Resolución/R_MADR_0179_2026.pdf",
    )
    copiados = []
    monkeypatch.setattr(bf.storage_sync, "copy_object", lambda bucket, old, new: copiados.append((old, new)))
    monkeypatch.setattr(bf.storage_sync, "delete_object", lambda *a: None)

    resultado = backfill(db_session)

    assert repository.get_document(db_session, a.id).title == "D_MADR_0765_2026"
    assert repository.get_document(db_session, b.id).title == "D_MADR_0765_2026"
    assert resultado["madr"]["colisiones_omitidas"] == 2
    assert repository.get_document(db_session, ok.id).title == "R_MA_0179_2026"
    assert resultado["madr"]["documentos_actualizados"] == 1
    assert copiados == [
        (
            "Ministerio de Agricultura y Desarrollo Rural/2026-07-15/Resolución/R_MADR_0179_2026.pdf",
            "Ministerio de Agricultura y Desarrollo Rural/2026-07-15/Resolución/R_MA_0179_2026.pdf",
        )
    ]
