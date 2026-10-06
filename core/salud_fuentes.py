"""¿Una fuente dejó de traer documentos sin que nadie lo note?

Una corrida que devuelve cero documentos sin errores se ve igual que "ese día
no se publicó nada" — así pasó con la CSJ en 2026, cuando la Corte dejó de
cargar providencias a su buscador y nadie se enteró en meses. Esto compara a
cada fuente con su PROPIA historia (por fecha de publicación), porque los
ritmos son muy distintos: la CSJ publica a diario, un boletín cada mes o cada
seis meses. Dos señales, cualquiera de las dos dispara el aviso:

- silencio: lleva mucho más tiempo de lo normal sin ningún documento.
- caída: sigue llegando algo, pero mucho menos de lo que suele llegar (lo que
  tuvo la CSJ: siguió soltando un documento suelto cada tantas semanas).
"""

import math
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional

# Ventana de historia contra la que se compara (un año: cubre la vacancia
# judicial de diciembre y los ritmos semestrales).
HISTORIA_DIAS = 365
# Con menos fechas distintas que esto no se sabe cuál es el ritmo "normal".
MIN_FECHAS_CON_DOCUMENTOS = 6
# Nunca avisar de silencio antes de esto: fines de semana y festivos seguidos
# no son una falla.
PISO_SILENCIO_DIAS = 14
# El silencio "normal" es el percentil 90 de las pausas entre publicaciones;
# se avisa al pasar del doble.
FACTOR_SILENCIO = 2
# Caída: solo en fuentes con volumen suficiente (con pocos documentos al mes,
# un mes flojo es ruido) y cuando llega menos de un cuarto de lo normal.
MIN_PROMEDIO_PARA_CAIDA = 20
FRACCION_CAIDA = 0.25
# Para medir el promedio hace falta al menos este tramo de historia antes de
# la ventana reciente.
MIN_DIAS_BASE_CAIDA = 90


@dataclass
class SaludFuente:
    ultimo_documento: Optional[date]
    dias_sin_documentos: Optional[int]
    limite_silencio_dias: Optional[int]
    ventana_dias: int
    docs_recientes: int
    promedio_ventana: Optional[float]
    alerta: Optional[str]  # "silencio" | "caida" | None
    detalle: Optional[str]


def _percentil_90(valores: list[int]) -> int:
    ordenados = sorted(valores)
    return ordenados[min(len(ordenados) - 1, math.ceil(0.9 * len(ordenados)) - 1)]


def evaluar_fuente(
    conteos: dict[date, int],
    hoy: date,
    ventana_dias: int = 30,
    ultimo_documento: Optional[date] = None,
    retraso_dias: int = 0,
) -> SaludFuente:
    """`conteos`: documentos por fecha de publicación (al menos el último año).
    `ultimo_documento`: la fecha más reciente de toda la historia, por si es
    anterior a `conteos` (una fuente callada hace más de un año).
    `ventana_dias`: el tramo reciente que se compara; más largo para fuentes que
    suben documentos con semanas de retraso.
    `retraso_dias`: el retraso que ya se le conoce a la fuente (su corrida
    diaria mira así de atrás); su documento más reciente siempre se ve así de
    viejo, así que el silencio no puede saltar antes."""
    inicio_historia = hoy - timedelta(days=HISTORIA_DIAS)
    # Una fecha en el futuro es un dato mal leído: no puede tapar un silencio.
    validos = {f: n for f, n in conteos.items() if inicio_historia <= f <= hoy and n > 0}
    candidatos = [f for f in (ultimo_documento, max(validos, default=None)) if f is not None and f <= hoy]
    ultimo = max(candidatos, default=None)

    if ultimo is None:
        return SaludFuente(None, None, None, ventana_dias, 0, None, None, None)

    dias_sin = (hoy - ultimo).days

    fechas = sorted(validos)
    limite = None
    if len(fechas) >= MIN_FECHAS_CON_DOCUMENTOS:
        pausas = [(b - a).days for a, b in zip(fechas, fechas[1:])]
        limite = max(PISO_SILENCIO_DIAS, retraso_dias, FACTOR_SILENCIO * _percentil_90(pausas))

    inicio_ventana = hoy - timedelta(days=ventana_dias)
    recientes = sum(n for f, n in validos.items() if f > inicio_ventana)
    promedio = None
    if fechas and (inicio_ventana - max(fechas[0], inicio_historia)).days >= MIN_DIAS_BASE_CAIDA:
        dias_base = (inicio_ventana - max(fechas[0], inicio_historia)).days
        base = sum(n for f, n in validos.items() if f <= inicio_ventana)
        promedio = base * ventana_dias / dias_base

    alerta = detalle = None
    if not fechas:
        alerta = "silencio"
        detalle = f"Lleva {dias_sin} días sin documentos nuevos (más de un año)."
    elif limite is not None and dias_sin > limite:
        alerta = "silencio"
        detalle = (
            f"Lleva {dias_sin} días sin documentos nuevos; "
            f"lo normal en esta fuente es no pasar de {limite}."
        )
    elif promedio is not None and promedio >= MIN_PROMEDIO_PARA_CAIDA and recientes < FRACCION_CAIDA * promedio:
        alerta = "caida"
        detalle = (
            f"En los últimos {ventana_dias} días trajo {recientes} documentos; "
            f"lo normal es unos {round(promedio)}."
        )

    return SaludFuente(ultimo, dias_sin, limite, ventana_dias, recientes, promedio, alerta, detalle)
