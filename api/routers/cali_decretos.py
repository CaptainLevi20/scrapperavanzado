from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException

from api.deps import require_admin
from api.schemas import CaliDecretosEstado, CaliDecretosStartRequest, CaliDecretosStopRequest
from core import cali_decretos as cali
from worker.tasks import descargar_decretos_cali_task

router = APIRouter(prefix="/cali-decretos", dependencies=[Depends(require_admin)])


def _directorio(dest_path: str) -> Path:
    destino = Path(dest_path)
    if not destino.is_dir():
        raise HTTPException(status_code=404, detail="La ruta no existe o no es una carpeta")
    return destino


def _directorio_para_escritura(dest_path: str) -> Path:
    # Como _directorio, pero si la carpeta no existe y su carpeta padre sí, la
    # crea: así el admin puede apuntar a una subcarpeta nueva de una carpeta ya
    # conectada al contenedor (ej. /descargas/lote-marzo) sin crearla a mano.
    # Un padre inexistente —o que el padre sea la raíz del disco, que pasa cuando
    # /descargas no está conectado— sigue siendo 404: atrapa rutas mal escritas.
    destino = Path(dest_path)
    if destino.is_dir():
        return destino
    padre = destino.parent
    if padre != padre.parent and padre.is_dir():
        try:
            destino.mkdir(exist_ok=True)
        except OSError:
            raise HTTPException(
                status_code=404, detail="La ruta no existe o no es una carpeta"
            ) from None
        return destino
    raise HTTPException(status_code=404, detail="La ruta no existe o no es una carpeta")


@router.post("/start", response_model=CaliDecretosEstado)
def start(payload: CaliDecretosStartRequest):
    destino = _directorio_para_escritura(payload.dest_path)
    estado = cali.leer_estado(destino)
    if estado is not None and cali.tarea_viva(estado, datetime.now(timezone.utc)):
        raise HTTPException(status_code=409, detail="Ya hay una descarga en curso para esa carpeta")
    if estado is None:
        estado = cali.estado_inicial()
    else:
        estado["estado"] = "en_curso"
        estado["detener_solicitado"] = False
    cali.escribir_estado(destino, estado)
    descargar_decretos_cali_task.delay(str(destino))
    return estado


@router.get("/status", response_model=CaliDecretosEstado)
def status(dest_path: str):
    destino = _directorio(dest_path)
    estado = cali.leer_estado(destino)
    if estado is None:
        raise HTTPException(status_code=404, detail="No hay ninguna descarga registrada para esa carpeta")
    return estado


@router.post("/stop", response_model=CaliDecretosEstado)
def stop(payload: CaliDecretosStopRequest):
    destino = _directorio(payload.dest_path)
    estado = cali.leer_estado(destino)
    if estado is None:
        raise HTTPException(status_code=404, detail="No hay ninguna descarga registrada para esa carpeta")
    estado["detener_solicitado"] = True
    cali.escribir_estado(destino, estado)
    return estado
