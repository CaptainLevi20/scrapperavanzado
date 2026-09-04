from typing import List

from core.models import RawDocModel
from core.scrapers.base import BaseScrapper
from core.scrapers.registry import register_family
from core.scrapers.families.superfinanciera import conceptos, normativa

_SOURCE = "Superintendencia Financiera de Colombia"


@register_family("superfinanciera")
class ScrapSuperfinanciera(BaseScrapper):
    def __init__(self):
        self.source = _SOURCE

    def scrap(self, fini, ffin, q="", limit=10000, stop_event=None, on_progress=None) -> List[RawDocModel]:
        docs: List[RawDocModel] = []
        docs.extend(
            normativa.scrap_normativa(
                fini, ffin, self.source, limit=limit, stop_event=stop_event, on_progress=on_progress
            )
        )
        if len(docs) >= limit:
            return docs[:limit]
        if stop_event is not None and stop_event.is_set():
            return docs[:limit]
        docs.extend(
            conceptos.scrap_conceptos(
                fini, ffin, self.source, limit=limit - len(docs), stop_event=stop_event, on_progress=on_progress
            )
        )
        return docs[:limit]
