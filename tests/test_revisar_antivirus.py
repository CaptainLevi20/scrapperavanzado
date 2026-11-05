"""Pruebas de la revisión con antivirus de lo YA guardado (solo lectura).

Pasa cada documento y versión archivada por el antivirus y reporta lo que
encuentra. No cambia, mueve ni borra nada: qué hacer con los hallazgos lo
decide una persona después.
"""

from types import SimpleNamespace

from core.antivirus import AntivirusNoDisponible
from core.revisar_antivirus import revisar


def _fila(id_, key, tipo="documento", fuente="Fuente A"):
    return SimpleNamespace(id=id_, tipo=tipo, fuente=fuente, title=f"Doc {id_}", storage_bucket="b", storage_key=key)


def _leer(contenidos):
    def leer(bucket, key):
        if key not in contenidos:
            raise FileNotFoundError(key)
        return iter([contenidos[key]])

    return leer


def _escanear(veredictos):
    def escanear(trozos):
        datos = b"".join(trozos)
        v = veredictos.get(datos)
        if isinstance(v, Exception):
            raise v
        return v

    return escanear


def test_separa_limpios_infectados_y_no_revisados_completos():
    filas = [_fila(1, "a"), _fila(2, "b", fuente="Fuente B"), _fila(3, "c", tipo="version")]
    contenidos = {"a": b"limpio", "b": b"malo", "c": b"zip-enorme"}
    veredictos = {b"malo": "Win.Test.EICAR_HDB-1", b"zip-enorme": "Heuristics.Limits.Exceeded.MaxScanSize"}

    r = revisar(filas, _leer(contenidos), _escanear(veredictos))

    assert r.revisados == 3
    assert r.limpios == 1
    assert [(x.id, x.fuente, x.virus) for x in r.infectados] == [(2, "Fuente B", "Win.Test.EICAR_HDB-1")]
    # Los límites de revisión del antivirus no son un virus: se reportan aparte.
    assert [(x.id, x.tipo) for x in r.no_revisados_completos] == [(3, "version")]


def test_un_archivo_que_falta_se_cuenta_aparte():
    r = revisar([_fila(1, "no-existe")], _leer({}), _escanear({}))

    assert r.revisados == 0
    assert [f.id for f in r.no_encontrados] == [1]


def test_si_el_antivirus_falla_en_un_archivo_se_anota_y_se_sigue():
    filas = [_fila(1, "a"), _fila(2, "b")]
    veredictos = {b"x": AntivirusNoDisponible("se cayó")}

    r = revisar(filas, _leer({"a": b"x", "b": b"limpio"}), _escanear(veredictos))

    assert [(x.id, x.motivo) for x in r.errores] == [(1, "se cayó")]
    assert r.limpios == 1


def test_revisa_en_paralelo_sin_perder_ninguno():
    filas = [_fila(i, str(i)) for i in range(1, 51)]
    contenidos = {str(i): (b"malo" if i % 10 == 0 else b"limpio") for i in range(1, 51)}

    r = revisar(filas, _leer(contenidos), _escanear({b"malo": "Virus.X"}), hilos=4)

    assert r.revisados == 50
    assert r.limpios == 45
    assert sorted(x.id for x in r.infectados) == [10, 20, 30, 40, 50]
