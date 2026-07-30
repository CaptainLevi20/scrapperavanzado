from core.scrapers.registry import FAMILY_REGISTRY


def test_mincit_is_registered_under_its_family_key():
    import core.scrapers.families  # noqa: F401

    assert FAMILY_REGISTRY["mincit"].__name__ == "ScrapMINCIT"


def test_scrap_returns_empty_list_by_default():
    from core.scrapers.families.mincit import ScrapMINCIT

    scraper = ScrapMINCIT()
    assert scraper.scrap(fini="2024-01-01", ffin="2024-12-31") == []
