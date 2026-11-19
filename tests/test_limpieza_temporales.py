import os
import time
from pathlib import Path

from worker.limpieza_temporales import limpiar_temporales_huerfanos


def _carpeta(base: Path, nombre: str, edad_horas: float, ahora: float) -> Path:
    carpeta = base / nombre
    carpeta.mkdir()
    archivo = carpeta / "doc.pdf"
    archivo.write_bytes(b"x" * 10)
    marca = ahora - edad_horas * 3600
    os.utime(archivo, (marca, marca))
    os.utime(carpeta, (marca, marca))
    return carpeta


def test_borra_carpetas_de_tareas_muertas_y_respeta_lo_demas(tmp_path):
    ahora = time.time()
    muerta = _carpeta(tmp_path, "run_source_8558_abc", 20, ahora)
    zip_muerto = _carpeta(tmp_path, "bulk_download_7_xyz", 20, ahora)
    activa = _carpeta(tmp_path, "run_source_8589_def", 0.1, ahora)
    ajena = _carpeta(tmp_path, "pymp-9o8mk6xq", 20, ahora)

    borradas = limpiar_temporales_huerfanos(tmp_path, edad_minima_horas=6, ahora=ahora)

    assert sorted(p.name for p in borradas) == ["bulk_download_7_xyz", "run_source_8558_abc"]
    assert not muerta.exists() and not zip_muerto.exists()
    assert activa.exists() and ajena.exists()


def test_carpeta_vieja_con_un_archivo_reciente_se_considera_activa(tmp_path):
    # El mtime de la carpeta no cambia si se reescribe un archivo existente;
    # se mira el archivo más reciente de adentro, no solo la carpeta.
    ahora = time.time()
    carpeta = _carpeta(tmp_path, "run_source_9000_aaa", 20, ahora)
    reciente = carpeta / "doc.pdf"
    os.utime(reciente, (ahora, ahora))

    assert limpiar_temporales_huerfanos(tmp_path, edad_minima_horas=6, ahora=ahora) == []
    assert carpeta.exists()


def test_ignora_archivos_sueltos_y_carpeta_inexistente(tmp_path):
    ahora = time.time()
    suelto = tmp_path / "run_source_1_suelto.part"
    suelto.write_bytes(b"x")
    marca = ahora - 20 * 3600
    os.utime(suelto, (marca, marca))

    assert limpiar_temporales_huerfanos(tmp_path, edad_minima_horas=6, ahora=ahora) == []
    assert suelto.exists()
    assert limpiar_temporales_huerfanos(tmp_path / "no-existe", ahora=ahora) == []


def test_se_ejecuta_al_arrancar_el_worker(monkeypatch):
    from celery import signals

    import worker.celery_app  # noqa: F401  registra la señal
    import worker.limpieza_temporales as modulo

    llamadas = []
    monkeypatch.setattr(modulo, "limpiar_temporales_huerfanos", lambda: llamadas.append(1))
    signals.worker_init.send(sender=None)
    assert llamadas == [1]


def test_un_fallo_en_la_limpieza_no_impide_arrancar(monkeypatch):
    import worker.celery_app
    import worker.limpieza_temporales as modulo

    def _falla():
        raise RuntimeError("disco raro")

    monkeypatch.setattr(modulo, "limpiar_temporales_huerfanos", _falla)
    # Celery ya atrapa errores de las señales, así que se llama directo: la
    # protección tiene que estar en el propio receptor.
    worker.celery_app._limpiar_temporales_al_arrancar()
