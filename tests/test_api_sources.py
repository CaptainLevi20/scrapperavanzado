def test_get_sources_requires_authentication(api_client):
    response = api_client.get("/sources")
    assert response.status_code == 401


def test_get_sources_rejects_invalid_token(api_client):
    response = api_client.get("/sources", headers={"Authorization": "Bearer wrong-token"})
    assert response.status_code == 401


def test_create_and_list_source(api_client, auth_header, admin_auth_header, db_session):
    from core.db import repository

    repository.create_source_family(db_session, key="constitucional", display_name="Corte Constitucional")

    create_response = api_client.post(
        "/sources",
        json={"family_key": "constitucional", "name": "Corte Constitucional", "family_params": {}},
        headers=admin_auth_header,
    )
    assert create_response.status_code == 201
    source_id = create_response.json()["id"]

    list_response = api_client.get("/sources", headers=auth_header)
    assert list_response.status_code == 200
    assert [s["name"] for s in list_response.json()] == ["Corte Constitucional"]

    patch_response = api_client.patch(f"/sources/{source_id}", json={"active": False}, headers=admin_auth_header)
    assert patch_response.status_code == 200
    assert patch_response.json()["active"] is False


def test_get_sources_filters_by_has_documents(api_client, auth_header, db_session):
    from core.db import repository

    repository.create_source_family(db_session, key="constitucional", display_name="Corte Constitucional")
    with_docs = repository.create_source(
        db_session, family_key="constitucional", name="Corte Constitucional", family_params={}
    )
    repository.create_source(db_session, family_key="constitucional", name="Fuente Vacía", family_params={})
    repository.insert_document(
        db_session,
        doc_id="doc-1",
        source_id=with_docs.id,
        title="T-100/24",
        storage_bucket="iurisync-test",
        storage_key="a.pdf",
    )

    response = api_client.get("/sources", params={"has_documents": "true"}, headers=auth_header)

    assert response.status_code == 200
    assert [s["name"] for s in response.json()] == ["Corte Constitucional"]


def test_get_sources_filters_by_id(api_client, auth_header, db_session):
    # Backs the Fuentes page's "Fuente" filter — it must narrow down to one
    # specific source (picked by name from the full list), not one family, since
    # a family can group many distinctly-named sources together.
    from core.db import repository

    repository.create_source_family(db_session, key="constitucional", display_name="Corte Constitucional")
    first = repository.create_source(
        db_session, family_key="constitucional", name="Corte Constitucional", family_params={}
    )
    repository.create_source(db_session, family_key="constitucional", name="Otra Fuente", family_params={})

    response = api_client.get("/sources", params={"id": first.id}, headers=auth_header)

    assert response.status_code == 200
    assert [s["name"] for s in response.json()] == ["Corte Constitucional"]


def test_get_source_families_reports_which_filter_by_publication_date(api_client, auth_header, db_session):
    """The 'Nuevo run' UI needs to tell the user, per source, whether the fini/ffin
    range will be matched against fecha de publicación or fecha de providencia —
    this is what it reads to decide."""
    from core.db import repository

    repository.create_source_family(db_session, key="jep", display_name="JEP")
    repository.create_source_family(db_session, key="constitucional", display_name="Corte Constitucional")

    response = api_client.get("/source-families", headers=auth_header)

    assert response.status_code == 200
    by_key = {family["key"]: family for family in response.json()}
    assert by_key["jep"]["filters_by_publication_date"] is True
    assert by_key["constitucional"]["filters_by_publication_date"] is False


def test_patch_unknown_source_returns_404(api_client, admin_auth_header):
    response = api_client.patch("/sources/999999", json={"active": False}, headers=admin_auth_header)
    assert response.status_code == 404


def test_create_source_with_unknown_family_key_returns_400(api_client, admin_auth_header):
    response = api_client.post(
        "/sources",
        json={"family_key": "no-existe", "name": "Fuente X", "family_params": {}},
        headers=admin_auth_header,
    )
    assert response.status_code == 400


def test_get_sources_respects_limit_and_offset(api_client, auth_header, db_session):
    from core.db import repository

    repository.create_source_family(db_session, key="constitucional", display_name="Corte Constitucional")
    for name in ["Fuente A", "Fuente B", "Fuente C"]:
        repository.create_source(db_session, family_key="constitucional", name=name, family_params={})

    response = api_client.get("/sources?limit=2", headers=auth_header)
    assert response.status_code == 200
    assert len(response.json()) == 2

    response = api_client.get("/sources?limit=2&offset=2", headers=auth_header)
    assert response.status_code == 200
    assert len(response.json()) == 1


def test_get_sources_rejects_out_of_range_limit_and_offset(api_client, auth_header):
    assert api_client.get("/sources?offset=-1", headers=auth_header).status_code == 422
    assert api_client.get("/sources?limit=0", headers=auth_header).status_code == 422
    assert api_client.get("/sources?limit=1000000", headers=auth_header).status_code == 422


def test_authenticated_request_updates_session_last_used_at(api_client, auth_header, db_session):
    from core.db import repository
    from core.security import hash_session_token

    raw_token = auth_header["Authorization"].removeprefix("Bearer ")
    before = repository.get_valid_session_by_token_hash(db_session, hash_session_token(raw_token))
    assert before.last_used_at is None

    response = api_client.get("/sources", headers=auth_header)
    assert response.status_code == 200

    after = repository.get_valid_session_by_token_hash(db_session, hash_session_token(raw_token))
    assert after.last_used_at is not None


def test_post_source_rejects_a_non_admin_user(api_client, auth_header, db_session):
    from core.db import repository

    repository.create_source_family(db_session, key="constitucional", display_name="Corte Constitucional")

    response = api_client.post(
        "/sources",
        json={"family_key": "constitucional", "name": "Corte Constitucional", "family_params": {}},
        headers=auth_header,
    )

    assert response.status_code == 403


def test_patch_source_rejects_a_non_admin_user(api_client, auth_header, admin_auth_header, db_session):
    from core.db import repository

    repository.create_source_family(db_session, key="constitucional", display_name="Corte Constitucional")
    source = repository.create_source(
        db_session, family_key="constitucional", name="Corte Constitucional", family_params={}
    )

    response = api_client.patch(f"/sources/{source.id}", json={"active": False}, headers=auth_header)

    assert response.status_code == 403


def test_get_sources_works_for_a_non_admin_user(api_client, auth_header, db_session):
    from core.db import repository

    repository.create_source_family(db_session, key="constitucional", display_name="Corte Constitucional")
    repository.create_source(db_session, family_key="constitucional", name="Corte Constitucional", family_params={})

    response = api_client.get("/sources", headers=auth_header)

    assert response.status_code == 200
    assert len(response.json()) == 1


def test_source_health_requires_authentication(api_client):
    assert api_client.get("/source-health").status_code == 401


def test_source_health_es_solo_para_administradores(api_client, auth_header):
    # El aviso de fuentes que pueden estar fallando es para quien administra
    # el sistema, no para los usuarios normales (decisión del usuario, oct 2026).
    assert api_client.get("/source-health", headers=auth_header).status_code == 403


def test_source_health_marca_la_fuente_callada_y_no_la_que_esta_al_dia(api_client, admin_auth_header, db_session):
    from datetime import date, timedelta

    from core.db import repository

    repository.create_source_family(db_session, key="constitucional", display_name="Corte Constitucional")
    al_dia = repository.create_source(db_session, family_key="constitucional", name="Al día", family_params={})
    callada = repository.create_source(db_session, family_key="constitucional", name="Callada", family_params={})
    inactiva = repository.create_source(db_session, family_key="constitucional", name="Inactiva", family_params={})
    repository.update_source(db_session, inactiva.id, active=False)

    hoy = date.today()
    # Las tres publicaban cada 3 días durante 6 meses; "Callada" dejó de
    # publicar hace 40 días, "Al día" sigue hasta ayer.
    for source, hasta in ((al_dia, hoy - timedelta(days=1)), (callada, hoy - timedelta(days=40)), (inactiva, hoy - timedelta(days=40))):
        for i in range(60):
            repository.insert_document(
                db_session,
                doc_id=f"{source.id}-{i}",
                source_id=source.id,
                title=f"T-{source.id}-{i}",
                f_public=hasta - timedelta(days=3 * i),
                storage_bucket="iurisync-test",
                storage_key=f"{source.id}-{i}.pdf",
            )

    response = api_client.get("/source-health", headers=admin_auth_header)

    assert response.status_code == 200
    por_nombre = {s["source_name"]: s for s in response.json()}
    assert set(por_nombre) == {"Al día", "Callada"}  # las inactivas no se vigilan
    assert por_nombre["Al día"]["alerta"] is None
    assert por_nombre["Al día"]["ultimo_documento"] == (hoy - timedelta(days=1)).isoformat()
    assert por_nombre["Callada"]["alerta"] == "silencio"
    assert por_nombre["Callada"]["dias_sin_documentos"] == 40
    assert "40 días sin documentos nuevos" in por_nombre["Callada"]["detalle"]


def test_source_health_respeta_el_margen_propio_de_una_fuente_que_publica_con_retraso(api_client, admin_auth_header, db_session):
    # La Procuraduría sube sus conceptos semanas o meses después de su fecha:
    # 30 días sin documentos es normal en ella (margen de 45), no en otras.
    from datetime import date, timedelta

    from core.db import repository

    repository.create_source_family(db_session, key="procuraduria", display_name="Procuraduría")
    repository.create_source_family(db_session, key="constitucional", display_name="Corte Constitucional")
    pgn = repository.create_source(db_session, family_key="procuraduria", name="PGN", family_params={})
    otra = repository.create_source(db_session, family_key="constitucional", name="Otra", family_params={})

    hoy = date.today()
    for source in (pgn, otra):
        for i in range(120):
            repository.insert_document(
                db_session, doc_id=f"{source.id}-{i}", source_id=source.id, title=f"X-{source.id}-{i}",
                f_public=hoy - timedelta(days=30 + i), storage_bucket="iurisync-test", storage_key=f"{source.id}-{i}.pdf",
            )

    por_nombre = {s["source_name"]: s for s in api_client.get("/source-health", headers=admin_auth_header).json()}

    assert por_nombre["PGN"]["alerta"] is None
    assert por_nombre["PGN"]["limite_silencio_dias"] == 45
    assert por_nombre["Otra"]["alerta"] == "silencio"
