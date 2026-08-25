from pathlib import Path


def _touch(path: Path, content: str = "contenido") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_analyze_requires_authentication(api_client, tmp_path):
    response = api_client.post("/reorganize/analyze", json={"root_path": str(tmp_path)})
    assert response.status_code == 401


def test_analyze_rejects_a_non_admin_user(api_client, auth_header, tmp_path):
    response = api_client.post("/reorganize/analyze", json={"root_path": str(tmp_path)}, headers=auth_header)
    assert response.status_code == 403


def test_apply_rejects_a_non_admin_user(api_client, auth_header, tmp_path):
    response = api_client.post(
        "/reorganize/apply", json={"root_path": str(tmp_path), "moves": []}, headers=auth_header
    )
    assert response.status_code == 403


def test_analyze_returns_404_for_a_path_that_does_not_exist(api_client, admin_auth_header, tmp_path):
    response = api_client.post(
        "/reorganize/analyze", json={"root_path": str(tmp_path / "no-existe")}, headers=admin_auth_header
    )
    assert response.status_code == 404


def test_analyze_happy_path(api_client, admin_auth_header, tmp_path):
    _touch(tmp_path / "DECRETOS" / "2022" / "D_MSPS_0017AJ_2022.pdf")
    # An empty sibling entity-folder is required so analyze_batch's con_entidad
    # tie-break (entity-like dirs vs year-like dirs) resolves DECRETOS as an
    # entity-organized tipo — otherwise, with only a year folder present, it is
    # read as sin_entidad and the file is treated as already correctly placed.
    (tmp_path / "DECRETOS" / "PGN").mkdir(parents=True, exist_ok=True)

    response = api_client.post("/reorganize/analyze", json={"root_path": str(tmp_path)}, headers=admin_auth_header)

    assert response.status_code == 200
    body = response.json()
    assert body["total_files"] == 1
    assert len(body["exceptions"]) == 1
    assert body["exceptions"][0]["kind"] == "missing_entity_folder"
    assert body["exceptions"][0]["proposed_path"] == "DECRETOS/MSPS/2022/D_MSPS_0017AJ_2022.pdf"


def test_apply_happy_path_moves_the_file_on_disk(api_client, admin_auth_header, tmp_path):
    source = tmp_path / "DECRETOS" / "2022" / "D_MSPS_0017AJ_2022.pdf"
    _touch(source)

    response = api_client.post(
        "/reorganize/apply",
        json={
            "root_path": str(tmp_path),
            "moves": [
                {
                    "current_path": "DECRETOS/2022/D_MSPS_0017AJ_2022.pdf",
                    "target_path": "DECRETOS/MSPS/2022/D_MSPS_0017AJ_2022.pdf",
                }
            ],
        },
        headers=admin_auth_header,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["results"][0]["moved"] is True
    assert not source.exists()
    assert (tmp_path / "DECRETOS" / "MSPS" / "2022" / "D_MSPS_0017AJ_2022.pdf").exists()
