from datetime import date

from core.db import repository
from core import backfill_tribunales_titulos as bf
from core.backfill_tribunales_titulos import backfill


def _tribunal(db_session, dept_code="68", nombre="Tribunal Superior de Santander"):
    if repository.get_source_family(db_session, "rama_judicial") is None:
        repository.create_source_family(db_session, key="rama_judicial", display_name="Rama Judicial")
    return repository.create_source(
        db_session, family_key="rama_judicial", name=nombre,
        family_params={"dept_code": dept_code, "dept_name": nombre, "entidad_id": "22"},
    )


def _doc(db_session, source, doc_id, title, key=None, content_type="application/pdf"):
    return repository.insert_document(
        db_session, doc_id=doc_id, source_id=source.id, title=title, f_public=date(2026, 9, 29),
        storage_bucket="iurisync-test", content_type=content_type,
        storage_key=key or f"Tribunal Superior de Santander/LABORAL/2026-09-29/{title}.pdf",
    )


def _sin_minio(monkeypatch, texto_pdf=None):
    copiados = []
    monkeypatch.setattr(bf.storage_sync, "copy_object", lambda bucket, old, new: copiados.append((old, new)))
    monkeypatch.setattr(bf.storage_sync, "delete_object", lambda *a: None)
    leidos = []

    def _descargar(bucket, key, local):
        leidos.append(key)
        local.write_bytes(b"%PDF")

    monkeypatch.setattr(bf, "download_file", _descargar)
    monkeypatch.setattr(bf, "_extraer_texto_primera_pagina", lambda p: texto_pdf or "")
    return copiados, leidos


def test_corrige_por_el_nombre_sin_leer_el_pdf(db_session, monkeypatch):
    source = _tribunal(db_session, "41", "Tribunal Superior del Huila")
    doc = _doc(db_session, source, "h1", "19. 41001-31-05-002-2021-00031-01 AutoAceptaDesistimiento Dr Charry")
    copiados, leidos = _sin_minio(monkeypatch)

    r = backfill(db_session)

    assert repository.get_document(db_session, doc.id).title == "T_HUIL_41001_31_05_002_2021_00031_01"
    assert r["por_nombre"] == 1 and r["por_pdf"] == 0
    assert leidos == []
    assert len(copiados) == 1  # el archivo se renombra al nombre canónico


def test_corrige_por_el_pdf_y_llena_la_fecha_de_providencia(db_session, monkeypatch):
    source = _tribunal(db_session)
    doc = _doc(db_session, source, "s1", "77.726 Admite Apelacion")
    _sin_minio(
        monkeypatch,
        "Bucaramanga, veintinueve (29) de septiembre de dos mil veintiséis (2026) RADICACIÓN: 68001-31-05-005-2023-00227-01.",
    )

    r = backfill(db_session)

    refrescado = repository.get_document(db_session, doc.id)
    assert refrescado.title == "T_SANT_68001_31_05_005_2023_00227_01"
    assert refrescado.f_providencia == date(2026, 9, 29)
    assert r["por_pdf"] == 1


def test_no_toca_listas_juzgados_ni_titulos_ya_correctos(db_session, monkeypatch):
    tribunal = _tribunal(db_session)
    juzgado = _tribunal(db_session, "", "Juzgados Civiles del Circuito")
    lista = _doc(db_session, tribunal, "l1", "ESTADO 157 DEL 30 DE SEPTIEMBRE 2026")
    del_juzgado = _doc(db_session, juzgado, "j1", "Auto 68001-31-03-007-2024-00065-02")
    correcto = _doc(db_session, tribunal, "c1", "T_SANT_68001_31_03_007_2024_00065_02")
    _, leidos = _sin_minio(monkeypatch, "Radicado: 68001310300720240006502")

    r = backfill(db_session)

    assert repository.get_document(db_session, lista.id).title == "ESTADO 157 DEL 30 DE SEPTIEMBRE 2026"
    assert repository.get_document(db_session, del_juzgado.id).title == "Auto 68001-31-03-007-2024-00065-02"
    assert repository.get_document(db_session, correcto.id).title == "T_SANT_68001_31_03_007_2024_00065_02"
    assert r["revisados"] == 1  # solo la lista (los juzgados y los ya correctos ni se miran)
    assert leidos == []  # a la lista no se le lee el PDF


def test_no_lee_archivos_que_no_son_pdf(db_session, monkeypatch):
    source = _tribunal(db_session)
    _doc(db_session, source, "d1", "77.726 Admite Apelacion", key="x/77.726 Admite Apelacion.docx",
         content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document")
    _, leidos = _sin_minio(monkeypatch, "Radicado: 68001310300720240006502")

    r = backfill(db_session)

    assert leidos == [] and r["sin_cambio"] == 1


def test_simular_no_cambia_nada(db_session, monkeypatch):
    source = _tribunal(db_session)
    doc = _doc(db_session, source, "s2", "2024-00065-02")
    copiados, _ = _sin_minio(monkeypatch, "Radicado: 68001310300720240006502")

    r = backfill(db_session, simular=True)

    assert r["por_pdf"] == 1
    assert repository.get_document(db_session, doc.id).title == "2024-00065-02"
    assert copiados == []


def test_sin_pdf_solo_corrige_por_el_nombre(db_session, monkeypatch):
    source = _tribunal(db_session)
    doc = _doc(db_session, source, "s3", "2024-00065-02")
    _, leidos = _sin_minio(monkeypatch, "Radicado: 68001310300720240006502")

    r = backfill(db_session, leer_pdf=False)

    assert repository.get_document(db_session, doc.id).title == "2024-00065-02"
    assert leidos == [] and r["sin_cambio"] == 1


def test_es_idempotente(db_session, monkeypatch):
    source = _tribunal(db_session)
    _doc(db_session, source, "s4", "2024-00065-02")
    _sin_minio(monkeypatch, "Radicado: 68001310300720240006502")

    primera = backfill(db_session)
    segunda = backfill(db_session)

    assert primera["por_pdf"] == 1
    assert segunda["revisados"] == 0


def test_agrupa_dos_actuaciones_del_mismo_radicado_sin_pisar_archivos(db_session, monkeypatch):
    # Dos autos del mismo proceso, en días distintos: quedan con el mismo
    # título (son actuaciones del mismo caso) y cada archivo con su propio
    # nombre (storage_sync les agrega la fecha).
    source = _tribunal(db_session)
    a = _doc(db_session, source, "a1", "AutoAdmite 68001-31-03-007-2024-00065-02",
             key="T/LABORAL/2026-09-01/Notificaciones/AutoAdmite.pdf")
    b = _doc(db_session, source, "a2", "AutoDecide 68001-31-03-007-2024-00065-02",
             key="T/LABORAL/2026-09-20/Notificaciones/AutoDecide.pdf")
    copiados, _ = _sin_minio(monkeypatch)

    backfill(db_session)

    ka = repository.get_document(db_session, a.id)
    kb = repository.get_document(db_session, b.id)
    assert ka.title == kb.title == "T_SANT_68001_31_03_007_2024_00065_02"
    assert ka.storage_key != kb.storage_key
    assert len({nuevo for _, nuevo in copiados}) == len(copiados)
