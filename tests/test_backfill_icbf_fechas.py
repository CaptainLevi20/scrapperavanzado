import io
import zipfile
from datetime import date

from core import backfill_icbf_fechas as bf
from core.backfill_icbf_fechas import backfill, doc_id_nuevo
from core.db import repository
from core.models import RawDocModel
from core.utils import compute_doc_id, make_doc_id

_URL = "https://www.icbf.gov.co/sites/default/files/normas/CONCEPTO%2010%20DE%202026.docx"


def _docx(encabezado: str) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr(
            "word/document.xml",
            '<w:document xmlns:w="w"><w:body><w:p><w:r><w:t>' + encabezado + "</w:t></w:r></w:p></w:body></w:document>",
        )
    return buf.getvalue()


def _fuente(db_session):
    if repository.get_source_family(db_session, "icbf") is None:
        repository.create_source_family(db_session, key="icbf", display_name="ICBF")
    return repository.create_source(db_session, family_key="icbf", name="Instituto Colombiano de Bienestar Familiar", family_params={})


def _concepto(db_session, source, title="CTO_ICBF_0010_2026", url=_URL, f_public=date(2026, 1, 1)):
    # Como lo guardó la versión anterior: doc_id con la fecha de relleno.
    return repository.insert_document(
        db_session, doc_id=make_doc_id(url, f_public.isoformat()), source_id=source.id, title=title,
        f_public=f_public, f_providencia=f_public, source_url=url, storage_bucket="iurisync-test",
        storage_key=f"Instituto Colombiano de Bienestar Familiar/2026-01-01/Concepto/{title}.docx",
    )


def _archivos(monkeypatch, por_key: dict):
    def _descargar(bucket, key, local):
        local.write_bytes(por_key[key])

    monkeypatch.setattr(bf, "download_file", _descargar)


def test_doc_id_nuevo_es_el_de_la_ingesta():
    doc = RawDocModel(source="x", link={"url": _URL, "method": "GET"}, title="t", tipo="Concepto", f_public="2026-07-30")
    assert doc_id_nuevo(_URL) == compute_doc_id(doc, include_publication_date=False)


def test_corrige_fecha_y_doc_id(db_session, monkeypatch):
    source = _fuente(db_session)
    doc = _concepto(db_session, source)
    _archivos(monkeypatch, {doc.storage_key: _docx("CONCEPTO 10 DE 2026 (30 de julio) INSTITUTO")})

    r = backfill(db_session)

    doc = repository.get_document(db_session, doc.id)
    assert doc.f_public == doc.f_providencia == date(2026, 7, 30)
    assert doc.doc_id == doc_id_nuevo(_URL)
    assert r["fecha_corregida"] == 1 and r["doc_id_cambiado"] == 1
    # La carpeta del archivo no se mueve.
    assert "/2026-01-01/" in doc.storage_key


def test_simular_no_cambia_nada(db_session, monkeypatch):
    source = _fuente(db_session)
    doc = _concepto(db_session, source)
    doc_id_viejo = doc.doc_id
    _archivos(monkeypatch, {doc.storage_key: _docx("CONCEPTO 10 DE 2026 (30 de julio)")})

    r = backfill(db_session, simular=True)

    doc = repository.get_document(db_session, doc.id)
    assert doc.f_public == date(2026, 1, 1) and doc.doc_id == doc_id_viejo
    assert r["fecha_corregida"] == 1 and r["doc_id_cambiado"] == 1


def test_sin_fecha_legible_cambia_solo_el_doc_id(db_session, monkeypatch):
    source = _fuente(db_session)
    doc = _concepto(db_session, source, title="CTO_ICBF_0013_2015", f_public=date(2015, 1, 1))
    # Caso real: el 13 de 2015 abre el documento del 14 de 2014.
    _archivos(monkeypatch, {doc.storage_key: _docx("CONCEPTO 14 DE 2014 (enero 30)")})

    r = backfill(db_session)

    doc = repository.get_document(db_session, doc.id)
    assert doc.f_public == date(2015, 1, 1)
    assert doc.doc_id == doc_id_nuevo(_URL)
    assert r["fecha_sin_cambio"] == 1


def test_se_puede_repetir(db_session, monkeypatch):
    source = _fuente(db_session)
    doc = _concepto(db_session, source)
    _archivos(monkeypatch, {doc.storage_key: _docx("CONCEPTO 10 DE 2026 (30 de julio)")})
    backfill(db_session)

    r = backfill(db_session)

    assert r["fecha_corregida"] == 0 and r["doc_id_cambiado"] == 0


def test_no_pisa_un_doc_id_ya_ocupado(db_session, monkeypatch):
    source = _fuente(db_session)
    doc = _concepto(db_session, source)
    repository.insert_document(
        db_session, doc_id=doc_id_nuevo(_URL), source_id=source.id, title="otro", f_public=date(2026, 7, 30),
        source_url=_URL, storage_bucket="iurisync-test", storage_key="x/otro.docx",
    )
    _archivos(monkeypatch, {doc.storage_key: _docx("CONCEPTO 10 DE 2026 (30 de julio)"), "x/otro.docx": b""})

    r = backfill(db_session)

    assert repository.get_document(db_session, doc.id).doc_id == make_doc_id(_URL, "2026-01-01")
    assert r["avisos"] == 1


def test_archivo_ilegible_deja_la_fecha(db_session, monkeypatch):
    source = _fuente(db_session)
    doc = _concepto(db_session, source)

    def _falla(bucket, key, local):
        raise OSError("MinIO caído")

    monkeypatch.setattr(bf, "download_file", _falla)
    r = backfill(db_session)

    assert repository.get_document(db_session, doc.id).f_public == date(2026, 1, 1)
    assert r["fecha_sin_cambio"] == 1
