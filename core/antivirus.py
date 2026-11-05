"""Conexión con el antivirus ClamAV (servicio `clamav` del docker-compose).

Cada archivo descargado de una fuente se manda al antivirus antes de guardarlo
(ver worker/tasks.py). Se usa el protocolo INSTREAM de clamd por TCP: el
archivo viaja por la red en trozos, así que el worker y el antivirus no
necesitan compartir carpetas.

Decisiones (2026-11-05):
- si el antivirus no responde o contesta con un error, se lanza
  AntivirusNoDisponible y el documento NO se guarda (queda fallido y se
  reintenta en la siguiente corrida): ningún archivo entra sin revisar;
- un archivo infectado va a cuarentena (ver worker/tasks.py).

Sin dependencias nuevas: el protocolo es simple (comando, trozos con su tamaño
en 4 bytes big-endian, trozo vacío para terminar, una línea de respuesta).
"""

import socket
from pathlib import Path

from core.config import get_settings

_TAMANO_TROZO = 64 * 1024


class ArchivoInfectado(Exception):
    """El antivirus encontró un virus. El archivo ya quedó en el bucket de
    cuarentena (`storage_bucket`/`storage_key`); el worker registra la
    cuarentena y no crea el documento."""

    def __init__(self, virus: str, storage_bucket: str, storage_key: str, sha256: str | None, file_size_bytes: int):
        super().__init__(f"Archivo infectado ({virus}): puesto en cuarentena, no se guardó el documento")
        self.virus = virus
        self.storage_bucket = storage_bucket
        self.storage_key = storage_key
        self.sha256 = sha256
        self.file_size_bytes = file_size_bytes


class AntivirusNoDisponible(RuntimeError):
    """El antivirus no respondió o devolvió un error: el archivo no se pudo revisar."""


def escanear(
    ruta: Path,
    host: str | None = None,
    puerto: int | None = None,
    timeout: float | None = None,
    tamano_trozo: int = _TAMANO_TROZO,
) -> str | None:
    """Revisa el archivo en `ruta`. Devuelve None si está limpio, o el nombre
    del virus encontrado. Lanza AntivirusNoDisponible si no se pudo revisar."""

    def trozos():
        with open(ruta, "rb") as archivo:
            while trozo := archivo.read(tamano_trozo):
                yield trozo

    return escanear_flujo(trozos(), host=host, puerto=puerto, timeout=timeout)


def escanear_flujo(
    trozos,
    host: str | None = None,
    puerto: int | None = None,
    timeout: float | None = None,
) -> str | None:
    """Igual que `escanear`, pero con el contenido como iterable de bytes (por
    ejemplo, leído directo del almacenamiento, sin copiarlo al disco)."""
    settings = get_settings()
    host = host or settings.clamav_host
    puerto = puerto or settings.clamav_port
    timeout = timeout or settings.clamav_timeout_segundos

    try:
        with socket.create_connection((host, puerto), timeout=timeout) as conexion:
            conexion.sendall(b"zINSTREAM\0")
            for trozo in trozos:
                if trozo:
                    conexion.sendall(len(trozo).to_bytes(4, "big") + trozo)
            conexion.sendall((0).to_bytes(4, "big"))
            respuesta = b""
            while not respuesta.endswith(b"\0"):
                parte = conexion.recv(4096)
                if not parte:
                    break
                respuesta += parte
    except OSError as exc:
        raise AntivirusNoDisponible(f"El antivirus no respondió ({host}:{puerto}): {exc}") from exc

    texto = respuesta.rstrip(b"\0").decode("utf-8", "replace").strip()
    # Respuestas de clamd: "stream: OK" | "stream: <virus> FOUND" | "... ERROR"
    if texto.endswith(" OK"):
        return None
    if texto.endswith(" FOUND"):
        return texto.removeprefix("stream:").removesuffix("FOUND").strip()
    raise AntivirusNoDisponible(f"Respuesta inesperada del antivirus: {texto or '(vacía)'}")
