from pathlib import Path

import pytest

import api.routers.cali_decretos as router_module


@pytest.fixture(autouse=True)
def _no_real_celery(monkeypatch):
    class _NoopTask:
        def delay(self, *args, **kwargs):
            return None

    monkeypatch.setattr(router_module, "descargar_decretos_cali_task", _NoopTask())


def test_start_requires_authentication(api_client, tmp_path):
    assert api_client.post("/cali-decretos/start", json={"dest_path": str(tmp_path)}).status_code == 401


def test_endpoints_reject_non_admin(api_client, auth_header, tmp_path):
    for method, path, body in [
        ("post", "/cali-decretos/start", {"dest_path": str(tmp_path)}),
        ("post", "/cali-decretos/stop", {"dest_path": str(tmp_path)}),
    ]:
        assert getattr(api_client, method)(path, json=body, headers=auth_header).status_code == 403
    assert api_client.get(
        "/cali-decretos/status", params={"dest_path": str(tmp_path)}, headers=auth_header
    ).status_code == 403


def test_start_creates_missing_leaf_directory(api_client, admin_auth_header, tmp_path):
    # El admin apunta a una subcarpeta nueva de una carpeta ya conectada
    # (ej. /descargas/lote-marzo): la herramienta la crea sola, no exige que
    # exista de antes.
    destino = tmp_path / "lote-marzo"
    resp = api_client.post(
        "/cali-decretos/start", json={"dest_path": str(destino)}, headers=admin_auth_header
    )
    assert resp.status_code == 200
    assert destino.is_dir()
    assert (destino / "_descarga_estado.json").is_file()


def test_start_404_when_parent_directory_missing(api_client, admin_auth_header, tmp_path):
    # El padre NO existe (ruta mal escrita, o la carpeta base no está conectada
    # al contenedor): sigue siendo 404, no se crea nada.
    resp = api_client.post(
        "/cali-decretos/start",
        json={"dest_path": str(tmp_path / "no-existe" / "cali")},
        headers=admin_auth_header,
    )
    assert resp.status_code == 404
    assert not (tmp_path / "no-existe").exists()


def test_start_creates_state_and_enqueues(api_client, admin_auth_header, tmp_path):
    resp = api_client.post(
        "/cali-decretos/start", json={"dest_path": str(tmp_path)}, headers=admin_auth_header
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["estado"] == "en_curso"
    assert (tmp_path / "_descarga_estado.json").is_file()


def test_start_409_when_task_is_alive(api_client, admin_auth_header, tmp_path):
    from core.cali_decretos import escribir_estado, estado_inicial

    escribir_estado(tmp_path, estado_inicial())  # freshly "en_curso", actualizado = now
    resp = api_client.post(
        "/cali-decretos/start", json={"dest_path": str(tmp_path)}, headers=admin_auth_header
    )
    assert resp.status_code == 409


def test_status_404_without_state_then_returns_it(api_client, admin_auth_header, tmp_path):
    assert api_client.get(
        "/cali-decretos/status", params={"dest_path": str(tmp_path)}, headers=admin_auth_header
    ).status_code == 404

    from core.cali_decretos import escribir_estado, estado_inicial

    escribir_estado(tmp_path, estado_inicial())
    resp = api_client.get(
        "/cali-decretos/status", params={"dest_path": str(tmp_path)}, headers=admin_auth_header
    )
    assert resp.status_code == 200
    assert resp.json()["estado"] == "en_curso"


def test_stop_sets_detener_solicitado(api_client, admin_auth_header, tmp_path):
    from core.cali_decretos import escribir_estado, estado_inicial, leer_estado

    escribir_estado(tmp_path, estado_inicial())
    resp = api_client.post(
        "/cali-decretos/stop", json={"dest_path": str(tmp_path)}, headers=admin_auth_header
    )
    assert resp.status_code == 200
    assert leer_estado(tmp_path)["detener_solicitado"] is True
