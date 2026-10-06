from datetime import date, timedelta

from core.salud_fuentes import evaluar_fuente

HOY = date(2026, 10, 6)


def _diario(desde: date, hasta: date, por_dia: int = 20) -> dict[date, int]:
    """Una fuente que publica todos los días hábiles (como la CSJ)."""
    conteos = {}
    dia = desde
    while dia <= hasta:
        if dia.weekday() < 5:
            conteos[dia] = por_dia
        dia += timedelta(days=1)
    return conteos


def _cada(dias: int, hasta: date, veces: int, por_vez: int = 1) -> dict[date, int]:
    return {hasta - timedelta(days=dias * i): por_vez for i in range(veces)}


def test_fuente_diaria_al_dia_no_genera_alerta():
    conteos = _diario(HOY - timedelta(days=364), HOY - timedelta(days=1))

    salud = evaluar_fuente(conteos, HOY)

    assert salud.alerta is None
    assert salud.ultimo_documento == max(conteos)
    assert salud.limite_silencio_dias == 14  # piso: los fines de semana no cuentan como silencio


def test_fuente_diaria_que_se_calla_genera_alerta_de_silencio():
    conteos = _diario(HOY - timedelta(days=364), HOY - timedelta(days=20))

    salud = evaluar_fuente(conteos, HOY)

    assert salud.alerta == "silencio"
    assert salud.dias_sin_documentos >= 20
    assert "días sin documentos nuevos" in salud.detalle


def test_fuente_mensual_no_alerta_por_un_mes_y_medio_sin_documentos():
    # Un boletín mensual: 45 días sin nada es normal, no una falla.
    conteos = _cada(30, HOY - timedelta(days=45), veces=12)

    salud = evaluar_fuente(conteos, HOY)

    assert salud.alerta is None
    assert salud.limite_silencio_dias == 60


def test_fuente_mensual_que_se_salta_dos_meses_genera_alerta():
    conteos = _cada(30, HOY - timedelta(days=70), veces=12)

    salud = evaluar_fuente(conteos, HOY)

    assert salud.alerta == "silencio"


def test_caida_fuerte_de_volumen_genera_alerta_aunque_siga_llegando_algo():
    # Lo que le pasó a la CSJ: cientos de documentos al mes hasta el 30 de
    # abril, y después solo un goteo de documentos sueltos. Nunca hubo un
    # silencio largo, pero la cantidad se desplomó.
    hoy = date(2026, 5, 31)
    conteos = _diario(date(2025, 6, 1), date(2026, 4, 30))
    conteos.update({date(2026, 5, 12): 1, date(2026, 5, 20): 2, date(2026, 5, 29): 1})

    salud = evaluar_fuente(conteos, hoy)

    assert salud.alerta == "caida"
    assert salud.docs_recientes == 4
    assert salud.promedio_ventana > 300
    assert "lo normal es unos" in salud.detalle


def test_fuente_de_poco_volumen_no_alerta_por_caida():
    # Con apenas unos pocos documentos al mes, un mes flojo es ruido, no una
    # caída: de eso se encarga solo la alerta de silencio.
    conteos = _cada(7, HOY - timedelta(days=40), veces=40, por_vez=2)

    salud = evaluar_fuente(conteos, HOY)

    assert salud.alerta != "caida"


def test_sin_historia_suficiente_no_alerta():
    conteos = {HOY - timedelta(days=200): 3, HOY - timedelta(days=150): 1}

    salud = evaluar_fuente(conteos, HOY)

    assert salud.alerta is None
    assert salud.limite_silencio_dias is None


def test_fuente_sin_ningun_documento_no_alerta():
    salud = evaluar_fuente({}, HOY)

    assert salud.alerta is None
    assert salud.ultimo_documento is None


def test_fuente_que_no_trae_nada_hace_mas_de_un_ano_genera_alerta():
    salud = evaluar_fuente({}, HOY, ultimo_documento=HOY - timedelta(days=500))

    assert salud.alerta == "silencio"
    assert salud.dias_sin_documentos == 500


def test_fechas_futuras_se_ignoran():
    # Una fecha mal leída en el futuro no puede tapar un silencio real.
    conteos = _diario(HOY - timedelta(days=364), HOY - timedelta(days=30))
    conteos[HOY + timedelta(days=90)] = 1

    salud = evaluar_fuente(conteos, HOY)

    assert salud.alerta == "silencio"
    assert salud.ultimo_documento < HOY


def test_ventana_mas_larga_para_fuentes_que_publican_con_retraso():
    # MinSalud sube documentos semanas después de su fecha: con ventana de 30
    # días el último mes siempre se vería flojo. Con ventana de 60, no.
    # El último mes se ve flojo (2 por día en vez de 10) solo porque lo demás
    # todavía no se ha subido.
    conteos = _diario(HOY - timedelta(days=364), HOY - timedelta(days=31), por_dia=10)
    conteos.update(_diario(HOY - timedelta(days=30), HOY - timedelta(days=1), por_dia=2))

    assert evaluar_fuente(conteos, HOY).alerta == "caida"
    assert evaluar_fuente(conteos, HOY, ventana_dias=60).alerta != "caida"


def test_fuente_con_retraso_conocido_no_alerta_silencio_antes_de_ese_retraso():
    # La Corte Constitucional tarda 10+ días en indexar: su documento más
    # reciente siempre se ve "viejo". El silencio no puede saltar antes del
    # retraso que ya se le conoce a la fuente.
    conteos = _diario(HOY - timedelta(days=364), HOY - timedelta(days=18))

    assert evaluar_fuente(conteos, HOY).alerta == "silencio"
    salud = evaluar_fuente(conteos, HOY, retraso_dias=21)
    assert salud.alerta is None
    assert salud.limite_silencio_dias == 21
