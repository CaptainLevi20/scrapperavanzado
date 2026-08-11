def test_list_documents_paginates_and_filters(api_client, auth_header, db_session):
    from core.db import repository

    repository.create_source_family(db_session, key="constitucional", display_name="Corte Constitucional")
    source = repository.create_source(db_session, family_key="constitucional", name="Corte Constitucional", family_params={})
    repository.insert_document(
        db_session,
        doc_id="doc-1",
        source_id=source.id,
        title="T-065/24",
        storage_bucket="iurisync-test",
        storage_key="Corte Constitucional/2024-02-01/Sentencia/T-065-24.rtf",
    )

    response = api_client.get("/documents", headers=auth_header)
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["doc_id"] == "doc-1"


def test_list_documents_rejects_out_of_range_limit_and_offset(api_client, auth_header):
    """Regression test: limit/offset had no validation at all — a negative
    offset made Postgres respond with a raw, unhelpful 500, and nothing stopped
    a request for an absurdly large limit (e.g. a million rows) from tying up
    the server. Both must now be rejected up front with a normal 422."""
    assert api_client.get("/documents?offset=-1", headers=auth_header).status_code == 422
    assert api_client.get("/documents?limit=0", headers=auth_header).status_code == 422
    assert api_client.get("/documents?limit=-5", headers=auth_header).status_code == 422
    assert api_client.get("/documents?limit=1000000", headers=auth_header).status_code == 422


def test_list_documents_filters_by_publication_date_range(api_client, auth_header, db_session):
    from datetime import date

    from core.db import repository

    repository.create_source_family(db_session, key="constitucional", display_name="Corte Constitucional")
    source = repository.create_source(db_session, family_key="constitucional", name="Corte Constitucional", family_params={})
    repository.insert_document(
        db_session,
        doc_id="doc-en-rango",
        source_id=source.id,
        title="T-100/24",
        storage_bucket="iurisync-test",
        storage_key="Corte Constitucional/2024-06-15/Sentencia/T-100-24.rtf",
        f_public=date(2024, 6, 15),
    )
    repository.insert_document(
        db_session,
        doc_id="doc-fuera-de-rango",
        source_id=source.id,
        title="T-200/24",
        storage_bucket="iurisync-test",
        storage_key="Corte Constitucional/2024-01-05/Sentencia/T-200-24.rtf",
        f_public=date(2024, 1, 5),
    )

    response = api_client.get(
        "/documents",
        params={"f_public_from": "2024-06-01", "f_public_to": "2024-06-30"},
        headers=auth_header,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["doc_id"] == "doc-en-rango"


def test_list_documents_filters_by_downloaded_at_range(api_client, auth_header, db_session):
    from datetime import datetime, timezone

    from core.db import repository

    repository.create_source_family(db_session, key="constitucional", display_name="Corte Constitucional")
    source = repository.create_source(db_session, family_key="constitucional", name="Corte Constitucional", family_params={})
    repository.insert_document(
        db_session,
        doc_id="doc-ingresado-hoy",
        source_id=source.id,
        title="T-100/24",
        storage_bucket="iurisync-test",
        storage_key="a.pdf",
        downloaded_at=datetime(2026, 7, 23, 15, 0, 0, tzinfo=timezone.utc),
    )
    repository.insert_document(
        db_session,
        doc_id="doc-ingresado-ayer",
        source_id=source.id,
        title="T-200/24",
        storage_bucket="iurisync-test",
        storage_key="b.pdf",
        downloaded_at=datetime(2026, 7, 22, 23, 59, 0, tzinfo=timezone.utc),
    )
    repository.insert_document(
        db_session,
        doc_id="doc-ingresado-manana",
        source_id=source.id,
        title="T-300/24",
        storage_bucket="iurisync-test",
        storage_key="c.pdf",
        downloaded_at=datetime(2026, 7, 24, 0, 0, 1, tzinfo=timezone.utc),
    )

    response = api_client.get(
        "/documents",
        params={"downloaded_from": "2026-07-23", "downloaded_to": "2026-07-23"},
        headers=auth_header,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["doc_id"] == "doc-ingresado-hoy"
    assert not any(item["doc_id"] == "doc-ingresado-manana" for item in body["items"])


def test_list_documents_downloaded_at_range_is_inclusive_of_the_whole_end_day(api_client, auth_header, db_session):
    from datetime import datetime, timezone

    from core.db import repository

    repository.create_source_family(db_session, key="constitucional", display_name="Corte Constitucional")
    source = repository.create_source(db_session, family_key="constitucional", name="Corte Constitucional", family_params={})
    repository.insert_document(
        db_session,
        doc_id="doc-fin-de-dia",
        source_id=source.id,
        title="T-300/24",
        storage_bucket="iurisync-test",
        storage_key="c.pdf",
        downloaded_at=datetime(2026, 7, 23, 23, 59, 59, tzinfo=timezone.utc),
    )
    repository.insert_document(
        db_session,
        doc_id="doc-justo-fuera-del-rango",
        source_id=source.id,
        title="T-400/24",
        storage_bucket="iurisync-test",
        storage_key="d.pdf",
        downloaded_at=datetime(2026, 7, 24, 0, 0, 0, tzinfo=timezone.utc),
    )

    response = api_client.get(
        "/documents",
        params={"downloaded_from": "2026-07-23", "downloaded_to": "2026-07-23"},
        headers=auth_header,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["doc_id"] == "doc-fin-de-dia"
    assert not any(item["doc_id"] == "doc-justo-fuera-del-rango" for item in body["items"])


def test_get_documents_reports_case_document_count_for_a_shared_radicado(api_client, auth_header, db_session):
    from core.db import repository

    repository.create_source_family(db_session, key="rama_judicial", display_name="Rama Judicial")
    source = repository.create_source(
        db_session, family_key="rama_judicial", name="Tribunal Superior de Bogotá", family_params={}
    )
    shared_title = "T_BTA_11001_31_03_048_2022_00418_02"
    for doc_id in ("doc-1", "doc-2", "doc-3"):
        repository.insert_document(
            db_session, doc_id=doc_id, source_id=source.id, title=shared_title,
            storage_bucket="iurisync-test", storage_key=f"{doc_id}.pdf",
        )

    response = api_client.get("/documents", params={"family_key": "rama_judicial"}, headers=auth_header)

    assert response.status_code == 200
    body = response.json()
    # The general listing collapses a shared radicado to its most recent actuación
    # (doc-3, the last/highest-id one here since none set an explicit f_public) —
    # the badge still reports the true count across all 3.
    assert len(body["items"]) == 1
    assert body["items"][0]["doc_id"] == "doc-3"
    assert body["items"][0]["case_document_count"] == 3


def test_get_documents_reports_null_case_document_count_for_a_unique_radicado(api_client, auth_header, db_session):
    from core.db import repository

    repository.create_source_family(db_session, key="rama_judicial", display_name="Rama Judicial")
    source = repository.create_source(
        db_session, family_key="rama_judicial", name="Tribunal Superior de Bogotá", family_params={}
    )
    repository.insert_document(
        db_session, doc_id="doc-only", source_id=source.id, title="T_BTA_11001_31_03_048_2022_00418_02",
        storage_bucket="iurisync-test", storage_key="a.pdf",
    )

    response = api_client.get("/documents", params={"family_key": "rama_judicial"}, headers=auth_header)

    assert response.status_code == 200
    assert response.json()["items"][0]["case_document_count"] is None


def test_get_documents_reports_case_document_count_for_a_tribunal_administrativo(api_client, auth_header, db_session):
    """A Tribunal Administrativo source is family "samai", but its titles look
    like rama_judicial's format rather than Consejo de Estado's — the badge
    must still recognize and count them as a case (see
    core/scrapers/families/samai.py::_normalizar_titulo)."""
    from core.db import repository

    repository.create_source_family(db_session, key="samai", display_name="SAMAI")
    source = repository.create_source(
        db_session, family_key="samai", name="Tribunal Administrativo de Antioquia", family_params={}
    )
    shared_title = "T_ANTI_05001_23_33_000_2018_01895_00"
    for doc_id in ("doc-1", "doc-2"):
        repository.insert_document(
            db_session, doc_id=doc_id, source_id=source.id, title=shared_title,
            storage_bucket="iurisync-test", storage_key=f"{doc_id}.pdf",
        )

    response = api_client.get("/documents", params={"family_key": "samai"}, headers=auth_header)

    assert response.status_code == 200
    body = response.json()
    assert len(body["items"]) == 1
    assert body["items"][0]["case_document_count"] == 2


def test_get_documents_reports_case_document_count_for_raw_undashed_samai_titles(api_client, auth_header, db_session):
    """Raw undashed titles (e.g. from documents captured before scraper normalization,
    processed by core/backfill_samai_radicado.py) must be recognized as valid case
    titles and grouped by exact title match for the badge count."""
    from core.db import repository

    repository.create_source_family(db_session, key="samai", display_name="SAMAI")
    tribunal = repository.create_source(
        db_session, family_key="samai", name="Tribunal Administrativo de Antioquia", family_params={}
    )
    # Raw undashed title: identical exact title means documents should be grouped together
    shared_raw_title = "25000234200020200000801(NRD)"
    for doc_id in ("doc-1", "doc-2"):
        repository.insert_document(
            db_session, doc_id=doc_id, source_id=tribunal.id, title=shared_raw_title,
            storage_bucket="iurisync-test", storage_key=f"{doc_id}.pdf",
        )

    response = api_client.get("/documents", params={"family_key": "samai"}, headers=auth_header)

    assert response.status_code == 200
    body = response.json()
    # Listing collapses by exact title; two docs with the exact same raw undashed title
    # should collapse to one item in the listing with case_document_count=2.
    assert len(body["items"]) == 1
    assert body["items"][0]["case_document_count"] == 2


def test_get_documents_does_not_group_repeated_fallback_titles(api_client, auth_header, db_session):
    """A magistrado-name fallback title repeated across unrelated documents must
    never be reported as a case."""
    from core.db import repository

    repository.create_source_family(db_session, key="rama_judicial", display_name="Rama Judicial")
    source = repository.create_source(
        db_session, family_key="rama_judicial", name="Tribunal Superior de Antioquia", family_params={}
    )
    for doc_id in ("doc-1", "doc-2"):
        repository.insert_document(
            db_session, doc_id=doc_id, source_id=source.id, title="DR. WILLIAM SANTA MARIN",
            storage_bucket="iurisync-test", storage_key=f"{doc_id}.pdf",
        )

    response = api_client.get("/documents", params={"family_key": "rama_judicial"}, headers=auth_header)

    assert response.status_code == 200
    assert all(item["case_document_count"] is None for item in response.json()["items"])


def test_get_documents_does_not_group_across_families(api_client, auth_header, db_session):
    """The same radicado-shaped title in a non-rama_judicial family must not be
    counted or grouped."""
    from core.db import repository

    repository.create_source_family(db_session, key="jep", display_name="JEP")
    source = repository.create_source(db_session, family_key="jep", name="JEP", family_params={})
    shared_title = "T_BTA_11001_31_03_048_2022_00418_02"
    for doc_id in ("doc-1", "doc-2"):
        repository.insert_document(
            db_session, doc_id=doc_id, source_id=source.id, title=shared_title,
            storage_bucket="iurisync-test", storage_key=f"{doc_id}.pdf",
        )

    response = api_client.get("/documents", params={"family_key": "jep"}, headers=auth_header)

    assert response.status_code == 200
    assert all(item["case_document_count"] is None for item in response.json()["items"])


def test_get_documents_computes_case_document_count_per_title_not_page_wide(api_client, auth_header, db_session):
    """Regression guard: a page containing both a shared radicado and a singleton
    radicado must give each its own correct count, not one uniform value for the
    whole page (e.g. len(items) or the first title's count applied to everyone)."""
    from core.db import repository

    repository.create_source_family(db_session, key="rama_judicial", display_name="Rama Judicial")
    source = repository.create_source(
        db_session, family_key="rama_judicial", name="Tribunal Superior de Bogotá", family_params={}
    )
    shared_title = "T_BTA_11001_31_03_048_2022_00418_02"
    singleton_title = "T_BTA_11001_31_03_048_2022_00418_03"
    for doc_id in ("shared-1", "shared-2"):
        repository.insert_document(
            db_session, doc_id=doc_id, source_id=source.id, title=shared_title,
            storage_bucket="iurisync-test", storage_key=f"{doc_id}.pdf",
        )
    repository.insert_document(
        db_session, doc_id="singleton-1", source_id=source.id, title=singleton_title,
        storage_bucket="iurisync-test", storage_key="singleton-1.pdf",
    )

    response = api_client.get("/documents", params={"family_key": "rama_judicial"}, headers=auth_header)

    assert response.status_code == 200
    items = response.json()["items"]
    # The shared radicado collapses to its one most-recent actuación in the general
    # listing (doc "shared-2", higher id since neither set an explicit f_public) —
    # this still proves per-title computation: the two titles get different counts
    # (2 vs None), which a page-wide/uniform-count bug could not reproduce.
    shared_items = [item for item in items if item["title"] == shared_title]
    singleton_items = [item for item in items if item["title"] == singleton_title]
    assert len(shared_items) == 1
    assert shared_items[0]["doc_id"] == "shared-2"
    assert shared_items[0]["case_document_count"] == 2
    assert len(singleton_items) == 1
    assert singleton_items[0]["case_document_count"] is None


def test_get_documents_filters_by_title_exact(api_client, auth_header, db_session):
    from core.db import repository

    repository.create_source_family(db_session, key="rama_judicial", display_name="Rama Judicial")
    source = repository.create_source(
        db_session, family_key="rama_judicial", name="Tribunal Superior de Bogotá", family_params={}
    )
    repository.insert_document(
        db_session, doc_id="doc-exact", source_id=source.id, title="T_BTA_11001_31_03_048_2022_00418_02",
        storage_bucket="iurisync-test", storage_key="a.pdf",
    )
    repository.insert_document(
        db_session, doc_id="doc-other", source_id=source.id, title="T_BTA_11001_31_03_048_2022_00418_03",
        storage_bucket="iurisync-test", storage_key="b.pdf",
    )

    response = api_client.get(
        "/documents", params={"title_exact": "T_BTA_11001_31_03_048_2022_00418_02"}, headers=auth_header
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["doc_id"] == "doc-exact"


def test_get_document_tipos_returns_sorted_distinct_values(api_client, auth_header, db_session):
    from core.db import repository

    repository.create_source_family(db_session, key="constitucional", display_name="Corte Constitucional")
    source = repository.create_source(db_session, family_key="constitucional", name="Corte Constitucional", family_params={})
    repository.insert_document(
        db_session, doc_id="doc-1", source_id=source.id, title="A", tipo="Sentencia",
        storage_bucket="iurisync-test", storage_key="a.pdf",
    )
    repository.insert_document(
        db_session, doc_id="doc-2", source_id=source.id, title="B", tipo="Auto",
        storage_bucket="iurisync-test", storage_key="b.pdf",
    )

    response = api_client.get("/documents/tipos", headers=auth_header)

    assert response.status_code == 200
    assert response.json() == ["Auto", "Sentencia"]


def test_get_document_tipos_scoped_to_a_source(api_client, auth_header, db_session):
    from core.db import repository

    repository.create_source_family(db_session, key="constitucional", display_name="Corte Constitucional")
    source_a = repository.create_source(db_session, family_key="constitucional", name="Corte Constitucional", family_params={})
    source_b = repository.create_source(db_session, family_key="constitucional", name="Otra fuente", family_params={})
    repository.insert_document(
        db_session, doc_id="doc-1", source_id=source_a.id, title="A", tipo="Sentencia",
        storage_bucket="iurisync-test", storage_key="a.pdf",
    )
    repository.insert_document(
        db_session, doc_id="doc-2", source_id=source_b.id, title="B", tipo="Auto",
        storage_bucket="iurisync-test", storage_key="b.pdf",
    )

    response = api_client.get(f"/documents/tipos?source_id={source_a.id}", headers=auth_header)

    assert response.status_code == 200
    assert response.json() == ["Sentencia"]


def test_get_document_secciones_scoped_to_tipo(api_client, auth_header, db_session):
    from core.db import repository

    repository.create_source_family(db_session, key="constitucional", display_name="Corte Constitucional")
    source = repository.create_source(db_session, family_key="constitucional", name="Corte Constitucional", family_params={})
    repository.insert_document(
        db_session, doc_id="doc-1", source_id=source.id, title="A", tipo="Sentencia", seccion="SECCION PRIMERA",
        storage_bucket="iurisync-test", storage_key="a.pdf",
    )
    repository.insert_document(
        db_session, doc_id="doc-2", source_id=source.id, title="B", tipo="Auto", seccion="SECCION SEGUNDA",
        storage_bucket="iurisync-test", storage_key="b.pdf",
    )

    response = api_client.get(f"/documents/secciones?tipo=Sentencia", headers=auth_header)

    assert response.status_code == 200
    assert response.json() == ["SECCION PRIMERA"]


def test_get_document_especialidades_scoped_to_seccion(api_client, auth_header, db_session):
    from core.db import repository

    repository.create_source_family(db_session, key="constitucional", display_name="Corte Constitucional")
    source = repository.create_source(db_session, family_key="constitucional", name="Corte Constitucional", family_params={})
    repository.insert_document(
        db_session, doc_id="doc-1", source_id=source.id, title="A", seccion="SECCION PRIMERA", especialidad="Nulidad",
        storage_bucket="iurisync-test", storage_key="a.pdf",
    )
    repository.insert_document(
        db_session, doc_id="doc-2", source_id=source.id, title="B", seccion="SECCION SEGUNDA", especialidad="Conciliación",
        storage_bucket="iurisync-test", storage_key="b.pdf",
    )

    response = api_client.get("/documents/especialidades?seccion=SECCION+PRIMERA", headers=auth_header)

    assert response.status_code == 200
    assert response.json() == ["Nulidad"]


def test_get_document_magistrados_scoped_to_especialidad(api_client, auth_header, db_session):
    from core.db import repository

    repository.create_source_family(db_session, key="constitucional", display_name="Corte Constitucional")
    source = repository.create_source(db_session, family_key="constitucional", name="Corte Constitucional", family_params={})
    repository.insert_document(
        db_session, doc_id="doc-1", source_id=source.id, title="A", especialidad="Nulidad", magistrado="Ana Pérez",
        storage_bucket="iurisync-test", storage_key="a.pdf",
    )
    repository.insert_document(
        db_session, doc_id="doc-2", source_id=source.id, title="B", especialidad="Conciliación", magistrado="Luis Gómez",
        storage_bucket="iurisync-test", storage_key="b.pdf",
    )

    response = api_client.get("/documents/magistrados?especialidad=Nulidad", headers=auth_header)

    assert response.status_code == 200
    assert response.json() == ["Ana Pérez"]


def test_get_document_stats_aggregates_over_the_full_table_not_a_sample(api_client, auth_header, db_session):
    # Regression guard: the dashboard used to compute these breakdowns client-side
    # from only the 1000 most-recently-downloaded documents, which silently
    # undercounted large families once the archive passed that cap. This endpoint
    # must reflect every document, however many there are.
    from datetime import date

    from core.db import repository

    repository.create_source_family(db_session, key="corte_suprema", display_name="Corte Suprema de Justicia")
    repository.create_source_family(db_session, key="constitucional", display_name="Corte Constitucional")
    csj = repository.create_source(db_session, family_key="corte_suprema", name="CSJ", family_params={})
    cconst = repository.create_source(
        db_session, family_key="constitucional", name="Corte Constitucional", family_params={}
    )

    for i in range(3):
        repository.insert_document(
            db_session,
            doc_id=f"csj-{i}",
            source_id=csj.id,
            title=f"CSJ {i}",
            tipo="Sentencia",
            storage_bucket="iurisync-test",
            storage_key=f"csj-{i}.pdf",
            f_public=date(2026, 3, 10),
        )
    repository.insert_document(
        db_session,
        doc_id="const-1",
        source_id=cconst.id,
        title="Corte Const 1",
        tipo="Auto",
        storage_bucket="iurisync-test",
        storage_key="const-1.pdf",
        f_public=date(2026, 5, 20),
    )

    response = api_client.get("/documents/stats", headers=auth_header)

    assert response.status_code == 200
    body = response.json()
    by_family = {row["key"]: row["count"] for row in body["by_family"]}
    assert by_family == {"corte_suprema": 3, "constitucional": 1}
    assert next(row for row in body["by_family"] if row["key"] == "corte_suprema")["display_name"] == "Corte Suprema de Justicia"

    # by_source must break counts down per individual source, not per family —
    # two sources can share a family (e.g. two chambers of the same court) and
    # would be wrongly merged into one bar if this reused the family grouping.
    by_source = {row["name"]: row["count"] for row in body["by_source"]}
    assert by_source == {"CSJ": 3, "Corte Constitucional": 1}

    by_tipo = {row["tipo"]: row["count"] for row in body["by_tipo"]}
    assert by_tipo == {"Sentencia": 3, "Auto": 1}

    assert body["available_years"] == [2026]
    assert body["year"] == 2026
    assert body["by_month"][2] == 3  # marzo (0-indexado)
    assert body["by_month"][4] == 1  # mayo


def test_get_document_stats_accepts_explicit_year(api_client, auth_header, db_session):
    from datetime import date

    from core.db import repository

    repository.create_source_family(db_session, key="constitucional", display_name="Corte Constitucional")
    source = repository.create_source(db_session, family_key="constitucional", name="Corte Constitucional", family_params={})
    repository.insert_document(
        db_session, doc_id="doc-2024", source_id=source.id, title="A",
        storage_bucket="iurisync-test", storage_key="a.pdf", f_public=date(2024, 1, 15),
    )
    repository.insert_document(
        db_session, doc_id="doc-2026", source_id=source.id, title="B",
        storage_bucket="iurisync-test", storage_key="b.pdf", f_public=date(2026, 1, 15),
    )

    response = api_client.get("/documents/stats", params={"year": 2024}, headers=auth_header)

    assert response.status_code == 200
    body = response.json()
    assert body["year"] == 2024
    assert body["by_month"][0] == 1
    assert set(body["available_years"]) == {2024, 2026}


def test_document_out_incluye_nombre_con_version(api_client, auth_header, db_session):
    # SAMAI (familia con actuaciones) + f_providencia + una republicación → nombre
    # con "_v2". La republicación es una nueva VERSIÓN del mismo documento, no una
    # actuación distinta (sigue siendo la única fila con este título), así que la
    # fecha lleva solo el año — ver test_document_out_con_otra_actuacion_usa_fecha_completa
    # para el caso con más de una actuación real.
    from datetime import date

    from core.db import repository

    repository.create_source_family(db_session, key="samai", display_name="SAMAI")
    source = repository.create_source(db_session, family_key="samai", name="Consejo de Estado", family_params={})
    doc = repository.insert_document(
        db_session, doc_id="apx-1", source_id=source.id, title="11001-03-28-000-2026-00300-00",
        storage_bucket="iurisync-test", storage_key="a.pdf", f_providencia=date(2026, 7, 31),
    )
    repository.archive_and_replace_document(db_session, doc.id, storage_bucket="iurisync-test", storage_key="b.pdf")

    response = api_client.get(f"/documents/{doc.id}", headers=auth_header)
    assert response.status_code == 200
    assert response.json()["nombre"] == "11001-03-28-000-2026-00300-00_2026_v2"


def test_document_out_sin_otra_actuacion_usa_solo_el_anio(api_client, auth_header, db_session):
    """Regresión: un documento con título de radicado pero sin ninguna otra
    actuación registrada (reportado en producción para
    T_SANT_68001_33_33_007_2025_00290_02) no debe llevar la fecha completa en
    el nombre — solo el año."""
    from datetime import date

    from core.db import repository

    repository.create_source_family(db_session, key="rama_judicial", display_name="Rama Judicial")
    source = repository.create_source(
        db_session, family_key="rama_judicial", name="Tribunal Superior de Bogotá", family_params={}
    )
    doc = repository.insert_document(
        db_session, doc_id="rj-1", source_id=source.id, title="T_SANT_68001_33_33_007_2025_00290_02",
        storage_bucket="iurisync-test", storage_key="a.pdf", f_providencia=date(2026, 8, 6),
    )

    response = api_client.get(f"/documents/{doc.id}", headers=auth_header)

    assert response.status_code == 200
    assert response.json()["nombre"] == "T_SANT_68001_33_33_007_2025_00290_02_2026"


def test_document_out_con_otra_actuacion_usa_fecha_completa(api_client, auth_header, db_session):
    """Cuando sí hay más de una actuación (otro documento con el mismo título en
    la misma familia), ambas llevan la fecha completa, para poder distinguirlas."""
    from datetime import date

    from core.db import repository

    repository.create_source_family(db_session, key="rama_judicial", display_name="Rama Judicial")
    source = repository.create_source(
        db_session, family_key="rama_judicial", name="Tribunal Superior de Bogotá", family_params={}
    )
    shared_title = "T_SANT_68001_33_33_007_2025_00290_02"
    doc1 = repository.insert_document(
        db_session, doc_id="rj-1", source_id=source.id, title=shared_title,
        storage_bucket="iurisync-test", storage_key="a.pdf", f_providencia=date(2026, 8, 6),
    )
    repository.insert_document(
        db_session, doc_id="rj-2", source_id=source.id, title=shared_title,
        storage_bucket="iurisync-test", storage_key="b.pdf", f_providencia=date(2026, 8, 20),
    )

    response = api_client.get(f"/documents/{doc1.id}", headers=auth_header)

    assert response.status_code == 200
    assert response.json()["nombre"] == "T_SANT_68001_33_33_007_2025_00290_02_20260806"


def test_get_document_returns_404_when_missing(api_client, auth_header):
    response = api_client.get("/documents/999999", headers=auth_header)
    assert response.status_code == 404


def test_download_document_redirects_to_presigned_url(api_client, auth_header, db_session, monkeypatch):
    from core.db import repository

    repository.create_source_family(db_session, key="constitucional", display_name="Corte Constitucional")
    source = repository.create_source(db_session, family_key="constitucional", name="Corte Constitucional", family_params={})
    document = repository.insert_document(
        db_session,
        doc_id="doc-1",
        source_id=source.id,
        title="T-065/24",
        storage_bucket="iurisync-test",
        storage_key="Corte Constitucional/2024-02-01/Sentencia/T-065-24.rtf",
    )

    monkeypatch.setattr(
        "api.routers.documents.presigned_url", lambda bucket, key, **kwargs: "https://signed.example.com/file"
    )

    response = api_client.get(f"/documents/{document.id}/download", headers=auth_header, follow_redirects=False)
    assert response.status_code in (302, 307)
    assert response.headers["location"] == "https://signed.example.com/file"


def test_list_documents_filters_by_review_status(api_client, auth_header, db_session):
    from core.db import repository

    repository.create_source_family(db_session, key="constitucional", display_name="Corte Constitucional")
    source = repository.create_source(db_session, family_key="constitucional", name="Corte Constitucional", family_params={})
    useful_doc = repository.insert_document(
        db_session,
        doc_id="doc-useful",
        source_id=source.id,
        title="Útil",
        storage_bucket="iurisync-test",
        storage_key="a.pdf",
    )
    repository.insert_document(
        db_session,
        doc_id="doc-pending",
        source_id=source.id,
        title="Pendiente",
        storage_bucket="iurisync-test",
        storage_key="b.pdf",
    )
    repository.update_document_review_status(db_session, useful_doc.id, "useful")

    response = api_client.get("/documents", params={"review_status": "useful"}, headers=auth_header)

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["doc_id"] == "doc-useful"
    assert body["items"][0]["review_status"] == "useful"


def test_patch_document_review_status_updates_and_returns_document(api_client, auth_header, db_session):
    from core.db import repository

    repository.create_source_family(db_session, key="constitucional", display_name="Corte Constitucional")
    source = repository.create_source(db_session, family_key="constitucional", name="Corte Constitucional", family_params={})
    document = repository.insert_document(
        db_session,
        doc_id="doc-1",
        source_id=source.id,
        title="T-065/24",
        storage_bucket="iurisync-test",
        storage_key="a.pdf",
    )

    response = api_client.patch(
        f"/documents/{document.id}", json={"review_status": "not_useful"}, headers=auth_header
    )

    assert response.status_code == 200
    body = response.json()
    assert body["review_status"] == "not_useful"
    assert body["reviewed_at"] is not None


def test_patch_document_review_status_returns_404_when_missing(api_client, auth_header):
    response = api_client.patch("/documents/999999", json={"review_status": "useful"}, headers=auth_header)
    assert response.status_code == 404


def test_patch_document_review_status_rejects_invalid_value(api_client, auth_header, db_session):
    from core.db import repository

    repository.create_source_family(db_session, key="constitucional", display_name="Corte Constitucional")
    source = repository.create_source(db_session, family_key="constitucional", name="Corte Constitucional", family_params={})
    document = repository.insert_document(
        db_session,
        doc_id="doc-1",
        source_id=source.id,
        title="T-065/24",
        storage_bucket="iurisync-test",
        storage_key="a.pdf",
    )

    response = api_client.patch(
        f"/documents/{document.id}", json={"review_status": "maybe"}, headers=auth_header
    )

    assert response.status_code == 422


def test_patch_document_title_updates_and_returns_document(api_client, auth_header, db_session):
    from core.db import repository

    repository.create_source_family(db_session, key="constitucional", display_name="Corte Constitucional")
    source = repository.create_source(db_session, family_key="constitucional", name="Corte Constitucional", family_params={})
    document = repository.insert_document(
        db_session,
        doc_id="doc-1",
        source_id=source.id,
        title="T065_24",
        storage_bucket="iurisync-test",
        storage_key="a.pdf",
    )

    response = api_client.patch(
        f"/documents/{document.id}/title", json={"title": "ST065_24 (corregido a mano)"}, headers=auth_header
    )

    assert response.status_code == 200
    assert response.json()["title"] == "ST065_24 (corregido a mano)"


def test_patch_document_title_strips_surrounding_whitespace(api_client, auth_header, db_session):
    from core.db import repository

    repository.create_source_family(db_session, key="constitucional", display_name="Corte Constitucional")
    source = repository.create_source(db_session, family_key="constitucional", name="Corte Constitucional", family_params={})
    document = repository.insert_document(
        db_session,
        doc_id="doc-1",
        source_id=source.id,
        title="T065_24",
        storage_bucket="iurisync-test",
        storage_key="a.pdf",
    )

    response = api_client.patch(
        f"/documents/{document.id}/title", json={"title": "  Título con espacios  "}, headers=auth_header
    )

    assert response.status_code == 200
    assert response.json()["title"] == "Título con espacios"


def test_patch_document_title_rejects_blank_value(api_client, auth_header, db_session):
    from core.db import repository

    repository.create_source_family(db_session, key="constitucional", display_name="Corte Constitucional")
    source = repository.create_source(db_session, family_key="constitucional", name="Corte Constitucional", family_params={})
    document = repository.insert_document(
        db_session,
        doc_id="doc-1",
        source_id=source.id,
        title="T065_24",
        storage_bucket="iurisync-test",
        storage_key="a.pdf",
    )

    response = api_client.patch(f"/documents/{document.id}/title", json={"title": "   "}, headers=auth_header)

    assert response.status_code == 422


def test_patch_document_title_returns_404_when_missing(api_client, auth_header):
    response = api_client.patch("/documents/999999/title", json={"title": "Nuevo título"}, headers=auth_header)
    assert response.status_code == 404


def test_patch_document_title_dispatches_storage_sync(api_client, auth_header, db_session, monkeypatch):
    from core.db import repository

    repository.create_source_family(db_session, key="constitucional", display_name="Corte Constitucional")
    source = repository.create_source(db_session, family_key="constitucional", name="Corte Constitucional", family_params={})
    document = repository.insert_document(
        db_session, doc_id="doc-title-sync", source_id=source.id, title="T-065/24",
        storage_bucket="iurisync-test", storage_key="a.pdf",
    )

    called = []
    monkeypatch.setattr(
        "api.routers.documents.reconcile_document_task.delay", lambda document_id: called.append(document_id)
    )

    response = api_client.patch(
        f"/documents/{document.id}/title", json={"title": "T-065/24 corregido"}, headers=auth_header
    )

    assert response.status_code == 200
    assert called == [document.id]


def test_bulk_patch_document_review_status_updates_multiple(api_client, auth_header, db_session):
    from core.db import repository

    repository.create_source_family(db_session, key="constitucional", display_name="Corte Constitucional")
    source = repository.create_source(db_session, family_key="constitucional", name="Corte Constitucional", family_params={})
    doc1 = repository.insert_document(
        db_session, doc_id="doc-1", source_id=source.id, title="Uno",
        storage_bucket="iurisync-test", storage_key="a.pdf",
    )
    doc2 = repository.insert_document(
        db_session, doc_id="doc-2", source_id=source.id, title="Dos",
        storage_bucket="iurisync-test", storage_key="b.pdf",
    )

    response = api_client.patch(
        "/documents/bulk-review",
        json={"document_ids": [doc1.id, doc2.id], "review_status": "useful"},
        headers=auth_header,
    )

    assert response.status_code == 200
    assert response.json() == {"updated": 2}


def test_bulk_patch_document_review_status_rejects_empty_list(api_client, auth_header):
    response = api_client.patch(
        "/documents/bulk-review",
        json={"document_ids": [], "review_status": "useful"},
        headers=auth_header,
    )

    assert response.status_code == 422


def test_bulk_patch_document_review_status_rejects_invalid_value(api_client, auth_header, db_session):
    from core.db import repository

    repository.create_source_family(db_session, key="constitucional", display_name="Corte Constitucional")
    source = repository.create_source(db_session, family_key="constitucional", name="Corte Constitucional", family_params={})
    doc1 = repository.insert_document(
        db_session, doc_id="doc-1", source_id=source.id, title="Uno",
        storage_bucket="iurisync-test", storage_key="a.pdf",
    )

    response = api_client.patch(
        "/documents/bulk-review",
        json={"document_ids": [doc1.id], "review_status": "maybe"},
        headers=auth_header,
    )

    assert response.status_code == 422


def test_bulk_patch_document_review_status_does_not_collide_with_single_patch_route(api_client, auth_header, db_session):
    # Regresión del orden de rutas: /documents/bulk-review no debe ser
    # capturada por /documents/{document_id} (que intentaría parsear
    # "bulk-review" como int y fallaría con un 422 distinto/incorrecto).
    from core.db import repository

    repository.create_source_family(db_session, key="constitucional", display_name="Corte Constitucional")
    source = repository.create_source(db_session, family_key="constitucional", name="Corte Constitucional", family_params={})
    doc1 = repository.insert_document(
        db_session, doc_id="doc-1", source_id=source.id, title="Uno",
        storage_bucket="iurisync-test", storage_key="a.pdf",
    )

    response = api_client.patch(
        "/documents/bulk-review",
        json={"document_ids": [doc1.id], "review_status": "useful"},
        headers=auth_header,
    )

    assert response.status_code == 200
    assert response.json() == {"updated": 1}


def test_preview_pdf_document_redirects_to_original_file(api_client, auth_header, db_session, monkeypatch):
    from core.db import repository

    repository.create_source_family(db_session, key="constitucional", display_name="Corte Constitucional")
    source = repository.create_source(db_session, family_key="constitucional", name="Corte Constitucional", family_params={})
    document = repository.insert_document(
        db_session,
        doc_id="doc-preview-pdf",
        source_id=source.id,
        title="T-065/24",
        storage_bucket="iurisync-test",
        storage_key="Corte Constitucional/2024-02-01/Sentencia/T-065-24.pdf",
        content_type="application/pdf",
    )

    monkeypatch.setattr(
        "api.routers.documents.presigned_url", lambda bucket, key, **kwargs: f"https://signed.example.com/{key}"
    )

    response = api_client.get(f"/documents/{document.id}/preview", headers=auth_header)

    assert response.status_code == 200
    assert response.json()["url"] == "https://signed.example.com/Corte Constitucional/2024-02-01/Sentencia/T-065-24.pdf"


def test_preview_sets_response_content_disposition_from_the_document_title(api_client, auth_header, db_session, monkeypatch):
    """The browser's OWN pdf viewer chrome (not just our UI) reads its suggested
    download filename from the response's Content-Disposition header — since we
    hand it a presigned URL rather than proxying bytes through a Blob, that hint
    has to be baked into the presigned URL itself via ResponseContentDisposition."""
    from core.db import repository

    repository.create_source_family(db_session, key="constitucional", display_name="Corte Constitucional")
    source = repository.create_source(db_session, family_key="constitucional", name="Corte Constitucional", family_params={})
    document = repository.insert_document(
        db_session,
        doc_id="doc-preview-disposition",
        source_id=source.id,
        title="T-065/24",
        storage_bucket="iurisync-test",
        storage_key="Corte Constitucional/2024-02-01/Sentencia/T-065-24.pdf",
        content_type="application/pdf",
    )

    captured = {}

    def _fake_presigned_url(bucket, key, **kwargs):
        captured["response_content_disposition"] = kwargs.get("response_content_disposition")
        return f"https://signed.example.com/{key}"

    monkeypatch.setattr("api.routers.documents.presigned_url", _fake_presigned_url)

    response = api_client.get(f"/documents/{document.id}/preview", headers=auth_header)

    assert response.status_code == 200
    assert captured["response_content_disposition"] == 'inline; filename="T-065-24.pdf"'


def test_preview_rtf_document_with_cached_preview_redirects_without_calling_celery(api_client, auth_header, db_session, monkeypatch):
    from core.db import repository

    repository.create_source_family(db_session, key="constitucional", display_name="Corte Constitucional")
    source = repository.create_source(db_session, family_key="constitucional", name="Corte Constitucional", family_params={})
    document = repository.insert_document(
        db_session,
        doc_id="doc-preview-cached",
        source_id=source.id,
        title="T-200/26",
        storage_bucket="iurisync-test",
        storage_key="Corte Constitucional/2026-06-30/Tutela/T-200-26.rtf",
        content_type="application/rtf",
    )
    repository.set_document_preview_key(db_session, document.id, "Corte Constitucional/2026-06-30/Tutela/T-200-26.preview.pdf")

    monkeypatch.setattr(
        "api.routers.documents.presigned_url", lambda bucket, key, **kwargs: f"https://signed.example.com/{key}"
    )

    def _fail_if_called(*_args, **_kwargs):
        raise AssertionError("no debería encolar la tarea si ya hay un preview cacheado")

    monkeypatch.setattr("api.routers.documents.generate_document_preview_pdf", _fail_if_called)

    response = api_client.get(f"/documents/{document.id}/preview", headers=auth_header)

    assert response.status_code == 200
    assert response.json()["url"] == "https://signed.example.com/Corte Constitucional/2026-06-30/Tutela/T-200-26.preview.pdf"


def test_preview_prefers_preset_preview_key_over_on_demand_conversion(api_client, auth_header, db_session, monkeypatch):
    """Regression test: for sources whose native format is PDF (e.g. JEP) but are stored
    as RTF for download, preview_storage_key is pre-set at scrape time to the untouched
    original PDF. That must win over the content_type-based on-demand conversion path —
    re-deriving a preview from the RTF would reconstruct it via a PDF-import round-trip,
    which can silently drop visible body text."""
    from core.db import repository

    repository.create_source_family(db_session, key="jep", display_name="JEP")
    source = repository.create_source(db_session, family_key="jep", name="JEP", family_params={})
    document = repository.insert_document(
        db_session,
        doc_id="doc-preview-preset-original",
        source_id=source.id,
        title="SAI-AOI-RC-PMA-320-2026",
        storage_bucket="iurisync-test",
        storage_key="JEP/2026-06-12/Resolución/SAI-AOI-RC-PMA-320-2026.rtf",
        content_type="application/rtf",
        preview_storage_key="JEP/2026-06-12/Resolución/SAI-AOI-RC-PMA-320-2026.preview.pdf",
    )

    monkeypatch.setattr(
        "api.routers.documents.presigned_url", lambda bucket, key, **kwargs: f"https://signed.example.com/{key}"
    )

    def _fail_if_called(*_args, **_kwargs):
        raise AssertionError("no debería intentar una conversión bajo demanda si ya hay un preview_storage_key")

    monkeypatch.setattr("api.routers.documents.generate_document_preview_pdf", _fail_if_called)

    response = api_client.get(f"/documents/{document.id}/preview", headers=auth_header)

    assert response.status_code == 200
    assert (
        response.json()["url"]
        == "https://signed.example.com/JEP/2026-06-12/Resolución/SAI-AOI-RC-PMA-320-2026.preview.pdf"
    )


def test_preview_rtf_document_without_cache_triggers_conversion_and_redirects(api_client, auth_header, db_session, monkeypatch):
    from core.db import repository

    repository.create_source_family(db_session, key="constitucional", display_name="Corte Constitucional")
    source = repository.create_source(db_session, family_key="constitucional", name="Corte Constitucional", family_params={})
    document = repository.insert_document(
        db_session,
        doc_id="doc-preview-new",
        source_id=source.id,
        title="T-202/26",
        storage_bucket="iurisync-test",
        storage_key="Corte Constitucional/2026-06-30/Tutela/T-202-26.rtf",
        content_type="application/rtf",
    )

    monkeypatch.setattr(
        "api.routers.documents.presigned_url", lambda bucket, key, **kwargs: f"https://signed.example.com/{key}"
    )

    class _FakeAsyncResult:
        def get(self, timeout=None):
            return "Corte Constitucional/2026-06-30/Tutela/T-202-26.preview.pdf"

    class _FakeTask:
        def delay(self, document_id):
            return _FakeAsyncResult()

    monkeypatch.setattr("api.routers.documents.generate_document_preview_pdf", _FakeTask())

    response = api_client.get(f"/documents/{document.id}/preview", headers=auth_header)

    assert response.status_code == 200
    assert response.json()["url"] == "https://signed.example.com/Corte Constitucional/2026-06-30/Tutela/T-202-26.preview.pdf"


def test_preview_returns_504_when_conversion_task_times_out(api_client, auth_header, db_session, monkeypatch):
    from celery.exceptions import TimeoutError as CeleryTimeoutError

    from core.db import repository

    repository.create_source_family(db_session, key="constitucional", display_name="Corte Constitucional")
    source = repository.create_source(db_session, family_key="constitucional", name="Corte Constitucional", family_params={})
    document = repository.insert_document(
        db_session,
        doc_id="doc-preview-timeout",
        source_id=source.id,
        title="T-203/26",
        storage_bucket="iurisync-test",
        storage_key="Corte Constitucional/2026-06-30/Tutela/T-203-26.rtf",
        content_type="application/rtf",
    )

    class _FakeAsyncResult:
        def get(self, timeout=None):
            raise CeleryTimeoutError()

    class _FakeTask:
        def delay(self, document_id):
            return _FakeAsyncResult()

    monkeypatch.setattr("api.routers.documents.generate_document_preview_pdf", _FakeTask())

    response = api_client.get(f"/documents/{document.id}/preview", headers=auth_header, follow_redirects=False)

    assert response.status_code == 504
    assert response.json()["detail"] == "La vista previa está tardando más de lo esperado, intenta de nuevo"


def test_preview_returns_502_when_conversion_fails(api_client, auth_header, db_session, monkeypatch):
    from core.db import repository

    repository.create_source_family(db_session, key="constitucional", display_name="Corte Constitucional")
    source = repository.create_source(db_session, family_key="constitucional", name="Corte Constitucional", family_params={})
    document = repository.insert_document(
        db_session,
        doc_id="doc-preview-fail",
        source_id=source.id,
        title="T-204/26",
        storage_bucket="iurisync-test",
        storage_key="Corte Constitucional/2026-06-30/Tutela/T-204-26.rtf",
        content_type="application/rtf",
    )

    class _FakeAsyncResult:
        def get(self, timeout=None):
            raise RuntimeError("Word no disponible")

    class _FakeTask:
        def delay(self, document_id):
            return _FakeAsyncResult()

    monkeypatch.setattr("api.routers.documents.generate_document_preview_pdf", _FakeTask())

    response = api_client.get(f"/documents/{document.id}/preview", headers=auth_header, follow_redirects=False)

    assert response.status_code == 502
    assert response.json()["detail"] == "No se pudo generar la vista previa"


def test_preview_returns_404_for_a_non_convertible_content_type(api_client, auth_header, db_session):
    from core.db import repository

    repository.create_source_family(db_session, key="constitucional", display_name="Corte Constitucional")
    source = repository.create_source(db_session, family_key="constitucional", name="Corte Constitucional", family_params={})
    document = repository.insert_document(
        db_session,
        doc_id="doc-preview-unsupported",
        source_id=source.id,
        title="Reporte",
        storage_bucket="iurisync-test",
        storage_key="Corte Constitucional/2026-06-30/Otro/reporte.txt",
        content_type="text/plain",
    )

    response = api_client.get(f"/documents/{document.id}/preview", headers=auth_header, follow_redirects=False)

    assert response.status_code == 404
    assert response.json()["detail"] == "Vista previa no disponible para este tipo de archivo"


def test_get_document_versions_lists_most_recently_superseded_first(api_client, auth_header, db_session):
    from core.db import repository

    repository.create_source_family(db_session, key="constitucional", display_name="Corte Constitucional")
    source = repository.create_source(db_session, family_key="constitucional", name="Corte Constitucional", family_params={})
    document = repository.insert_document(
        db_session, doc_id="doc-v", source_id=source.id, title="A. 1/26",
        storage_bucket="iurisync-test", storage_key="v1.rtf", file_size_bytes=100,
    )
    repository.archive_and_replace_document(
        db_session, document.id, storage_bucket="iurisync-test", storage_key="v2.rtf", file_size_bytes=200
    )
    repository.archive_and_replace_document(
        db_session, document.id, storage_bucket="iurisync-test", storage_key="v3.rtf", file_size_bytes=300
    )

    response = api_client.get(f"/documents/{document.id}/versions", headers=auth_header)

    assert response.status_code == 200
    body = response.json()
    assert [v["file_size_bytes"] for v in body] == [200, 100]


def test_get_document_versions_returns_empty_list_for_a_document_with_no_history(api_client, auth_header, db_session):
    from core.db import repository

    repository.create_source_family(db_session, key="constitucional", display_name="Corte Constitucional")
    source = repository.create_source(db_session, family_key="constitucional", name="Corte Constitucional", family_params={})
    document = repository.insert_document(
        db_session, doc_id="doc-no-versions", source_id=source.id, title="A. 2/26",
        storage_bucket="iurisync-test", storage_key="only.rtf", file_size_bytes=50,
    )

    response = api_client.get(f"/documents/{document.id}/versions", headers=auth_header)

    assert response.status_code == 200
    assert response.json() == []


def test_get_document_versions_returns_404_for_a_document_that_does_not_exist(api_client, auth_header):
    """Regression test: this used to return 200 with an empty list for ANY
    nonexistent document_id, indistinguishable from a real document that
    simply has no version history yet."""
    response = api_client.get("/documents/999999/versions", headers=auth_header)
    assert response.status_code == 404


def test_get_document_version_download_returns_404_for_a_version_of_another_document(api_client, auth_header, db_session):
    from core.db import repository

    repository.create_source_family(db_session, key="constitucional", display_name="Corte Constitucional")
    source = repository.create_source(db_session, family_key="constitucional", name="Corte Constitucional", family_params={})
    document_a = repository.insert_document(
        db_session, doc_id="doc-a", source_id=source.id, title="A", storage_bucket="iurisync-test",
        storage_key="a.rtf", file_size_bytes=10,
    )
    document_b = repository.insert_document(
        db_session, doc_id="doc-b", source_id=source.id, title="B", storage_bucket="iurisync-test",
        storage_key="b.rtf", file_size_bytes=10,
    )
    repository.archive_and_replace_document(
        db_session, document_b.id, storage_bucket="iurisync-test", storage_key="b-v2.rtf", file_size_bytes=20
    )
    [version_of_b] = repository.list_document_versions(db_session, document_b.id)

    response = api_client.get(f"/documents/{document_a.id}/versions/{version_of_b.id}/download", headers=auth_header)

    assert response.status_code == 404


def test_get_document_version_download_returns_signed_url(api_client, auth_header, db_session):
    from core.db import repository

    repository.create_source_family(db_session, key="constitucional", display_name="Corte Constitucional")
    source = repository.create_source(db_session, family_key="constitucional", name="Corte Constitucional", family_params={})
    document = repository.insert_document(
        db_session, doc_id="doc-download-version", source_id=source.id, title="A. 3/26",
        storage_bucket="iurisync-test", storage_key="v1.rtf", file_size_bytes=10,
    )
    repository.archive_and_replace_document(
        db_session, document.id, storage_bucket="iurisync-test", storage_key="v2.rtf", file_size_bytes=20
    )
    [version] = repository.list_document_versions(db_session, document.id)

    response = api_client.get(f"/documents/{document.id}/versions/{version.id}/download", headers=auth_header)

    assert response.status_code == 200
    assert "url" in response.json()


def test_get_documents_general_listing_shows_only_the_most_recent_actuacion(api_client, auth_header, db_session):
    from datetime import date

    from core.db import repository

    repository.create_source_family(db_session, key="rama_judicial", display_name="Rama Judicial")
    source = repository.create_source(
        db_session, family_key="rama_judicial", name="Tribunal Superior de Bogotá", family_params={}
    )
    shared_title = "T_BTA_11001_31_03_048_2022_00418_02"
    repository.insert_document(
        db_session, doc_id="doc-old", source_id=source.id, title=shared_title,
        storage_bucket="iurisync-test", storage_key="a.pdf", f_public=date(2026, 6, 16),
    )
    repository.insert_document(
        db_session, doc_id="doc-new", source_id=source.id, title=shared_title,
        storage_bucket="iurisync-test", storage_key="b.pdf", f_public=date(2026, 7, 17),
    )

    response = api_client.get("/documents", params={"family_key": "rama_judicial"}, headers=auth_header)

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["doc_id"] == "doc-new"
    assert body["items"][0]["case_document_count"] == 2


def test_get_documents_title_exact_still_returns_every_actuacion_uncollapsed(api_client, auth_header, db_session):
    """The case-view modal fetches a case's members via title_exact — that fetch
    must never be collapsed, or the modal would only ever show one document."""
    from datetime import date

    from core.db import repository

    repository.create_source_family(db_session, key="rama_judicial", display_name="Rama Judicial")
    source = repository.create_source(
        db_session, family_key="rama_judicial", name="Tribunal Superior de Bogotá", family_params={}
    )
    shared_title = "T_BTA_11001_31_03_048_2022_00418_02"
    repository.insert_document(
        db_session, doc_id="doc-old", source_id=source.id, title=shared_title,
        storage_bucket="iurisync-test", storage_key="a.pdf", f_public=date(2026, 6, 16),
    )
    repository.insert_document(
        db_session, doc_id="doc-new", source_id=source.id, title=shared_title,
        storage_bucket="iurisync-test", storage_key="b.pdf", f_public=date(2026, 7, 17),
    )

    response = api_client.get(
        "/documents", params={"family_key": "rama_judicial", "title_exact": shared_title}, headers=auth_header
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    assert {item["doc_id"] for item in body["items"]} == {"doc-old", "doc-new"}


def test_get_document_stats_does_not_cap_by_source_or_by_tipo_at_eight(api_client, auth_header, db_session):
    # Regression guard: count_documents_by_source/count_documents_by_tipo used
    # to hard-cap results at limit=8 (ordered by count desc), so a low-volume
    # source or tipo past the top 8 silently never reached the dashboard —
    # e.g. a newly added source with few documents so far.
    from datetime import date

    from core.db import repository

    repository.create_source_family(db_session, key="constitucional", display_name="Corte Constitucional")

    tipos = [f"Tipo{i}" for i in range(10)]
    for i in range(10):
        source = repository.create_source(
            db_session, family_key="constitucional", name=f"Fuente {i}", family_params={}
        )
        for j in range(10 - i):
            repository.insert_document(
                db_session,
                doc_id=f"doc-{i}-{j}",
                source_id=source.id,
                title=f"Documento {i}-{j}",
                tipo=tipos[i],
                storage_bucket="iurisync-test",
                storage_key=f"doc-{i}-{j}.pdf",
                f_public=date(2026, 3, 10),
            )

    response = api_client.get("/documents/stats", headers=auth_header)

    assert response.status_code == 200
    body = response.json()
    assert len(body["by_source"]) == 10
    assert {row["name"] for row in body["by_source"]} == {f"Fuente {i}" for i in range(10)}
    assert len(body["by_tipo"]) == 10
    assert {row["tipo"] for row in body["by_tipo"]} == set(tipos)
    assert [row["count"] for row in body["by_source"]] == sorted(
        (row["count"] for row in body["by_source"]), reverse=True
    )
    assert [row["count"] for row in body["by_tipo"]] == sorted(
        (row["count"] for row in body["by_tipo"]), reverse=True
    )


def test_get_document_stats_by_source_can_be_scoped_to_a_month(api_client, auth_header, db_session):
    # Regression + feature test: by_source defaults to the all-time total
    # (unchanged from today), but passing year+month scopes it down to just
    # that month — using the same effective date (f_public, falling back to
    # downloaded_at) that by_month already uses.
    from datetime import date

    from core.db import repository

    repository.create_source_family(db_session, key="constitucional", display_name="Corte Constitucional")
    source = repository.create_source(
        db_session, family_key="constitucional", name="Corte Constitucional", family_params={}
    )

    repository.insert_document(
        db_session, doc_id="doc-marzo", source_id=source.id, title="Doc marzo",
        tipo="Sentencia", storage_bucket="iurisync-test", storage_key="doc-marzo.pdf",
        f_public=date(2026, 3, 15),
    )
    repository.insert_document(
        db_session, doc_id="doc-abril-1", source_id=source.id, title="Doc abril 1",
        tipo="Sentencia", storage_bucket="iurisync-test", storage_key="doc-abril-1.pdf",
        f_public=date(2026, 4, 5),
    )
    repository.insert_document(
        db_session, doc_id="doc-abril-2", source_id=source.id, title="Doc abril 2",
        tipo="Sentencia", storage_bucket="iurisync-test", storage_key="doc-abril-2.pdf",
        f_public=date(2026, 4, 20),
    )
    repository.insert_document(
        db_session, doc_id="doc-otro-anio", source_id=source.id, title="Doc otro año",
        tipo="Sentencia", storage_bucket="iurisync-test", storage_key="doc-otro-anio.pdf",
        f_public=date(2025, 4, 10),
    )

    # Sin mes: comportamiento actual, total histórico (las 4).
    response = api_client.get("/documents/stats", headers=auth_header)
    assert response.status_code == 200
    by_source = {row["name"]: row["count"] for row in response.json()["by_source"]}
    assert by_source == {"Corte Constitucional": 4}

    # Con mes: solo abril de 2026 (2 documentos) — no marzo de 2026 ni abril de 2025.
    response = api_client.get("/documents/stats", params={"year": 2026, "month": 4}, headers=auth_header)
    assert response.status_code == 200
    by_source = {row["name"]: row["count"] for row in response.json()["by_source"]}
    assert by_source == {"Corte Constitucional": 2}


def test_get_document_stats_rejects_month_out_of_range(api_client, auth_header, db_session):
    response = api_client.get("/documents/stats", params={"month": 13}, headers=auth_header)
    assert response.status_code == 422

    response = api_client.get("/documents/stats", params={"month": 0}, headers=auth_header)
    assert response.status_code == 422


def test_get_documents_includes_case_link_note(api_client, db_session, auth_header):
    from core.db import repository

    repository.create_source_family_if_missing(db_session, key="samai", display_name="SAMAI")
    tribunal = repository.create_source(db_session, family_key="samai", name="Tribunal Administrativo de Antioquia", family_params={})
    consejo = repository.create_source(db_session, family_key="samai", name="Consejo de Estado", family_params={})
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

    response = api_client.get("/documents", headers=auth_header)

    by_source = {d["source_id"]: d for d in response.json()["items"]}
    assert by_source[tribunal.id]["case_link_id"] is not None
    assert by_source[tribunal.id]["case_link_other_source_name"] == "Consejo de Estado"


def test_get_documents_filters_by_seccion_especialidad_magistrado(api_client, auth_header, db_session):
    from core.db import repository

    repository.create_source_family(db_session, key="constitucional", display_name="Corte Constitucional")
    source = repository.create_source(db_session, family_key="constitucional", name="Corte Constitucional", family_params={})
    repository.insert_document(
        db_session, doc_id="doc-1", source_id=source.id, title="Coincide",
        seccion="SECCION PRIMERA", especialidad="Nulidad", magistrado="Ana Pérez",
        storage_bucket="iurisync-test", storage_key="a.pdf",
    )
    repository.insert_document(
        db_session, doc_id="doc-2", source_id=source.id, title="No coincide",
        seccion="SECCION SEGUNDA", especialidad="Conciliación", magistrado="Luis Gómez",
        storage_bucket="iurisync-test", storage_key="b.pdf",
    )

    response = api_client.get(
        "/documents?seccion=SECCION+PRIMERA&especialidad=Nulidad&magistrado=Ana+P%C3%A9rez",
        headers=auth_header,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["title"] == "Coincide"
