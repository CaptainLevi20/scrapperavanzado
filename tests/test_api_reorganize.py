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


def test_apply_returns_404_for_a_path_that_does_not_exist(api_client, admin_auth_header, tmp_path):
    response = api_client.post(
        "/reorganize/apply",
        json={"root_path": str(tmp_path / "no-existe"), "moves": []},
        headers=admin_auth_header,
    )
    assert response.status_code == 404


def test_analyze_happy_path(api_client, admin_auth_header, tmp_path):
    _touch(tmp_path / "DECRETOS" / "2022" / "D_MSPS_0017AJ_2022.pdf")
    # Two empty sibling entity-folders are required so analyze_batch's con_entidad
    # tie-break (entity-like dirs vs year-like dirs) resolves DECRETOS as an
    # entity-organized tipo. A single entity-folder would only tie 1-vs-1 against
    # the "2022" year folder, and the tie-break now requires a strict majority of
    # entity-like dirs (a bare tie between nonzero counts resolves to sin_entidad
    # instead) — otherwise the file would be read as already correctly placed.
    (tmp_path / "DECRETOS" / "PGN").mkdir(parents=True, exist_ok=True)
    (tmp_path / "DECRETOS" / "OTRO").mkdir(parents=True, exist_ok=True)

    response = api_client.post("/reorganize/analyze", json={"root_path": str(tmp_path)}, headers=admin_auth_header)

    assert response.status_code == 200
    body = response.json()
    assert body["total_files"] == 1
    assert len(body["exceptions"]) == 1
    assert body["exceptions"][0]["kind"] == "missing_entity_folder"
    assert body["exceptions"][0]["proposed_path"] == "DECRETOS/MSPS/2022/D_MSPS_0017AJ_2022.pdf"


def test_analyze_detects_an_entity_mismatch(api_client, admin_auth_header, tmp_path):
    _touch(tmp_path / "ACUERDOS" / "ARCHIVO" / "2003" / "A_AGN_0015_2003.pdf")

    response = api_client.post("/reorganize/analyze", json={"root_path": str(tmp_path)}, headers=admin_auth_header)

    assert response.status_code == 200
    body = response.json()
    assert len(body["exceptions"]) == 1
    assert body["exceptions"][0]["kind"] == "entity_mismatch"
    assert body["exceptions"][0]["detected_entity"] == "AGN"
    assert body["exceptions"][0]["proposed_path"] == "ACUERDOS/AGN/2003/A_AGN_0015_2003.pdf"


def test_analyze_detects_a_year_mismatch(api_client, admin_auth_header, tmp_path):
    _touch(tmp_path / "ACUERDOS" / "MME" / "2014" / "A_MME_0031_2015.pdf")

    response = api_client.post("/reorganize/analyze", json={"root_path": str(tmp_path)}, headers=admin_auth_header)

    assert response.status_code == 200
    body = response.json()
    assert len(body["exceptions"]) == 1
    assert body["exceptions"][0]["kind"] == "year_mismatch"
    assert body["exceptions"][0]["detected_year"] == 2015
    assert body["exceptions"][0]["proposed_path"] == "ACUERDOS/MME/2015/A_MME_0031_2015.pdf"


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


def test_analyze_suggests_a_folder_rename_when_all_files_agree(api_client, admin_auth_header, tmp_path):
    _touch(tmp_path / "ACUERDOS" / "CMARAUCA" / "2016" / "A_CARAUCA_100_2016.pdf")
    _touch(tmp_path / "ACUERDOS" / "CMARAUCA" / "2017" / "A_CARAUCA_200_2017.pdf")

    response = api_client.post("/reorganize/analyze", json={"root_path": str(tmp_path)}, headers=admin_auth_header)

    assert response.status_code == 200
    body = response.json()
    assert body["exceptions"] == []
    assert len(body["folder_renames"]) == 1
    assert body["folder_renames"][0]["current_entity"] == "CMARAUCA"
    assert body["folder_renames"][0]["suggested_entity"] == "CARAUCA"
    assert body["folder_renames"][0]["file_count"] == 2


def test_apply_renames_the_folder_and_moves_files_in_the_same_request(api_client, admin_auth_header, tmp_path):
    _touch(tmp_path / "ACUERDOS" / "CMARAUCA" / "2016" / "A_CARAUCA_100_2016.pdf", content="uno")
    source = tmp_path / "DECRETOS" / "2022" / "D_MSPS_0017AJ_2022.pdf"
    _touch(source, content="dos")

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
            "folder_renames": [{"current_path": "ACUERDOS/CMARAUCA", "target_path": "ACUERDOS/CARAUCA"}],
        },
        headers=admin_auth_header,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["results"][0]["moved"] is True
    assert body["folder_rename_results"][0]["renamed"] is True
    assert not (tmp_path / "ACUERDOS" / "CMARAUCA").exists()
    assert (tmp_path / "ACUERDOS" / "CARAUCA" / "2016" / "A_CARAUCA_100_2016.pdf").read_text() == "uno"
    assert (tmp_path / "DECRETOS" / "MSPS" / "2022" / "D_MSPS_0017AJ_2022.pdf").read_text() == "dos"
