"""Revisión de SOLO LECTURA: pasa por el antivirus todos los documentos y
versiones archivadas ya guardados, y reporta lo que encuentra. No cambia, mueve
ni borra nada; qué hacer con los hallazgos lo decide una persona después.

Los archivos guardados antes del 5 de noviembre de 2026 no pasaron por el
antivirus (los nuevos sí, al descargarlos). Cada archivo se lee del
almacenamiento y se manda al antivirus en trozos, sin copiarlo al disco.

    python -m core.revisar_antivirus --salida hallazgos.csv [--hilos 4] [--desde-id N]

Separa:
- infectados: el antivirus encontró un virus;
- no revisados completos: el antivirus llegó a sus límites (por ejemplo, un
  comprimido que al abrirse pasa de 1 GB) y lo marca como
  "Heuristics.Limits.Exceeded"; no es un virus, pero no se pudo revisar todo;
- errores: el antivirus no respondió para ese archivo;
- no encontrados: el registro apunta a un archivo que no está.

Los documentos se recorren en orden de id y el avance muestra el último id
revisado: si la corrida se corta, se retoma con --desde-id.
"""

import argparse
import csv
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from core.antivirus import AntivirusNoDisponible, RevisionIncompleta

_LIMITES = "Heuristics.Limits.Exceeded"


@dataclass
class Hallazgo:
    id: int
    tipo: str  # "documento" | "version"
    fuente: str
    title: str
    storage_key: str
    virus: str = ""
    motivo: str = ""


@dataclass
class Resultado:
    revisados: int = 0
    limpios: int = 0
    infectados: list[Hallazgo] = field(default_factory=list)
    no_revisados_completos: list[Hallazgo] = field(default_factory=list)
    errores: list[Hallazgo] = field(default_factory=list)
    no_encontrados: list = field(default_factory=list)


def revisar(filas, leer, escanear, hilos: int = 1, cada: int | None = None) -> Resultado:
    """`filas`: objetos con id, tipo, fuente, title, storage_bucket, storage_key.
    `leer(bucket, key)` devuelve un iterable de bytes o lanza FileNotFoundError.
    `escanear(trozos)` devuelve None (limpio) o el nombre del virus, o lanza
    AntivirusNoDisponible."""
    resultado = Resultado()
    candado = threading.Lock()

    def uno(fila):
        def hallazgo(**extra):
            return Hallazgo(fila.id, fila.tipo, fila.fuente, fila.title, fila.storage_key, **extra)

        try:
            virus = escanear(leer(fila.storage_bucket, fila.storage_key))
        except FileNotFoundError:
            with candado:
                resultado.no_encontrados.append(fila)
            return
        except RevisionIncompleta as exc:
            # Límite del antivirus (no es virus): se reporta aparte.
            with candado:
                resultado.revisados += 1
                resultado.no_revisados_completos.append(hallazgo(virus=exc.limite))
            return
        except AntivirusNoDisponible as exc:
            with candado:
                resultado.errores.append(hallazgo(motivo=str(exc)))
            return
        with candado:
            resultado.revisados += 1
            if virus is None:
                resultado.limpios += 1
            elif virus.startswith(_LIMITES):
                resultado.no_revisados_completos.append(hallazgo(virus=virus))
            else:
                resultado.infectados.append(hallazgo(virus=virus))
            if cada and resultado.revisados % cada == 0:
                print(f"  ... {resultado.revisados} revisados (último id: {fila.tipo} {fila.id})", flush=True)

    if hilos <= 1:
        for fila in filas:
            uno(fila)
    else:
        with ThreadPoolExecutor(max_workers=hilos) as pool:
            list(pool.map(uno, filas))
    return resultado


def main() -> None:
    parser = argparse.ArgumentParser(description="Revisa con el antivirus lo ya guardado (solo lectura).")
    parser.add_argument("--salida", help="CSV con los hallazgos")
    parser.add_argument("--hilos", type=int, default=4, help="archivos revisados a la vez (por defecto 4)")
    parser.add_argument("--desde-id", type=int, default=0, help="retomar desde este id de documento")
    args = parser.parse_args()

    from botocore.exceptions import ClientError
    from sqlalchemy import text

    from core.antivirus import escanear_flujo
    from core.db.session import SessionLocal
    from core.storage import _client

    cliente = _client()

    def leer(bucket, key):
        try:
            cuerpo = cliente.get_object(Bucket=bucket, Key=key)["Body"]
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in ("404", "NoSuchKey"):
                raise FileNotFoundError(key) from exc
            raise
        return cuerpo.iter_chunks(256 * 1024)

    db = SessionLocal()
    try:
        filas = db.execute(
            text(
                "select d.id, 'documento' as tipo, s.name as fuente, d.title, d.storage_bucket, d.storage_key "
                "from documents d join sources s on s.id = d.source_id where d.id >= :desde "
                "union all "
                "select v.id, 'version', s.name, d.title, v.storage_bucket, v.storage_key "
                "from document_versions v join documents d on d.id = v.document_id "
                "join sources s on s.id = d.source_id where v.document_id >= :desde "
                "order by tipo, id"
            ),
            {"desde": args.desde_id},
        ).fetchall()
    finally:
        db.close()

    print(f"Revisando {len(filas)} archivos con el antivirus (solo lectura, {args.hilos} a la vez)...", flush=True)
    r = revisar(filas, leer, escanear_flujo, hilos=args.hilos, cada=1000)

    print(f"\nRevisados: {r.revisados} · limpios: {r.limpios}")
    print(f"INFECTADOS: {len(r.infectados)}")
    for x in r.infectados:
        print(f"  [{x.tipo} {x.id}] {x.fuente} | {x.title} | {x.virus}")
    print(f"No revisados completos (límites del antivirus): {len(r.no_revisados_completos)}")
    for x in r.no_revisados_completos[:20]:
        print(f"  [{x.tipo} {x.id}] {x.fuente} | {x.title} | {x.virus}")
    print(f"Errores del antivirus: {len(r.errores)}")
    for x in r.errores[:20]:
        print(f"  [{x.tipo} {x.id}] {x.motivo}")
    print(f"No encontrados en el almacenamiento: {len(r.no_encontrados)}")

    if args.salida:
        with open(args.salida, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["resultado", "tipo", "id", "fuente", "titulo", "storage_key", "detalle"])
            for etiqueta, lista, campo in (
                ("infectado", r.infectados, "virus"),
                ("no revisado completo", r.no_revisados_completos, "virus"),
                ("error del antivirus", r.errores, "motivo"),
            ):
                for x in lista:
                    w.writerow([etiqueta, x.tipo, x.id, x.fuente, x.title, x.storage_key, getattr(x, campo)])
            for fila in r.no_encontrados:
                w.writerow(["no encontrado", fila.tipo, fila.id, fila.fuente, fila.title, fila.storage_key, ""])
        print(f"\nCSV: {args.salida}")


if __name__ == "__main__":
    main()
