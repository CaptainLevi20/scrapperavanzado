"""Pruebas de la conexión con el antivirus (ClamAV, servicio `clamav`).

Cada archivo descargado se manda al antivirus antes de guardarlo. Si el
antivirus no responde, el archivo NO se guarda (decisión 2026-11-05): mejor un
documento fallido que se reintenta que un archivo sin revisar en los productos.

La mayoría de pruebas usan un antivirus simulado (un servidor que responde
como ClamAV). La última usa el ClamAV real del docker-compose de desarrollo y
se salta si no está encendido.
"""

import socket
import socketserver
import threading

import pytest

from core.antivirus import AntivirusNoDisponible, escanear

_EICAR = b"X5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*"


class _ClamdFalso(socketserver.BaseRequestHandler):
    respuesta = b"stream: OK\0"
    recibido = b""

    def handle(self):
        datos = b""
        while not datos.endswith(b"\0\0\0\0"):
            trozo = self.request.recv(65536)
            if not trozo:
                break
            datos += trozo
        type(self).recibido = datos
        self.request.sendall(type(self).respuesta)


@pytest.fixture
def clamd_falso():
    servidor = socketserver.TCPServer(("127.0.0.1", 0), _ClamdFalso)
    hilo = threading.Thread(target=servidor.serve_forever, daemon=True)
    hilo.start()
    yield servidor
    servidor.shutdown()
    servidor.server_close()


def _archivo(tmp_path, contenido=b"%PDF-1.4 hola"):
    ruta = tmp_path / "doc.pdf"
    ruta.write_bytes(contenido)
    return ruta


def test_un_archivo_limpio_devuelve_none(tmp_path, clamd_falso):
    _ClamdFalso.respuesta = b"stream: OK\0"
    host, puerto = clamd_falso.server_address

    assert escanear(_archivo(tmp_path), host=host, puerto=puerto) is None


def test_un_archivo_infectado_devuelve_el_nombre_del_virus(tmp_path, clamd_falso):
    _ClamdFalso.respuesta = b"stream: Win.Test.EICAR_HDB-1 FOUND\0"
    host, puerto = clamd_falso.server_address

    assert escanear(_archivo(tmp_path), host=host, puerto=puerto) == "Win.Test.EICAR_HDB-1"


def test_manda_el_archivo_completo_con_el_protocolo_instream(tmp_path, clamd_falso):
    _ClamdFalso.respuesta = b"stream: OK\0"
    host, puerto = clamd_falso.server_address
    contenido = b"x" * 5000

    escanear(_archivo(tmp_path, contenido), host=host, puerto=puerto, tamano_trozo=1024)

    datos = _ClamdFalso.recibido
    assert datos.startswith(b"zINSTREAM\0")
    # Trozos de 1024 bytes precedidos de su tamaño (4 bytes, big-endian), y
    # un trozo vacío al final.
    cuerpo = datos[len(b"zINSTREAM\0"):]
    recompuesto = b""
    while True:
        n = int.from_bytes(cuerpo[:4], "big")
        cuerpo = cuerpo[4:]
        if n == 0:
            break
        recompuesto += cuerpo[:n]
        cuerpo = cuerpo[n:]
    assert recompuesto == contenido


def test_si_el_antivirus_no_responde_lanza_no_disponible(tmp_path):
    # Un puerto donde no escucha nadie.
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    puerto = s.getsockname()[1]
    s.close()

    with pytest.raises(AntivirusNoDisponible):
        escanear(_archivo(tmp_path), host="127.0.0.1", puerto=puerto)


def test_una_respuesta_de_error_del_antivirus_lanza_no_disponible(tmp_path, clamd_falso):
    _ClamdFalso.respuesta = b"INSTREAM size limit exceeded. ERROR\0"
    host, puerto = clamd_falso.server_address

    with pytest.raises(AntivirusNoDisponible, match="size limit"):
        escanear(_archivo(tmp_path), host=host, puerto=puerto)


def test_con_el_clamav_real_detecta_el_archivo_de_prueba_eicar(tmp_path):
    from core.config import get_settings

    settings = get_settings()
    try:
        socket.create_connection((settings.clamav_host, settings.clamav_port), timeout=1).close()
    except OSError:
        pytest.skip("ClamAV de desarrollo no está encendido (docker compose up -d clamav)")

    assert escanear(_archivo(tmp_path, b"%PDF-1.4 limpio")) is None
    assert "Eicar" in escanear(_archivo(tmp_path, _EICAR))
