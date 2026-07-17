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

    def scrap(self, fini, ffin, q="", limit=100, stop_event=None, on_progress=None):
        raise NotImplementedError("Subclasses must implement this method.")
