import responses

from core.scrapers.families.jep import ScrapJEP, _extraer_tipo
from core.scrapers.registry import FAMILY_REGISTRY

_URL = "https://relatoria.jep.gov.co/listarProvidecias"


@responses.activate
def test_scrap_filters_by_year_and_deduplicates():
    responses.add(
        responses.GET,
        _URL,
        json=[
            {
                "id": 1, "fecha": 2024, "radicado": "SRVR-003",
                "nombre": "S - Sala de Amnistía o Indulto",
                "hipervinculo": "docs/Auto_SRVR-003_06-julio-2024.pdf",
            },
            {
                "id": 2, "fecha": 2024, "radicado": "SRVR-003",
                "nombre": "S - Sala de Amnistía o Indulto",
                "hipervinculo": "docs/Auto_SRVR-003_06-julio-2024.pdf",  # mismo hipervinculo → duplicado
            },
            {
                "id": 3, "fecha": 2018, "radicado": "SRVR-004",
                "nombre": "S - Sala de Amnistía o Indulto",
                "hipervinculo": "docs/Auto_SRVR-004_01-enero-2018.pdf",  # fuera del rango de año
            },
            {"id": 4, "fecha": 2024, "radicado": "No Aplica", "nombre": "", "hipervinculo": ""},  # placeholder
        ],
        status=200,
    )

    scraper = ScrapJEP()
    docs = scraper.scrap(fini="2023-01-01", ffin="2025-12-31")

    assert len(docs) == 1
    doc = docs[0]
    assert doc.title == "SRVR-003"
    assert doc.tipo == "Auto"
    assert doc.seccion == "S - Sala de Amnistía o Indulto"
    assert doc.seccion_en_carpeta is False
    assert doc.f_public == "2024-01-01"
    assert doc.link == {"url": "https://relatoria.jep.gov.co/docs/Auto_SRVR-003_06-julio-2024.pdf", "method": "GET"}
    assert doc.save_path == "JEP/2024-01-01/Auto/SRVR-003-1(extension)"


def test_extraer_tipo_prefers_compound_prefixes():
    assert _extraer_tipo("docs/SV-AV_2024.pdf") == "Salvamento y Aclaración de Voto"
    assert _extraer_tipo("docs/SV_2024.pdf") == "Salvamento de Voto"
    assert _extraer_tipo("docs/AV_2024.pdf") == "Aclaración de Voto"
    assert _extraer_tipo("docs/Sentencia_2024.pdf") == "Sentencia"
    assert _extraer_tipo("docs/Desconocido_2024.pdf") == ""


def test_jep_is_registered_under_its_family_key():
    import core.scrapers.families  # noqa: F401

    assert FAMILY_REGISTRY["jep"] is ScrapJEP
