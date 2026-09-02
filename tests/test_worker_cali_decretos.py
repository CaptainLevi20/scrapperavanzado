import threading
from pathlib import Path

import pytest
import responses

import worker.tasks as tasks

_PDF_BYTES = b"%PDF-1.6\n" + b"x" * 5000
_HTML_BYTES = b"<html><body>error 404</body></html>"


@pytest.fixture(autouse=True)
def _sin_esperas(monkeypatch):
    # Ruling 1: _descargar_un_pdf llama time.sleep directamente (no recibe un
    # parametro `dormir`), asi que el backoff se neutraliza parcheando el modulo.
    monkeypatch.setattr(tasks.time, "sleep", lambda *_a: None)


@responses.activate
def test_descargar_un_pdf_http_success_moves_file(tmp_path):
    responses.add(responses.GET, "https://x.test/a.pdf", body=_PDF_BYTES, status=200)
    destino = tmp_path / "out" / "D_ALCACALI_0001_1974.pdf"
    motivo = tasks._descargar_un_pdf("https://x.test/a.pdf", destino, tmp_path)
    assert motivo is None
    assert destino.read_bytes() == _PDF_BYTES


@responses.activate
def test_descargar_un_pdf_non_pdf_body_fails_after_retries(tmp_path):
    responses.add(responses.GET, "https://x.test/b.pdf", body=_HTML_BYTES, status=200)
    responses.add(responses.GET, "https://x.test/b.pdf", body=_HTML_BYTES, status=200)
    responses.add(responses.GET, "https://x.test/b.pdf", body=_HTML_BYTES, status=200)
    responses.add(responses.GET, "https://x.test/b.pdf", body=_HTML_BYTES, status=200)
    destino = tmp_path / "out" / "x.pdf"
    motivo = tasks._descargar_un_pdf("https://x.test/b.pdf", destino, tmp_path)
    assert motivo == "no-es-pdf"
    assert not destino.exists()


@responses.activate
def test_descargar_un_pdf_http_error_then_success(tmp_path):
    responses.add(responses.GET, "https://x.test/c.pdf", status=503)
    responses.add(responses.GET, "https://x.test/c.pdf", body=_PDF_BYTES, status=200)
    destino = tmp_path / "out" / "c.pdf"
    motivo = tasks._descargar_un_pdf("https://x.test/c.pdf", destino, tmp_path)
    assert motivo is None
    assert destino.read_bytes() == _PDF_BYTES


def test_descargar_un_pdf_ftp_failure_reports_ftp_no_disponible(tmp_path, monkeypatch):
    def _boom(url, destino_tmp):
        raise OSError("ftp unreachable")

    monkeypatch.setattr(tasks, "_descargar_ftp", _boom)
    destino = tmp_path / "out" / "d.pdf"
    motivo = tasks._descargar_un_pdf(
        "ftp://ftp.cali.gov.co/DECRETOS/1984/x.pdf", destino, tmp_path
    )
    assert motivo == "ftp-no-disponible"


def test_descargar_un_pdf_temp_files_are_unique_per_call(tmp_path, monkeypatch):
    # Temp-file collision fix (Task 3 review): dos descargas concurrentes de URLs
    # distintas nunca deben compartir el mismo archivo .part.
    vistos: list[Path] = []

    def _capturar(url, destino_tmp):
        vistos.append(Path(destino_tmp))
        destino_tmp.write_bytes(_PDF_BYTES)
        return _PDF_BYTES[:4], len(_PDF_BYTES)

    monkeypatch.setattr(tasks, "_descargar_http", _capturar)
    tasks._descargar_un_pdf("https://x.test/1.pdf", tmp_path / "a" / "1.pdf", tmp_path)
    tasks._descargar_un_pdf("https://x.test/1.pdf", tmp_path / "a" / "2.pdf", tmp_path)
    assert len(vistos) == 2
    assert vistos[0] != vistos[1]


import json  # noqa: F401,E402

from core.cali_decretos import leer_estado  # noqa: E402

_BASE = "https://www.cali.gov.co/aplicaciones/boletin_decretos/paginador.php"


def _pagina_html(filas, total_paginas=2):
    trs = ""
    for numero, fecha, anio, url in filas:
        boton = (
            f"<button onMouseUp=\"MM_openBrWindow(1,'{url}','descargar','')\">Descargar</button>"
            if url
            else "<span>sin boton</span>"
        )
        trs += (
            f"<tr><td>DECRETO</td><td>{numero}</td><td>{fecha}</td><td>desc</td>"
            f"<td>nota</td><td>{anio}</td><td>SG</td><td>{boton}</td></tr>"
        )
    return (
        f"<table><tbody>{trs}</tbody>"
        f"<td colspan='10'><b>10 registros (filtrado de 71969 registros en total)</b>"
        f"<strong>Pagina 1/{total_paginas}</strong></td></table>"
    )


@responses.activate
def test_task_happy_path_two_pages_builds_tree_and_marks_terminado(tmp_path, monkeypatch):
    monkeypatch.setattr(tasks.time, "sleep", lambda *_: None)

    responses.add(
        responses.GET, _BASE, status=200,
        match=[responses.matchers.query_param_matcher({"pag": "1"})],
        body=_pagina_html([("0001", "1974-01-02", "1974", "https://pdf.test/a.pdf")]),
    )
    responses.add(
        responses.GET, _BASE, status=200,
        match=[responses.matchers.query_param_matcher({"pag": "2"})],
        body=_pagina_html([("0002", "1975-05-05", "1975", "https://pdf.test/b.pdf")]),
    )
    responses.add(responses.GET, "https://pdf.test/a.pdf", body=_PDF_BYTES, status=200)
    responses.add(responses.GET, "https://pdf.test/b.pdf", body=_PDF_BYTES, status=200)

    tasks.descargar_decretos_cali_task(str(tmp_path))

    assert (tmp_path / "DECRETOS" / "ALCACALI" / "1974" / "D_ALCACALI_0001_1974.pdf").read_bytes() == _PDF_BYTES
    assert (tmp_path / "DECRETOS" / "ALCACALI" / "1975" / "D_ALCACALI_0002_1975.pdf").exists()
    estado = leer_estado(tmp_path)
    assert estado["estado"] == "terminado"
    assert estado["descargados"] == 2
    assert estado["ultima_pagina_completada"] == 2
    assert estado["total_paginas"] == 2


@responses.activate
def test_task_pdf_failure_lands_in_fallidos_without_aborting(tmp_path, monkeypatch):
    monkeypatch.setattr(tasks.time, "sleep", lambda *_: None)
    responses.add(
        responses.GET, _BASE, status=200,
        match=[responses.matchers.query_param_matcher({"pag": "1"})],
        body=_pagina_html(
            [
                ("0001", "1974-01-02", "1974", "https://pdf.test/ok.pdf"),
                ("0002", "1974-02-02", "1974", "https://pdf.test/bad.pdf"),
            ],
            total_paginas=1,
        ),
    )
    responses.add(responses.GET, "https://pdf.test/ok.pdf", body=_PDF_BYTES, status=200)
    responses.add(responses.GET, "https://pdf.test/bad.pdf", status=500)

    tasks.descargar_decretos_cali_task(str(tmp_path))

    estado = leer_estado(tmp_path)
    assert estado["estado"] == "terminado_con_fallos"
    assert estado["descargados"] == 1
    assert estado["fallidos_count"] == 1
    assert estado["fallidos"][0]["numero"] == "0002"
    assert estado["fallidos"][0]["url"] == "https://pdf.test/bad.pdf"


@responses.activate
def test_task_skips_files_already_on_disk(tmp_path, monkeypatch):
    monkeypatch.setattr(tasks.time, "sleep", lambda *_: None)
    ya = tmp_path / "DECRETOS" / "ALCACALI" / "1974" / "D_ALCACALI_0001_1974.pdf"
    ya.parent.mkdir(parents=True, exist_ok=True)
    ya.write_bytes(_PDF_BYTES)

    responses.add(
        responses.GET, _BASE, status=200,
        match=[responses.matchers.query_param_matcher({"pag": "1"})],
        body=_pagina_html([("0001", "1974-01-02", "1974", "https://pdf.test/a.pdf")], total_paginas=1),
    )
    # No mock for https://pdf.test/a.pdf on purpose: it must NOT be requested.

    tasks.descargar_decretos_cali_task(str(tmp_path))

    estado = leer_estado(tmp_path)
    assert estado["ya_existian"] == 1
    assert estado["descargados"] == 0


@responses.activate
def test_task_duplicate_numero_anio_gets_suffix_and_aviso(tmp_path, monkeypatch):
    monkeypatch.setattr(tasks.time, "sleep", lambda *_: None)
    responses.add(
        responses.GET, _BASE, status=200,
        match=[responses.matchers.query_param_matcher({"pag": "1"})],
        body=_pagina_html(
            [
                ("0010", "1987-01-02", "1987", "https://pdf.test/one.pdf"),
                ("0010", "1987-03-03", "1987", "https://pdf.test/two.pdf"),
            ],
            total_paginas=1,
        ),
    )
    responses.add(responses.GET, "https://pdf.test/one.pdf", body=_PDF_BYTES, status=200)
    responses.add(responses.GET, "https://pdf.test/two.pdf", body=_PDF_BYTES, status=200)

    tasks.descargar_decretos_cali_task(str(tmp_path))

    y = tmp_path / "DECRETOS" / "ALCACALI" / "1987"
    assert (y / "D_ALCACALI_0010_1987.pdf").exists()
    assert (y / "D_ALCACALI_0010_1987_2.pdf").exists()
    estado = leer_estado(tmp_path)
    assert estado["duplicados"] == 1
    assert any(a["tipo"] == "duplicado" for a in estado["avisos"])


@responses.activate
def test_task_stops_between_pages_when_detener_solicitado(tmp_path, monkeypatch):
    monkeypatch.setattr(tasks.time, "sleep", lambda *_: None)
    responses.add(
        responses.GET, _BASE, status=200,
        match=[responses.matchers.query_param_matcher({"pag": "1"})],
        body=_pagina_html([("0001", "1974-01-02", "1974", "https://pdf.test/a.pdf")], total_paginas=5),
    )
    responses.add(responses.GET, "https://pdf.test/a.pdf", body=_PDF_BYTES, status=200)

    real_escribir = tasks.cali.escribir_estado

    def _escribir_y_pedir_stop(destino, estado):
        real_escribir(destino, estado)
        if estado.get("ultima_pagina_completada") == 1:
            actual = tasks.cali.leer_estado(destino)
            actual["detener_solicitado"] = True
            real_escribir(destino, actual)

    monkeypatch.setattr(tasks.cali, "escribir_estado", _escribir_y_pedir_stop)

    tasks.descargar_decretos_cali_task(str(tmp_path))

    estado = leer_estado(tmp_path)
    assert estado["estado"] == "detenido"
    assert estado["ultima_pagina_completada"] == 1


@responses.activate
def test_task_fresh_run_page1_failure_ends_terminado_con_fallos(tmp_path, monkeypatch):
    # En una corrida nueva, si la página 1 no responde (ninguna respuesta registrada
    # → cada intento lanza ConnectionError → _pedir_pagina devuelve None) y no hay un
    # total_paginas previo, la tarea debe terminar CON fallos y registrar el fallo,
    # nunca marcarse "terminado" con 0 descargas (que se leería como éxito).
    monkeypatch.setattr(tasks.time, "sleep", lambda *_: None)

    tasks.descargar_decretos_cali_task(str(tmp_path))

    estado = leer_estado(tmp_path)
    assert estado["estado"] == "terminado_con_fallos"
    assert estado["descargados"] == 0
    assert estado["fallidos_count"] == 1
    assert estado["fallidos"][0]["motivo"] == "pagina"
    assert not estado["total_paginas"]


@responses.activate
def test_task_five_consecutive_failures_reduce_concurrency(tmp_path, monkeypatch):
    # Cinco fallos seguidos de descarga bajan la concurrencia de 8 a 3 y emiten el
    # aviso correspondiente.
    monkeypatch.setattr(tasks.time, "sleep", lambda *_: None)
    filas = [(f"{i:04d}", "1990-01-01", "1990", f"https://pdf.test/f{i}.pdf") for i in range(1, 6)]
    responses.add(
        responses.GET, _BASE, status=200,
        match=[responses.matchers.query_param_matcher({"pag": "1"})],
        body=_pagina_html(filas, total_paginas=1),
    )
    for i in range(1, 6):
        responses.add(responses.GET, f"https://pdf.test/f{i}.pdf", status=500)

    tasks.descargar_decretos_cali_task(str(tmp_path))

    estado = leer_estado(tmp_path)
    assert estado["concurrencia_actual"] == 3
    assert any(a["tipo"] == "concurrencia_reducida" for a in estado["avisos"])
    assert estado["avisos_count"] >= 1


@responses.activate
def test_task_resume_does_not_rewalk_completed_pages(tmp_path, monkeypatch):
    monkeypatch.setattr(tasks.time, "sleep", lambda *_: None)
    estado = tasks.cali.estado_inicial()
    estado.update(estado="detenido", total_paginas=2, ultima_pagina_completada=1)
    tasks.cali.escribir_estado(tmp_path, estado)

    # Only pag=1 (mandatory totals refresh) and pag=2 are mocked; pag=1 has no PDF
    # so re-reading it must not try to download anything.
    responses.add(
        responses.GET, _BASE, status=200,
        match=[responses.matchers.query_param_matcher({"pag": "1"})],
        body=_pagina_html([("0001", "1974-01-02", "1974", None)], total_paginas=2),
    )
    responses.add(
        responses.GET, _BASE, status=200,
        match=[responses.matchers.query_param_matcher({"pag": "2"})],
        body=_pagina_html([("0002", "1975-05-05", "1975", "https://pdf.test/b.pdf")], total_paginas=2),
    )
    responses.add(responses.GET, "https://pdf.test/b.pdf", body=_PDF_BYTES, status=200)

    tasks.descargar_decretos_cali_task(str(tmp_path))

    final = leer_estado(tmp_path)
    assert final["estado"] == "terminado"
    assert (tmp_path / "DECRETOS" / "ALCACALI" / "1975" / "D_ALCACALI_0002_1975.pdf").exists()


@responses.activate
def test_task_stop_requested_mid_page_is_honored(tmp_path, monkeypatch):
    # Regresion: el Detener llega MIENTRAS se descarga una pagina (el caso real,
    # ya que las descargas dominan el tiempo). La escritura de fin de pagina no
    # debe pisar el flag `detener_solicitado` que dejo el endpoint /stop; si lo
    # pisa, el recorrido continua y el boton Detener queda sin efecto.
    monkeypatch.setattr(tasks.time, "sleep", lambda *_: None)
    responses.add(
        responses.GET, _BASE, status=200,
        match=[responses.matchers.query_param_matcher({"pag": "1"})],
        body=_pagina_html([("0001", "1974-01-02", "1974", "https://pdf.test/a.pdf")], total_paginas=2),
    )
    responses.add(
        responses.GET, _BASE, status=200,
        match=[responses.matchers.query_param_matcher({"pag": "2"})],
        body=_pagina_html([("0002", "1975-05-05", "1975", "https://pdf.test/b.pdf")], total_paginas=2),
    )
    responses.add(responses.GET, "https://pdf.test/a.pdf", body=_PDF_BYTES, status=200)
    responses.add(responses.GET, "https://pdf.test/b.pdf", body=_PDF_BYTES, status=200)

    real_descargar = tasks._descargar_un_pdf

    def _descargar_y_pedir_stop(url, destino_final, tmp_dir):
        # Simula que /stop llega durante la descarga de la pagina 1 (antes de que
        # esa pagina persista su estado de fin de pagina).
        resultado = real_descargar(url, destino_final, tmp_dir)
        if "a.pdf" in url:
            actual = tasks.cali.leer_estado(tmp_path)
            actual["detener_solicitado"] = True
            tasks.cali.escribir_estado(tmp_path, actual)
        return resultado

    monkeypatch.setattr(tasks, "_descargar_un_pdf", _descargar_y_pedir_stop)

    tasks.descargar_decretos_cali_task(str(tmp_path))

    estado = leer_estado(tmp_path)
    assert estado["estado"] == "detenido"
    assert estado["ultima_pagina_completada"] == 1
    # La pagina 2 no debe haberse descargado.
    assert not (tmp_path / "DECRETOS" / "ALCACALI" / "1975" / "D_ALCACALI_0002_1975.pdf").exists()


@responses.activate
def test_task_stop_on_last_page_skips_final_pass_and_ends_detenido(tmp_path, monkeypatch):
    # Regresion (el caso mas comun del "casi nunca detiene"): el Detener llega
    # mientras se descarga la UNICA pagina / la ultima pagina. El for termina solo
    # (no hay iteracion siguiente donde revisar el flag), corre la pasada final de
    # reintentos y el estado se cierra como "terminado_con_fallos" con
    # detener_solicitado pisado a False. Debe cerrarse "detenido" y NO reintentar.
    monkeypatch.setattr(tasks.time, "sleep", lambda *_: None)
    responses.add(
        responses.GET, _BASE, status=200,
        match=[responses.matchers.query_param_matcher({"pag": "1"})],
        body=_pagina_html(
            [
                ("0001", "1974-01-02", "1974", "https://pdf.test/a.pdf"),
                ("0002", "1974-02-02", "1974", "https://pdf.test/bad.pdf"),
            ],
            total_paginas=1,
        ),
    )
    responses.add(responses.GET, "https://pdf.test/a.pdf", body=_PDF_BYTES, status=200)
    # bad.pdf no se registra a proposito: falla por ConnectionError y cae a fallidos.

    real_descargar = tasks._descargar_un_pdf
    lock = threading.Lock()
    llamadas = {"n": 0}

    def _descargar_y_pedir_stop(url, destino_final, tmp_dir):
        resultado = real_descargar(url, destino_final, tmp_dir)
        if "a.pdf" in url:
            actual = tasks.cali.leer_estado(tmp_path)
            actual["detener_solicitado"] = True
            tasks.cali.escribir_estado(tmp_path, actual)
        with lock:
            llamadas["n"] += 1
        return resultado

    monkeypatch.setattr(tasks, "_descargar_un_pdf", _descargar_y_pedir_stop)

    tasks.descargar_decretos_cali_task(str(tmp_path))

    estado = leer_estado(tmp_path)
    assert estado["estado"] == "detenido"
    assert estado["detener_solicitado"] is True
    assert estado["ultima_pagina_completada"] == 1
    # Solo las 2 descargas de la pagina (a.pdf, bad.pdf). Sin el arreglo serian 3
    # (bad.pdf reintentado en la pasada final) y el estado "terminado_con_fallos".
    assert llamadas["n"] == 2


@responses.activate
def test_task_stop_during_final_pass_is_honored(tmp_path, monkeypatch):
    # El Detener llega DURANTE la pasada final de reintentos (que puede reintentar
    # cientos de descargas). Debe cortarse ahi y cerrar "detenido", sin pisar el
    # flag a False.
    monkeypatch.setattr(tasks.time, "sleep", lambda *_: None)
    responses.add(
        responses.GET, _BASE, status=200,
        match=[responses.matchers.query_param_matcher({"pag": "1"})],
        body=_pagina_html(
            [
                ("0001", "1974-01-02", "1974", "https://pdf.test/bad1.pdf"),
                ("0002", "1974-02-02", "1974", "https://pdf.test/bad2.pdf"),
            ],
            total_paginas=1,
        ),
    )
    # Ninguno de los dos PDF se registra: ambos fallan y quedan en fallidos, listos
    # para la pasada final.

    real_descargar = tasks._descargar_un_pdf
    lock = threading.Lock()
    llamadas = {"n": 0}

    def _descargar_y_pedir_stop(url, destino_final, tmp_dir):
        with lock:
            llamadas["n"] += 1
            n = llamadas["n"]
        resultado = real_descargar(url, destino_final, tmp_dir)
        # La pagina hace 2 llamadas (bad1, bad2). La 3a es la 1a de la pasada final.
        if n == 3:
            actual = tasks.cali.leer_estado(tmp_path)
            actual["detener_solicitado"] = True
            tasks.cali.escribir_estado(tmp_path, actual)
        return resultado

    monkeypatch.setattr(tasks, "_descargar_un_pdf", _descargar_y_pedir_stop)

    tasks.descargar_decretos_cali_task(str(tmp_path))

    estado = leer_estado(tmp_path)
    assert estado["estado"] == "detenido"
    assert estado["detener_solicitado"] is True
    # La pasada final se corto tras el primer reintento: 2 (pagina) + 1 (final).
    # Sin el arreglo serian 4 y el estado "terminado_con_fallos".
    assert llamadas["n"] == 3
