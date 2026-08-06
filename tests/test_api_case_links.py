from core.db import repository


def _samai_source(db_session, name):
    repository.create_source_family_if_missing(db_session, key="samai", display_name="SAMAI")
    return repository.create_source(db_session, family_key="samai", name=name, family_params={})


def test_list_case_links_returns_assembled_expedientes(api_client, db_session, auth_header):
    tribunal = _samai_source(db_session, "Tribunal Administrativo de Antioquia")
    consejo = _samai_source(db_session, "Consejo de Estado")
    repository.insert_document(
        db_session, doc_id="doc-a", source_id=tribunal.id, title="t1",
        radicado="05001233300020180047100", storage_bucket="iurisync-test", storage_key="a.pdf",
    )
    repository.insert_document(
        db_session, doc_id="doc-b", source_id=consejo.id, title="t2",
        radicado="05001233300020180047101", storage_bucket="iurisync-test", storage_key="b.pdf",
    )
    repository._link_case_group(
        db_session, tribunal.id, "05001233300020180047100", consejo.id, "05001233300020180047101"
    )

    response = api_client.get("/case-links", headers=auth_header)

    assert response.status_code == 200
    [item] = response.json()
    assert item["stage_count"] == 2
    assert item["document_count"] == 2
    assert set(item["source_names"]) == {"Tribunal Administrativo de Antioquia", "Consejo de Estado"}


def test_get_case_link_includes_stage_ids(api_client, db_session, auth_header):
    tribunal = _samai_source(db_session, "Tribunal Administrativo de Antioquia")
    consejo = _samai_source(db_session, "Consejo de Estado")
    repository.insert_document(
        db_session, doc_id="doc-a", source_id=tribunal.id, title="t1",
        radicado="05001233300020180047100", storage_bucket="iurisync-test", storage_key="a.pdf",
    )
    repository.insert_document(
        db_session, doc_id="doc-b", source_id=consejo.id, title="t2",
        radicado="05001233300020180047101", storage_bucket="iurisync-test", storage_key="b.pdf",
    )
    case_link = repository._link_case_group(
        db_session, tribunal.id, "05001233300020180047100", consejo.id, "05001233300020180047101"
    )

    response = api_client.get(f"/case-links/{case_link.id}", headers=auth_header)

    stages = response.json()["stages"]
    assert all(isinstance(s["stage_id"], int) for s in stages)


def test_remove_stage_dissolves_two_stage_expediente(api_client, db_session, auth_header):
    tribunal = _samai_source(db_session, "Tribunal Administrativo de Antioquia")
    consejo = _samai_source(db_session, "Consejo de Estado")
    repository.insert_document(
        db_session, doc_id="doc-a", source_id=tribunal.id, title="t1",
        radicado="05001233300020180047100", storage_bucket="iurisync-test", storage_key="a.pdf",
    )
    repository.insert_document(
        db_session, doc_id="doc-b", source_id=consejo.id, title="t2",
        radicado="05001233300020180047101", storage_bucket="iurisync-test", storage_key="b.pdf",
    )
    case_link = repository._link_case_group(
        db_session, tribunal.id, "05001233300020180047100", consejo.id, "05001233300020180047101"
    )
    stage = repository.list_case_link_stages(db_session, case_link.id)[0]

    response = api_client.delete(f"/case-links/{case_link.id}/stages/{stage.id}", headers=auth_header)

    assert response.status_code == 200
    assert response.json()["dissolved"] is True
    assert api_client.get("/case-links", headers=auth_header).json() == []


def test_remove_stage_returns_404_when_stage_not_in_expediente(api_client, db_session, auth_header):
    tribunal = _samai_source(db_session, "Tribunal Administrativo de Antioquia")
    consejo = _samai_source(db_session, "Consejo de Estado")
    repository.insert_document(
        db_session, doc_id="doc-a", source_id=tribunal.id, title="t1",
        radicado="05001233300020180047100", storage_bucket="iurisync-test", storage_key="a.pdf",
    )
    repository.insert_document(
        db_session, doc_id="doc-b", source_id=consejo.id, title="t2",
        radicado="05001233300020180047101", storage_bucket="iurisync-test", storage_key="b.pdf",
    )
    case_link = repository._link_case_group(
        db_session, tribunal.id, "05001233300020180047100", consejo.id, "05001233300020180047101"
    )

    response = api_client.delete(f"/case-links/{case_link.id}/stages/999999", headers=auth_header)

    assert response.status_code == 404
