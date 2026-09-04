from core.scrapers.registry import FAMILY_REGISTRY


def test_superfinanciera_is_registered_under_its_family_key():
    import core.scrapers.families  # noqa: F401

    assert FAMILY_REGISTRY["superfinanciera"].__name__ == "ScrapSuperfinanciera"


def test_superfinanciera_scraper_source_name():
    import core.scrapers.families  # noqa: F401

    scraper = FAMILY_REGISTRY["superfinanciera"]()
    assert scraper.source == "Superintendencia Financiera de Colombia"


def test_superfinanciera_scrap_returns_empty_list_with_no_data(monkeypatch):
    import core.scrapers.families  # noqa: F401
    from core.scrapers.families.superfinanciera import normativa, conceptos

    monkeypatch.setattr(normativa, "scrap_normativa", lambda *a, **k: [])
    monkeypatch.setattr(conceptos, "scrap_conceptos", lambda *a, **k: [])
    scraper = FAMILY_REGISTRY["superfinanciera"]()
    assert scraper.scrap(fini="2026-01-01", ffin="2026-01-31", on_progress=lambda m: None) == []
