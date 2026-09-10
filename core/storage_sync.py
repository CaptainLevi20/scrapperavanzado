import logging
import re
from pathlib import PurePosixPath
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.db import repository
from core.db.models import Document
from core.naming import es_familia_con_actuaciones, nombre_documento, nombre_version
from core.storage import copy_object, delete_object, list_objects, object_exists
from core.utils import rekey_filename

logger = logging.getLogger(__name__)


def _expected_document_key(document: Document, family_key: Optional[str], tiene_actuaciones: bool) -> str:
    nombre_esperado = nombre_documento(document, family_key, tiene_actuaciones)
    return rekey_filename(document.storage_key, nombre_esperado)


def _expected_version_key(document: Document, version, family_key: Optional[str], tiene_actuaciones: bool) -> str:
    nombre_esperado = nombre_version(document, version, family_key, tiene_actuaciones)
    return rekey_filename(version.storage_key, nombre_esperado)


def _grupos_en_colision(keys_por_id: dict[int, str]) -> dict[str, list[int]]:
    """Agrupa ids por su key calculada y devuelve solo los grupos con más de un
    id — es decir, las keys que dos o más filas calcularían igual."""
    grupos: dict[str, list[int]] = {}
    for id_, key in keys_por_id.items():
        grupos.setdefault(key, []).append(id_)
    return {key: ids for key, ids in grupos.items() if len(ids) > 1}


def _base_sin_sufijos(stem: str) -> str:
    """Quita del final del nombre el sufijo de fecha (_AAAAMMDD o _AAAA) y el de
    versión (-v{n}), para poder comparar dos nombres que solo difieren en eso —
    p. ej. `T_..._2026` (año, calculado ahora) contra `T_..._20260806` (fecha
    completa, con la que un reconcile anterior renombró el objeto real). Solo se
    reconoce como año un _AAAA de la forma 19xx/20xx, para no morder los
    últimos 4 dígitos de un radicado."""
    anterior = None
    actual = stem
    while actual != anterior:
        anterior = actual
        actual = re.sub(r"-v\d+$", "", actual)
        actual = re.sub(r"_\d{8}$", "", actual)
        actual = re.sub(r"_(?:19|20)\d{2}$", "", actual)
    return actual


def _objeto_falta(bucket: str, key: str, entidad_desc: str) -> bool:
    """True solo si se pudo confirmar que el objeto NO existe (404). Si la
    consulta a MinIO falla por cualquier otra razón (permisos, MinIO caído,
    red), devuelve False — ante la duda se sigue el camino normal de
    renombrado, que ya captura sus propias fallas; nunca se bloquea al
    llamador (ver Global Constraints del plan)."""
    try:
        return not object_exists(bucket, key)
    except Exception as exc:
        logger.warning("%s: no se pudo verificar si %r existe en MinIO: %s", entidad_desc, key, exc)
        return False


def _clave_real_del_objeto(
    bucket: str, storage_key_roto: str, nueva_key: str, entidad_desc: str
) -> Optional[str]:
    """`storage_key_roto` apunta a un objeto que ya no existe en MinIO
    (típicamente: un reconcile anterior renombró el objeto pero la escritura en
    la base no llegó a confirmarse). Ubica el objeto real sin copiar nada:

      1. si el objeto ya está bajo su nombre canónico vigente (`nueva_key`), es
         ese;
      2. si no, busca en la misma carpeta un único objeto cuyo nombre coincida
         con el canónico salvo el sufijo de fecha/versión.

    Devuelve la clave encontrada, o None si no hay una coincidencia inequívoca
    (0 candidatos, o más de uno) o si no se pudo consultar MinIO — en ese caso
    deja un error en el log para corrección manual."""
    try:
        if object_exists(bucket, nueva_key):
            return nueva_key

        carpeta = str(PurePosixPath(nueva_key).parent)
        prefijo = "" if carpeta == "." else carpeta + "/"
        base_esperada = _base_sin_sufijos(PurePosixPath(nueva_key).stem)
        candidatos = sorted(
            k
            for k in list_objects(bucket, prefijo)
            if str(PurePosixPath(k).parent) == carpeta
            and _base_sin_sufijos(PurePosixPath(k).stem) == base_esperada
        )
    except Exception as exc:
        logger.error(
            "%s: storage_key %r apunta a un objeto inexistente y falló la "
            "búsqueda del archivo real en MinIO: %s. Requiere corrección manual.",
            entidad_desc, storage_key_roto, exc,
        )
        return None

    if len(candidatos) == 1:
        return candidatos[0]

    logger.error(
        "%s: storage_key %r apunta a un objeto inexistente en MinIO y no se "
        "pudo ubicar el archivo real en la carpeta %r (candidatos: %s). "
        "Requiere corrección manual.",
        entidad_desc, storage_key_roto, prefijo, candidatos,
    )
    return None


def reconcile_document(db: Session, document: Document, family_key: Optional[str], tiene_actuaciones: bool) -> bool:
    """Renombra en MinIO el archivo de `document` si su storage_key actual no
    coincide con su nombre canónico vigente. Devuelve True solo si el
    renombrado se ejecutó con éxito y storage_key quedó actualizado en la
    base — una falla se registra en el log y no propaga (ver Global
    Constraints del plan: nunca bloquea al llamador).

    La clave vieja en MinIO NUNCA se borra hasta que la escritura en la base
    ya se confirmó (regresión — incidente doc 39905, 2026-08-21: la versión
    anterior renombraba en MinIO —copia + borrado— y recién después escribía
    en la base; si esa escritura fallaba, storage_key se quedaba apuntando a
    la clave vieja, que ya se había borrado, dejando el documento con
    registro válido pero sin archivo real). Si la escritura en la base falla
    aquí, en el peor caso queda una copia duplicada bajo la clave nueva sin
    que la base la sepa — inofensivo (espacio extra), nunca una referencia
    rota."""
    nueva_key = _expected_document_key(document, family_key, tiene_actuaciones)
    if nueva_key == document.storage_key:
        return False
    old_key = document.storage_key

    if _objeto_falta(document.storage_bucket, old_key, f"documento {document.id}"):
        # storage_key quedó apuntando a un objeto que ya no existe (un reconcile
        # anterior lo renombró en MinIO pero la escritura en la base no se
        # confirmó). No se puede copiar desde una clave inexistente: se intenta
        # ubicar el archivo real y corregir solo el puntero en la base, sin
        # tocar MinIO (regresión: incidente descargas masivas 2026-09-09). Si
        # no se logra ubicar, se cae al camino normal de abajo — que intentará
        # copiar desde old_key y fallará con un warning, igual que antes de
        # este parche (nunca se bloquea al llamador).
        clave_real = _clave_real_del_objeto(
            document.storage_bucket, old_key, nueva_key, f"documento {document.id}"
        )
        if clave_real is not None:
            try:
                repository.update_document_storage_key(db, document.id, clave_real)
            except Exception as exc:
                logger.warning(
                    "No se pudo actualizar storage_key del documento %s al reparar un puntero roto: %s",
                    document.id, exc,
                )
                db.rollback()
                return False
            logger.warning(
                "storage_key del documento %s apuntaba a un objeto inexistente (%s); "
                "se reparó apuntando a %s (sin copiar ni borrar nada en MinIO).",
                document.id, old_key, clave_real,
            )
            return True

    try:
        copy_object(document.storage_bucket, old_key, nueva_key)
    except Exception as exc:
        logger.warning("No se pudo renombrar el documento %s en MinIO: %s", document.id, exc)
        return False
    try:
        repository.update_document_storage_key(db, document.id, nueva_key)
    except Exception as exc:
        logger.warning("No se pudo actualizar storage_key del documento %s tras copiarlo en MinIO: %s", document.id, exc)
        # Si la falla vino de la escritura en la DB, la sesión compartida
        # queda en estado de transacción fallida — sin este rollback, la
        # próxima consulta que use esta misma sesión (el siguiente documento
        # del mismo reconcile_title_group/reconcile_all) levantaría fuera de
        # cualquier try/except, abortando todo el barrido.
        db.rollback()
        try:
            delete_object(document.storage_bucket, nueva_key)
        except Exception:
            pass
        return False
    try:
        delete_object(document.storage_bucket, old_key)
    except Exception as exc:
        # La base ya apunta a nueva_key, que sí existe — la clave vieja queda
        # como copia duplicada sin usar, no como referencia rota.
        logger.warning("No se pudo borrar la clave vieja %s del documento %s en MinIO: %s", old_key, document.id, exc)
    return True


def reconcile_document_versions(
    db: Session,
    document: Document,
    family_key: Optional[str],
    tiene_actuaciones: bool,
    skip_version_ids: Optional[set[int]] = None,
) -> int:
    """Igual que reconcile_document, pero para cada versión archivada de
    `document`. Devuelve cuántas se renombraron con éxito. Las versiones cuyo
    id esté en `skip_version_ids` (detectadas de antemano como colisión de
    nombre calculado con otra versión del mismo grupo) ni se intentan
    renombrar."""
    renombradas = 0
    for version in repository.list_document_versions(db, document.id):
        if skip_version_ids and version.id in skip_version_ids:
            continue
        nombre_esperado = nombre_version(document, version, family_key, tiene_actuaciones)
        nueva_key = rekey_filename(version.storage_key, nombre_esperado)
        if nueva_key == version.storage_key:
            continue
        old_key = version.storage_key

        if _objeto_falta(version.storage_bucket, old_key, f"versión {version.id}"):
            # Igual que en reconcile_document: storage_key apunta a un objeto ya
            # inexistente — se intenta ubicar el archivo real y corregir solo el
            # puntero en la base, sin tocar MinIO. Si no se logra ubicar, se cae
            # al camino normal de abajo (copiar desde old_key, que fallará con
            # un warning igual que antes de este parche).
            clave_real = _clave_real_del_objeto(
                version.storage_bucket, old_key, nueva_key, f"versión {version.id}"
            )
            if clave_real is not None:
                try:
                    repository.update_document_version_storage_key(db, version.id, clave_real)
                except Exception as exc:
                    logger.warning(
                        "No se pudo actualizar storage_key de la versión %s al reparar un puntero roto: %s",
                        version.id, exc,
                    )
                    db.rollback()
                    continue
                logger.warning(
                    "storage_key de la versión %s apuntaba a un objeto inexistente (%s); "
                    "se reparó apuntando a %s (sin copiar ni borrar nada en MinIO).",
                    version.id, old_key, clave_real,
                )
                renombradas += 1
                continue

        try:
            copy_object(version.storage_bucket, old_key, nueva_key)
        except Exception as exc:
            logger.warning("No se pudo renombrar la versión %s en MinIO: %s", version.id, exc)
            continue
        try:
            repository.update_document_version_storage_key(db, version.id, nueva_key)
        except Exception as exc:
            logger.warning("No se pudo actualizar storage_key de la versión %s tras copiarla en MinIO: %s", version.id, exc)
            # Ver comentario equivalente en reconcile_document: sin este
            # rollback, una falla de escritura en la DB deja la sesión
            # inutilizable para el resto del barrido.
            db.rollback()
            try:
                delete_object(version.storage_bucket, nueva_key)
            except Exception:
                pass
            continue
        try:
            delete_object(version.storage_bucket, old_key)
        except Exception as exc:
            logger.warning("No se pudo borrar la clave vieja %s de la versión %s en MinIO: %s", old_key, version.id, exc)
        renombradas += 1
    return renombradas


def reconcile_title_group(db: Session, family_key: str, title: str) -> dict:
    """Recalcula si el grupo de documentos con este título dentro de esta
    familia tiene más de una actuación (misma señal que case_document_count)
    y reconcilia a cada uno (y sus versiones archivadas) con esa decisión.
    Se dispara cuando llega una actuación nueva, para corregir también a los
    'hermanos' existentes que nadie tocó directamente.

    Antes de renombrar nada, detecta colisiones: dos hermanos (o dos versiones
    archivadas, posiblemente de hermanos distintos) pueden calcular exactamente
    la misma key de MinIO cuando comparten carpeta de subida y nombre canónico
    (algo que sí puede pasar — ver el finding de la revisión final). Si eso
    ocurre, renombrar ambos causaría que el segundo rename_object (copia +
    borrado del lado del servidor) sobrescriba el archivo al que el primero
    acaba de mudarse, perdiendo su contenido en silencio. Por eso: ninguno de
    los dos lados de una colisión se toca (storage_key queda exactamente como
    estaba), se deja un warning en el log, y el resto del grupo (los que no
    colisionan) se reconcilia con normalidad."""
    documentos = repository.list_documents_by_title_within_family(db, family_key, title)
    tiene_actuaciones = len(documentos) > 1

    keys_por_documento: dict[int, str] = {
        documento.id: _expected_document_key(documento, family_key, tiene_actuaciones)
        for documento in documentos
    }
    keys_por_version: dict[int, str] = {}
    for documento in documentos:
        for version in repository.list_document_versions(db, documento.id):
            keys_por_version[version.id] = _expected_version_key(documento, version, family_key, tiene_actuaciones)

    grupos_colision_documentos = _grupos_en_colision(keys_por_documento)
    grupos_colision_versiones = _grupos_en_colision(keys_por_version)

    for key, ids in grupos_colision_documentos.items():
        logger.warning(
            "Colisión de nombre calculado entre documentos hermanos del título %r (familia %s): "
            "los documentos %s calculan la misma key %r — no se renombran, storage_key queda sin cambios.",
            title, family_key, ids, key,
        )
    for key, ids in grupos_colision_versiones.items():
        logger.warning(
            "Colisión de nombre calculado entre versiones archivadas del título %r (familia %s): "
            "las versiones %s calculan la misma key %r — no se renombran, storage_key queda sin cambios.",
            title, family_key, ids, key,
        )

    documentos_a_omitir = {id_ for ids in grupos_colision_documentos.values() for id_ in ids}
    versiones_a_omitir = {id_ for ids in grupos_colision_versiones.values() for id_ in ids}

    documentos_renombrados = 0
    versiones_renombradas = 0
    for documento in documentos:
        if documento.id not in documentos_a_omitir:
            if reconcile_document(db, documento, family_key, tiene_actuaciones):
                documentos_renombrados += 1
        versiones_renombradas += reconcile_document_versions(
            db, documento, family_key, tiene_actuaciones, skip_version_ids=versiones_a_omitir,
        )
    return {"documentos_renombrados": documentos_renombrados, "versiones_renombradas": versiones_renombradas}


def reconcile_all(db: Session) -> dict:
    """Recorre todo el archivo. Usado por el backfill inicial y por la tarea
    nocturna (red de seguridad para lo que un disparo inmediato no haya
    cubierto). Agrupa los documentos de familias con actuaciones por
    (familia, título) para no recalcular el conteo por cada uno."""
    documentos = db.scalars(select(Document)).all()
    family_keys = repository.get_source_family_keys(db, [d.source_id for d in documentos])

    grupos_de_caso: set[tuple[str, str]] = set()
    documentos_sueltos: list[Document] = []
    for documento in documentos:
        family_key = family_keys.get(documento.source_id)
        if es_familia_con_actuaciones(family_key, documento.title):
            grupos_de_caso.add((family_key, documento.title))
        else:
            documentos_sueltos.append(documento)

    documentos_renombrados = 0
    versiones_renombradas = 0
    for family_key, title in grupos_de_caso:
        resultado = reconcile_title_group(db, family_key, title)
        documentos_renombrados += resultado["documentos_renombrados"]
        versiones_renombradas += resultado["versiones_renombradas"]

    for documento in documentos_sueltos:
        family_key = family_keys.get(documento.source_id)
        if reconcile_document(db, documento, family_key, False):
            documentos_renombrados += 1
        versiones_renombradas += reconcile_document_versions(db, documento, family_key, False)

    return {"documentos_renombrados": documentos_renombrados, "versiones_renombradas": versiones_renombradas}
