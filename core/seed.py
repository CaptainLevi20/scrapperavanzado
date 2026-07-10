from core.db import repository
from core.db.session import SessionLocal
from core.scrapers.families.samai import SAMAI_CORPS

_FAMILIES = {
    "constitucional": ("Corte Constitucional", "Buscador de relatoría de la Corte Constitucional"),
    "samai": (
        "SAMAI (Tribunales Administrativos)",
        "Sistema SAMAI del Consejo de Estado; cubre Consejo de Estado y Tribunales Administrativos",
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


def main():
    db = SessionLocal()
    try:
        seed_source_families_and_sources(db)
    finally:
        db.close()


if __name__ == "__main__":
    main()
