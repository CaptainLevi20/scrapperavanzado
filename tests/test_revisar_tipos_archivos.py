"""Pruebas de la revisión de solo lectura de los archivos YA guardados.

Sirve para correr la verificación del tipo real (core/verificacion_archivos.py)
sobre todo lo que hay en el almacenamiento antes de desplegarla, y ver qué
documentos legítimos rechazaría. No cambia ni borra nada.
"""

from types import SimpleNamespace

from core.revisar_tipos_archivos import revisar_documentos

_PDF_VALIDO = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n"


def _fila(id_, contenido_key, fuente="Fuente A"):
    return SimpleNamespace(
        id=id_, fuente=fuente, title=f"Doc {id_}", storage_bucket="b", storage_key=contenido_key
    )


def test_cuenta_los_aceptados_y_lista_los_rechazados_con_su_motivo(tmp_path):
    contenidos = {"ok.pdf": _PDF_VALIDO, "malo.pdf": b"MZ\x90\x00programa"}

    def descargar(bucket, key, destino):
        destino.write_bytes(contenidos[key])

    resultado = revisar_documentos([_fila(1, "ok.pdf"), _fila(2, "malo.pdf", fuente="Fuente B")], descargar, tmp_path)

    assert resultado.revisados == 2
    assert resultado.por_formato == {"pdf": 1}
    assert [(r.id, r.fuente) for r in resultado.rechazados] == [(2, "Fuente B")]
    assert "no permitido" in resultado.rechazados[0].motivo


def test_un_archivo_que_falta_en_el_almacenamiento_no_cuenta_como_rechazado(tmp_path):
    def descargar(bucket, key, destino):
        raise FileNotFoundError(key)

    resultado = revisar_documentos([_fila(1, "no-existe.pdf")], descargar, tmp_path)

    assert resultado.rechazados == []
    assert [f.id for f in resultado.no_encontrados] == [1]


def test_no_deja_archivos_temporales(tmp_path):
    def descargar(bucket, key, destino):
        destino.write_bytes(_PDF_VALIDO)

    revisar_documentos([_fila(1, "a.pdf"), _fila(2, "b.pdf")], descargar, tmp_path)

    assert list(tmp_path.iterdir()) == []
