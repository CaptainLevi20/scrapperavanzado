"""Revisión de SOLO LECTURA: pasa la verificación del tipo real
(core/verificacion_archivos.py) por todos los archivos ya guardados y reporta
cuáles se rechazarían. No cambia ni borra nada: ni la base de datos ni el
almacenamiento.

Para qué sirve:
- antes de desplegar la verificación, confirmar contra los archivos reales de
  producción que no rechaza documentos legítimos;
- después, encontrar archivos guardados antes de que existiera la verificación
  y que no la pasarían (los nuevos ya se revisan al descargarlos).

Uso, con el código ya desplegado:

    python -m core.revisar_tipos_archivos [--salida rechazados.csv]

Uso ANTES de desplegar: copiar este archivo y core/verificacion_archivos.py a
una misma carpeta y correr este archivo con la imagen actual del worker (ver
la descripción del PR). Por eso la importación de la verificación tiene una
alternativa local.
"""

import argparse
import csv
import sys
import tempfile
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

if not __package__:
    # Corrido como archivo suelto (`python /revision/revisar_tipos_archivos.py`)
    # desde la carpeta del proyecto (/srv en la imagen): Python solo pone en la
    # ruta la carpeta del archivo, no la del proyecto, y `core` no se encontraría.
    sys.path.insert(0, str(Path.cwd()))

try:
    from core.verificacion_archivos import ArchivoNoPermitido, verificar_archivo
except ImportError:  # imagen anterior al despliegue: usar la copia de al lado
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from verificacion_archivos import ArchivoNoPermitido, verificar_archivo


@dataclass
class Rechazado:
    id: int
    fuente: str
    title: str
    storage_key: str
    motivo: str


@dataclass
class Resultado:
    revisados: int = 0
    por_formato: Counter = field(default_factory=Counter)
    rechazados: list[Rechazado] = field(default_factory=list)
    no_encontrados: list = field(default_factory=list)


def revisar_documentos(filas, descargar, carpeta_tmp: Path, cada=None) -> Resultado:
    """`filas`: objetos con id, fuente, title, storage_bucket, storage_key.
    `descargar(bucket, key, destino)`: copia el objeto a `destino`; lanza
    FileNotFoundError si no existe. Cada archivo se borra apenas se revisa."""
    resultado = Resultado()
    destino = carpeta_tmp / "revision.tmp"
    for fila in filas:
        try:
            descargar(fila.storage_bucket, fila.storage_key, destino)
        except FileNotFoundError:
            resultado.no_encontrados.append(fila)
            continue
        try:
            resultado.por_formato[verificar_archivo(destino)] += 1
        except ArchivoNoPermitido as exc:
            resultado.rechazados.append(
                Rechazado(fila.id, fila.fuente, fila.title, fila.storage_key, str(exc))
            )
        finally:
            destino.unlink(missing_ok=True)
        resultado.revisados += 1
        if cada and resultado.revisados % cada == 0:
            print(f"  ... {resultado.revisados} revisados", flush=True)
    return resultado


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--salida", help="CSV con los documentos que se rechazarían")
    args = parser.parse_args()

    from botocore.exceptions import ClientError
    from sqlalchemy import text

    from core.db.session import SessionLocal
    from core.storage import _client

    cliente = _client()

    def descargar(bucket, key, destino):
        try:
            cliente.download_file(bucket, key, str(destino))
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in ("404", "NoSuchKey"):
                raise FileNotFoundError(key) from exc
            raise

    db = SessionLocal()
    try:
        filas = db.execute(
            text(
                "select d.id, s.name as fuente, d.title, d.storage_bucket, d.storage_key "
                "from documents d join sources s on s.id = d.source_id order by d.id"
            )
        ).fetchall()
    finally:
        db.close()

    print(f"Revisando {len(filas)} documentos (solo lectura)...", flush=True)
    with tempfile.TemporaryDirectory() as carpeta:
        r = revisar_documentos(filas, descargar, Path(carpeta), cada=1000)

    print(f"\nRevisados: {r.revisados}")
    for formato, cantidad in r.por_formato.most_common():
        print(f"  {formato}: {cantidad}")
    print(f"No encontrados en el almacenamiento: {len(r.no_encontrados)}")
    print(f"SE RECHAZARÍAN: {len(r.rechazados)}")
    for fuente, cantidad in Counter(x.fuente for x in r.rechazados).most_common():
        print(f"  {fuente}: {cantidad}")
    for x in r.rechazados[:50]:
        print(f"  [{x.id}] {x.fuente} | {x.title} | {x.motivo}")
    if len(r.rechazados) > 50:
        print(f"  ... y {len(r.rechazados) - 50} más (ver el CSV)")

    if args.salida:
        with open(args.salida, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["id", "fuente", "titulo", "storage_key", "motivo"])
            for x in r.rechazados:
                w.writerow([x.id, x.fuente, x.title, x.storage_key, x.motivo])
        print(f"\nCSV: {args.salida}")


if __name__ == "__main__":
    main()
