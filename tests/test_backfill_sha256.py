"""Pruebas del cálculo de la huella digital (SHA-256) de lo ya guardado.

Los documentos descargados desde que existe la huella la traen de una vez; este
cálculo la llena para los que ya estaban en el almacenamiento, y para sus
versiones archivadas. Solo escribe la columna sha256: no toca los archivos.
"""

import hashlib
from datetime import datetime, timezone

from core.backfill_sha256 import calcular_huellas
from core.db import repository
from core.db.models import DocumentVersion


def _fuente(db_session):
    repository.create_source_family(db_session, key="constitucional", display_name="Corte Constitucional")
    return repository.create_source(db_session, family_key="constitucional", name="Corte Constitucional", family_params={})


def _lector(contenidos: dict[str, bytes]):
    def leer(bucket, key):
        if key not in contenidos:
            raise FileNotFoundError(key)
        datos = contenidos[key]
        # en trozos, como llega del almacenamiento
        return (datos[i : i + 3] for i in range(0, len(datos), 3))

    return leer


def test_calcula_la_huella_de_documentos_y_versiones_que_no_la_tienen(db_session):
    fuente = _fuente(db_session)
    doc = repository.insert_document(
        db_session, doc_id="h-1", source_id=fuente.id, title="T-1",
        storage_bucket="b", storage_key="vigente.pdf",
    )
    db_session.add(DocumentVersion(
        document_id=doc.id, storage_bucket="b", storage_key="anterior.pdf",
        downloaded_at=datetime.now(timezone.utc),
    ))
    db_session.commit()

    resumen = calcular_huellas(db_session, _lector({"vigente.pdf": b"nuevo", "anterior.pdf": b"viejo"}))

    assert repository.get_document(db_session, doc.id).sha256 == hashlib.sha256(b"nuevo").hexdigest()
    [version] = repository.list_document_versions(db_session, doc.id)
    assert version.sha256 == hashlib.sha256(b"viejo").hexdigest()
    assert resumen == {"documentos": 1, "versiones": 1, "no_encontrados": 0}


def test_no_recalcula_los_que_ya_tienen_huella(db_session):
    fuente = _fuente(db_session)
    doc = repository.insert_document(
        db_session, doc_id="h-2", source_id=fuente.id, title="T-2",
        storage_bucket="b", storage_key="a.pdf", sha256="ya-calculada",
    )

    def no_debe_leer(bucket, key):
        raise AssertionError("no debía leer el archivo")

    resumen = calcular_huellas(db_session, no_debe_leer)

    assert repository.get_document(db_session, doc.id).sha256 == "ya-calculada"
    assert resumen["documentos"] == 0


def test_un_archivo_que_falta_se_cuenta_y_se_sigue_con_los_demas(db_session):
    fuente = _fuente(db_session)
    falta = repository.insert_document(
        db_session, doc_id="h-3", source_id=fuente.id, title="T-3",
        storage_bucket="b", storage_key="no-existe.pdf",
    )
    ok = repository.insert_document(
        db_session, doc_id="h-4", source_id=fuente.id, title="T-4",
        storage_bucket="b", storage_key="si.pdf",
    )

    resumen = calcular_huellas(db_session, _lector({"si.pdf": b"x"}))

    assert repository.get_document(db_session, falta.id).sha256 is None
    assert repository.get_document(db_session, ok.id).sha256 == hashlib.sha256(b"x").hexdigest()
    assert resumen == {"documentos": 1, "versiones": 0, "no_encontrados": 1}


def test_en_simulacion_no_escribe_nada(db_session):
    fuente = _fuente(db_session)
    doc = repository.insert_document(
        db_session, doc_id="h-5", source_id=fuente.id, title="T-5",
        storage_bucket="b", storage_key="a.pdf",
    )

    resumen = calcular_huellas(db_session, _lector({"a.pdf": b"x"}), simular=True)

    assert repository.get_document(db_session, doc.id).sha256 is None
    assert resumen["documentos"] == 1
