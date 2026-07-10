import pytest

from core.scrapers.base import BaseScrapper
from core.scrapers.registry import FAMILY_REGISTRY, register_family, resolve_scraper


def test_register_family_adds_class_to_registry():
    @register_family("dummy")
    class DummyScraper(BaseScrapper):
        def __init__(self, greeting="hi"):
            self.greeting = greeting

        def scrap(self, fini, ffin, **kwargs):
            return [self.greeting]

    assert FAMILY_REGISTRY["dummy"] is DummyScraper


def test_resolve_scraper_instantiates_with_params():
    scraper = resolve_scraper("dummy", {"greeting": "hola"})
    assert scraper.scrap("2026-01-01", "2026-01-02") == ["hola"]


def test_resolve_scraper_raises_for_unknown_family():
    with pytest.raises(ValueError, match="desconocida"):
        resolve_scraper("no-existe", {})
