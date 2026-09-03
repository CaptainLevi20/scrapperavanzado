import pytest

from core.db import repository
from core.backfill_leyes_decretos import backfill, nuevo_titulo_ley_decreto
from core import backfill_leyes_decretos as bf


@pytest.mark.parametrize(
    "viejo, esperado",
    [
        ("L_MA_2277_2022", "L2277022"),
        ("D_ME_0715_2001", "D0715001"),
        ("D_MDEP_0006_1996", "D000696"),
        ("L_MVCT_0100_1993", "L010093"),
    ],
)
def test_nuevo_titulo_convierte_ley_decreto(viejo, esperado):
    assert nuevo_titulo_ley_decreto(viejo) == esperado


@pytest.mark.parametrize(
    "titulo",
    ["R_MA_0100_2023", "C_MJ_CIR26-0000002_2026", "LEST_MI_1751_2015", "L2277022", "", "basura"],
)
def test_nuevo_titulo_devuelve_none_para_lo_demas(titulo):
    assert nuevo_titulo_ley_decreto(titulo) is None


def _fuente(db_session, family_key, name):
    repository.create_source_family(db_session, key=family_key, display_name=name)
    return repository.create_source(db_session, family_key=family_key, name=name, family_params={})


def test_backfill_renombra_ley_decreto_y_deja_resoluciones_intactas(db_session, monkeypatch):
    madr = _fuente(db_session, "madr", "Ministerio de Agricultura y Desarrollo Rural")
    ley = repository.insert_document(
        db_session, doc_id="ley-1", source_id=madr.id, title="L_MA_2277_2022",
        storage_bucket="iurisync-test",
        storage_key="Ministerio de Agricultura y Desarrollo Rural/2022-12-13/Ley/L_MA_2277_2022.pdf",
    )
    reso = repository.insert_document(
        db_session, doc_id="reso-1", source_id=madr.id, title="R_MA_0100_2023",
        storage_bucket="iurisync-test",
        storage_key="Ministerio de Agricultura y Desarrollo Rural/2023-01-01/Resolución/R_MA_0100_2023.pdf",
    )
    copiados = []
    monkeypatch.setattr(bf.storage_sync, "copy_object", lambda b, o, n: copiados.append((o, n)))
    monkeypatch.setattr(bf.storage_sync, "delete_object", lambda *a: None)
    monkeypatch.setattr(bf, "_borrar_objeto", lambda *a: None)

    resultado = backfill(db_session)

    assert repository.get_document(db_session, ley.id).title == "L2277022"
    assert repository.get_document(db_session, ley.id).storage_key == (
        "Ministerio de Agricultura y Desarrollo Rural/2022-12-13/Ley/L2277022.pdf"
    )
    assert repository.get_document(db_session, reso.id).title == "R_MA_0100_2023"  # sin cambios
    assert resultado["renombrados"] == 1


def test_backfill_deduplica_entre_ministerios_y_conserva_el_archivo_mas_grande(db_session, monkeypatch):
    madr = _fuente(db_session, "madr", "Ministerio de Agricultura y Desarrollo Rural")
    minamb = _fuente(db_session, "minambiente", "Ministerio de Ambiente y Desarrollo Sostenible")
    chica = repository.insert_document(
        db_session, doc_id="chica", source_id=madr.id, title="L_MA_2277_2022",
        storage_bucket="iurisync-test", storage_key="madr/L_MA_2277_2022.pdf", file_size_bytes=100,
    )
    grande = repository.insert_document(
        db_session, doc_id="grande", source_id=minamb.id, title="L_MADS_2277_2022",
        storage_bucket="iurisync-test", storage_key="minamb/L_MADS_2277_2022.pdf", file_size_bytes=500,
    )
    objetos_borrados = []
    monkeypatch.setattr(bf.storage_sync, "copy_object", lambda *a: None)
    monkeypatch.setattr(bf.storage_sync, "delete_object", lambda *a: None)
    monkeypatch.setattr(bf, "_borrar_objeto", lambda bucket, key: objetos_borrados.append(key))

    resultado = backfill(db_session)

    assert repository.get_document(db_session, grande.id) is not None
    assert repository.get_document(db_session, grande.id).title == "L2277022"
    assert repository.get_document(db_session, chica.id) is None  # borrada
    assert resultado["duplicados_borrados"] == 1
    assert any("L_MA_2277_2022.pdf" in k or "L2277022" in k for k in objetos_borrados)


def test_backfill_desempata_por_id_menor_cuando_los_tamanos_empatan_y_null_pierde(db_session, monkeypatch):
    madr = _fuente(db_session, "madr", "Ministerio de Agricultura y Desarrollo Rural")
    minamb = _fuente(db_session, "minambiente", "Ministerio de Ambiente y Desarrollo Sostenible")
    mincit = _fuente(db_session, "mincit", "Ministerio de Comercio, Industria y Turismo")
    a = repository.insert_document(
        db_session, doc_id="a", source_id=madr.id, title="D_MA_0009_2020",
        storage_bucket="iurisync-test", storage_key="a/D_MA_0009_2020.pdf", file_size_bytes=None,
    )
    b = repository.insert_document(
        db_session, doc_id="b", source_id=minamb.id, title="D_MADS_0009_2020",
        storage_bucket="iurisync-test", storage_key="b/D_MADS_0009_2020.pdf", file_size_bytes=200,
    )
    c = repository.insert_document(
        db_session, doc_id="c", source_id=mincit.id, title="D_MCIT_0009_2020",
        storage_bucket="iurisync-test", storage_key="c/D_MCIT_0009_2020.pdf", file_size_bytes=200,
    )
    monkeypatch.setattr(bf.storage_sync, "copy_object", lambda *a: None)
    monkeypatch.setattr(bf.storage_sync, "delete_object", lambda *a: None)
    monkeypatch.setattr(bf, "_borrar_objeto", lambda *a: None)

    backfill(db_session)

    # NULL (a) pierde; entre b y c (empatan en 200) gana el id menor (b).
    assert repository.get_document(db_session, a.id) is None
    assert repository.get_document(db_session, c.id) is None
    assert repository.get_document(db_session, b.id) is not None


def test_backfill_no_toca_otras_familias(db_session, monkeypatch):
    _fuente(db_session, "madr", "Ministerio de Agricultura y Desarrollo Rural")
    cc = _fuente(db_session, "constitucional", "Corte Constitucional")
    d = repository.insert_document(
        db_session, doc_id="cc-1", source_id=cc.id, title="ST-065-24",
        storage_bucket="iurisync-test", storage_key="cc/ST-065-24.rtf",
    )
    monkeypatch.setattr(bf.storage_sync, "copy_object", lambda *a: None)
    monkeypatch.setattr(bf.storage_sync, "delete_object", lambda *a: None)
    monkeypatch.setattr(bf, "_borrar_objeto", lambda *a: None)

    backfill(db_session)

    assert repository.get_document(db_session, d.id).title == "ST-065-24"


def test_backfill_guarda_de_colision_intra_fuente(db_session, monkeypatch):
    madr = _fuente(db_session, "madr", "Ministerio de Agricultura y Desarrollo Rural")
    key = "Ministerio de Agricultura y Desarrollo Rural/2022-12-13/Ley/L_MA_2277_2022.pdf"
    a = repository.insert_document(
        db_session, doc_id="col-a", source_id=madr.id, title="L_MA_2277_2022",
        storage_bucket="iurisync-test", storage_key=key,
    )
    b = repository.insert_document(
        db_session, doc_id="col-b", source_id=madr.id, title="L_MA_2277_2022",
        storage_bucket="iurisync-test", storage_key=key,
    )
    monkeypatch.setattr(bf.storage_sync, "copy_object", lambda *a: (_ for _ in ()).throw(AssertionError("no renombrar en colisión")))
    monkeypatch.setattr(bf.storage_sync, "delete_object", lambda *a: None)
    monkeypatch.setattr(bf, "_borrar_objeto", lambda *a: None)

    resultado = backfill(db_session)

    assert repository.get_document(db_session, a.id).title == "L_MA_2277_2022"
    assert repository.get_document(db_session, b.id).title == "L_MA_2277_2022"
    assert resultado["colisiones_omitidas"] == 2
