class BaseScrapper:
    source = None

    # Whether fini/ffin (the run's requested date range) are matched against the
    # document's publication date (f_public) rather than its providencia date
    # (f_providencia). Most sources' own search APIs only support filtering by
    # providencia date, so that's the default; a family overrides this only when
    # it can genuinely filter (or, like JEP, precisely re-filter client-side)
    # by publication date instead.
    filters_by_publication_date = False

    # Whether a document that already exists (same doc_id) should still be
    # re-checked for a republication (the source replaced the same file at the
    # same URL with a bigger/different one) via a cheap HEAD request. True by
    # default since most families expose a direct GET file URL; a family opts
    # out when its download mechanism has no cheap direct URL to check (e.g. a
    # shared POST endpoint, or an indirect JWT hop).
    checks_for_republication = True

    # Whether doc_id (the DB identity used to look up "does this document
    # already exist") should fold in f_public. True by default, since for
    # most families f_public is a fixed, intrinsic attribute of the document
    # (e.g. a court decision's own publication date) that never changes for
    # the same underlying file. A family opts out when f_public instead
    # reflects a listing occurrence that the source can repeat for the same
    # file under a new date (e.g. Rama Judicial re-listing an unclaimed
    # "estado" the next business day) — folding a churning date into doc_id
    # would make the same file produce a different identity every time it's
    # re-listed, permanently hiding it from the republication check above.
    doc_id_uses_publication_date = True

    # For the DAILY SCHEDULED run only (not a manual run's explicit range):
    # the minimum number of days back "today" that fini must cover, even if
    # the configured lookback window is shorter. None (the default) leaves
    # the scheduled run's own window untouched. A family sets this when its
    # own site publishes/indexes documents with a lag longer than the normal
    # lookback — otherwise a short, steadily-advancing window would slide
    # past a document before the source ever surfaces it, permanently
    # hiding it rather than just delaying it by a day or two.
    scheduled_min_lookback_days: int | None = None

    # Para familias cuyo sitio, al republicar un documento, lo vuelve a listar
    # con fecha NUEVA (SAMAI): un documento ya guardado que reaparece con la
    # MISMA fecha es solo el mismo listado visto otra vez (la ventana diaria se
    # superpone) y no se revisa como posible republicación. Importa cuando
    # revisar cuesta una descarga completa y la ventana diaria es larga.
    republication_only_on_new_listing_date: bool = False

    # Días que el aviso "fuentes que pueden estar fallando" (core/salud_fuentes.py)
    # debe tolerar sin documentos nuevos antes de avisar, para una fuente cuyo
    # sitio publica con retraso conocido pero cuya corrida diaria se dejó corta
    # a propósito (si la corrida ya mira más atrás, scheduled_min_lookback_days
    # cumple el mismo papel). None = sin margen propio.
    alerta_margen_dias: int | None = None

    # Whether worker/tasks.py rebuilds the storage key right away when
    # resolve_unverified_document corrects the title (SAMAI/CSJ). A family
    # whose corrected titles group several actuaciones of the same case
    # (rama_judicial) sets False: the file keeps its descriptive key and
    # core/storage_sync.py renames it, since only that detects two
    # actuaciones landing on the same key.
    rekey_storage_on_title_fix: bool = True

    def scrap(self, fini, ffin, q="", limit=100, stop_event=None, on_progress=None):
        raise NotImplementedError("Subclasses must implement this method.")

    def resolve_unverified_document(self, doc, local_path, content_type) -> None:
        """Called by the worker right after downloading a document whose
        `title_unverified` flag is True, with the freshly downloaded file
        still on disk — a chance to recover a proper title (and anything else
        derived from it, like tipo) from the file's own content instead of
        the unreliable metadata that produced the placeholder. Mutates `doc`
        in place; does nothing by default. `local_path` is a `pathlib.Path`."""
        return
