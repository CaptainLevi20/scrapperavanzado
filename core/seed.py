from core.db import repository
from core.db.session import SessionLocal
from core.scrapers.families.rama_judicial import JUZGADOS_ENTIDADES, SUPERIORES_DEPTS
from core.scrapers.families.samai import SAMAI_CORPS

_FAMILIES = {
    "constitucional": ("Corte Constitucional", "Buscador de relatoría de la Corte Constitucional"),
    "samai": (
        "SAMAI (Consejo de Estado y Tribunales Administrativos)",
        "Sistema SAMAI del Consejo de Estado; cubre Consejo de Estado y Tribunales Administrativos",
    ),
    "corte_suprema": (
        "Corte Suprema de Justicia",
        "API GraphQL de consulta de providencias de la Corte Suprema de Justicia",
    ),
    "jep": ("Jurisdicción Especial para la Paz", "API de relatoría de la JEP"),
    "cndj": ("Comisión Nacional de Disciplina Judicial", "Buscador de relatoría del CNDJ"),
    "adr": ("Agencia de Desarrollo Rural", "Normativa publicada por la Agencia de Desarrollo Rural"),
    "adres": (
        "Administradora de los Recursos del Sistema General de Seguridad Social en Salud",
        "Normativa publicada por ADRES",
    ),
    "ane": ("Agencia Nacional del Espectro", "Normativa publicada por la Agencia Nacional del Espectro"),
    "anh": ("Agencia Nacional de Hidrocarburos", "Normativa publicada por la Agencia Nacional de Hidrocarburos"),
    "rama_judicial": (
        "Rama Judicial (Tribunales Superiores y Juzgados)",
        "Publicaciones procesales de la Rama Judicial; cubre Tribunales Superiores por departamento y Juzgados por tipo",
    ),
    "mincit": (
        "Ministerio de Comercio, Industria y Turismo",
        "Normativa (resoluciones, decretos, circulares, leyes) publicada por el Ministerio de Comercio, Industria y Turismo",
    ),
    "madr": (
        "Ministerio de Agricultura y Desarrollo Rural",
        "Normativa (leyes, decretos, resoluciones, conpes) publicada por el Ministerio de Agricultura y Desarrollo Rural",
    ),
    "minambiente": (
        "Ministerio de Ambiente y Desarrollo Sostenible",
        "Normativa (resoluciones, decretos, leyes, autos, conpes, circulares, conceptos) publicada por el Ministerio de "
        "Ambiente y Desarrollo Sostenible",
    ),
    "minvivienda": (
        "Ministerio de Vivienda, Ciudad y Territorio",
        "Normativa (resoluciones, decretos, leyes, conpes, acuerdos, directivas, circulares, autos) publicada por el "
        "Ministerio de Vivienda, Ciudad y Territorio",
    ),
    "mineducacion": (
        "Ministerio de Educación Nacional",
        "Normativa (leyes, decretos, resoluciones, circulares, directivas, acuerdos) publicada por el Ministerio de Educación Nacional",
    ),
    "mininterior": (
        "Ministerio del Interior",
        "Normativa (decretos, resoluciones, circulares, leyes, directivas, acuerdos, conceptos, actos administrativos y legislativos) publicada por el Ministerio del Interior",
    ),
    "minenergia": (
        "Ministerio de Minas y Energía",
        "Normativa (decretos, resoluciones, circulares) publicada por el Ministerio de Minas y Energía",
    ),
}


def seed_source_families_and_sources(db) -> None:
    # Each insert below is its own ON CONFLICT DO NOTHING (see
    # create_source_family_if_missing/create_source_if_missing) rather than a
    # "list what already exists, then create what's missing" pass: two seed
    # runs racing each other (`python -m core.seed` launched twice at once, or
    # a future multi-worker startup hook) would otherwise both see nothing
    # existing yet, both try to create the same row, and the loser crashes on
    # a duplicate-key IntegrityError partway through, leaving the catalog
    # incomplete.
    for key, (display_name, description) in _FAMILIES.items():
        repository.create_source_family_if_missing(db, key=key, display_name=display_name, description=description)

    # El equipo de fuentes confirma que todo lo que trae la Corte Constitucional
    # es útil, así que sus documentos deben entrar ya revisados como "useful" en
    # vez de "pending" (worker.scrape_source_task lee este auto_review_status).
    repository.create_source_if_missing(
        db, family_key="constitucional", name="Corte Constitucional", family_params={"auto_review_status": "useful"}
    )

    for corp_code, corp_name in SAMAI_CORPS.items():
        repository.create_source_if_missing(
            db, family_key="samai", name=corp_name, family_params={"corp_code": corp_code, "corp_name": corp_name}
        )

    repository.create_source_if_missing(db, family_key="corte_suprema", name="CSJ", family_params={})

    repository.create_source_if_missing(db, family_key="jep", name="JEP", family_params={})

    repository.create_source_if_missing(
        db, family_key="cndj", name="Comisión Nacional de Disciplina Judicial", family_params={}
    )

    repository.create_source_if_missing(db, family_key="adr", name="Agencia de Desarrollo Rural", family_params={})

    adres_name = "Administradora de los Recursos del Sistema General de Seguridad Social en Salud"
    repository.create_source_if_missing(db, family_key="adres", name=adres_name, family_params={})

    repository.create_source_if_missing(db, family_key="ane", name="Agencia Nacional del Espectro", family_params={})

    repository.create_source_if_missing(db, family_key="anh", name="Agencia Nacional de Hidrocarburos", family_params={})

    for dept_code, dept_name in SUPERIORES_DEPTS.items():
        repository.create_source_if_missing(
            db,
            family_key="rama_judicial",
            name=dept_name,
            family_params={"dept_code": dept_code, "dept_name": dept_name, "entidad_id": "22"},
        )

    for juz_id, juz_name in JUZGADOS_ENTIDADES.items():
        repository.create_source_if_missing(
            db,
            family_key="rama_judicial",
            name=juz_name,
            family_params={"dept_code": "", "dept_name": juz_name, "entidad_id": juz_id},
        )

    repository.create_source_if_missing(
        db, family_key="mincit", name="Ministerio de Comercio, Industria y Turismo", family_params={}
    )

    repository.create_source_if_missing(
        db, family_key="madr", name="Ministerio de Agricultura y Desarrollo Rural", family_params={}
    )

    repository.create_source_if_missing(
        db, family_key="minambiente", name="Ministerio de Ambiente y Desarrollo Sostenible", family_params={}
    )

    repository.create_source_if_missing(
        db, family_key="minvivienda", name="Ministerio de Vivienda, Ciudad y Territorio", family_params={}
    )

    repository.create_source_if_missing(
        db, family_key="mineducacion", name="Ministerio de Educación Nacional", family_params={}
    )

    repository.create_source_if_missing(
        db, family_key="mininterior", name="Ministerio del Interior", family_params={}
    )

    repository.create_source_if_missing(
        db, family_key="minenergia", name="Ministerio de Minas y Energía", family_params={}
    )


def main():
    db = SessionLocal()
    try:
        seed_source_families_and_sources(db)
    finally:
        db.close()


if __name__ == "__main__":
    main()
