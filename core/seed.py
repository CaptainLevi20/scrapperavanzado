from core.db import repository
from core.db.session import SessionLocal
from core.scrapers.families.rama_judicial import JUZGADOS_ENTIDADES, SUPERIORES_DEPTS
from core.scrapers.families.samai import SAMAI_CORPS

_FAMILIES = {
    "constitucional": ("Corte Constitucional", "Buscador de relatoría de la Corte Constitucional"),
    "samai": (
        "SAMAI (Tribunales Administrativos)",
        "Sistema SAMAI del Consejo de Estado; cubre Consejo de Estado y Tribunales Administrativos",
    ),
    "corte_suprema": (
        "Corte Suprema de Justicia",
        "API GraphQL de consulta de providencias de la Corte Suprema de Justicia",
    ),
    "jep": ("Jurisdicción Especial para la Paz", "API de relatoría de la JEP"),
    "cndj": ("Consejo Nacional de Disciplina Judicial", "Buscador de relatoría del CNDJ"),
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
}


def seed_source_families_and_sources(db) -> None:
    existing_families = {f.key for f in repository.list_source_families(db)}
    for key, (display_name, description) in _FAMILIES.items():
        if key not in existing_families:
            repository.create_source_family(db, key=key, display_name=display_name, description=description)

    existing_sources = {s.name for s in repository.list_sources(db)}

    if "Corte Constitucional" not in existing_sources:
        repository.create_source(db, family_key="constitucional", name="Corte Constitucional", family_params={})

    for corp_code, corp_name in SAMAI_CORPS.items():
        if corp_name not in existing_sources:
            repository.create_source(
                db, family_key="samai", name=corp_name, family_params={"corp_code": corp_code, "corp_name": corp_name}
            )

    if "CSJ" not in existing_sources:
        repository.create_source(db, family_key="corte_suprema", name="CSJ", family_params={})

    if "JEP" not in existing_sources:
        repository.create_source(db, family_key="jep", name="JEP", family_params={})

    if "Consejo Nacional de Disciplina Judicial" not in existing_sources:
        repository.create_source(
            db, family_key="cndj", name="Consejo Nacional de Disciplina Judicial", family_params={}
        )

    if "Agencia de Desarrollo Rural" not in existing_sources:
        repository.create_source(db, family_key="adr", name="Agencia de Desarrollo Rural", family_params={})

    adres_name = "Administradora de los Recursos del Sistema General de Seguridad Social en Salud"
    if adres_name not in existing_sources:
        repository.create_source(db, family_key="adres", name=adres_name, family_params={})

    if "Agencia Nacional del Espectro" not in existing_sources:
        repository.create_source(db, family_key="ane", name="Agencia Nacional del Espectro", family_params={})

    if "Agencia Nacional de Hidrocarburos" not in existing_sources:
        repository.create_source(db, family_key="anh", name="Agencia Nacional de Hidrocarburos", family_params={})

    for dept_code, dept_name in SUPERIORES_DEPTS.items():
        if dept_name not in existing_sources:
            repository.create_source(
                db,
                family_key="rama_judicial",
                name=dept_name,
                family_params={"dept_code": dept_code, "dept_name": dept_name, "entidad_id": "22"},
            )

    for juz_id, juz_name in JUZGADOS_ENTIDADES.items():
        if juz_name not in existing_sources:
            repository.create_source(
                db,
                family_key="rama_judicial",
                name=juz_name,
                family_params={"dept_code": "", "dept_name": juz_name, "entidad_id": juz_id},
            )


def main():
    db = SessionLocal()
    try:
        seed_source_families_and_sources(db)
    finally:
        db.close()


if __name__ == "__main__":
    main()
