from typing import List, Optional

from pydantic import BaseModel


class RawDocModel(BaseModel):
    source: str
    link: dict
    title: str
    tipo: str
    f_public: str
    f_providencia: Optional[str] = None
    seccion: Optional[str] = None
    seccion_en_carpeta: bool = True
    especialidad: Optional[str] = None
    magistrado: Optional[str] = None
    detalle: Optional[str] = None
    save_path: Optional[str] = None
    convert_to: Optional[str] = None
    # True when the scraper couldn't identify a clean title from metadata
    # alone (e.g. CSJ's "doc", "(3)") — the worker will ask the scraper to
    # try recovering it from the downloaded file's own content instead.
    title_unverified: bool = False

    def __getitem__(self, key):
        return getattr(self, key)
