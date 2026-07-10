from typing import Dict, Type

from core.scrapers.base import BaseScrapper

FAMILY_REGISTRY: Dict[str, Type[BaseScrapper]] = {}


def register_family(key: str):
    def _wrap(cls: Type[BaseScrapper]):
        FAMILY_REGISTRY[key] = cls
        return cls

    return _wrap


def resolve_scraper(family_key: str, params: dict) -> BaseScrapper:
    try:
        cls = FAMILY_REGISTRY[family_key]
    except KeyError:
        raise ValueError(f"Familia técnica desconocida: {family_key}")
    return cls(**params)
