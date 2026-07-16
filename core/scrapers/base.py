class BaseScrapper:
    source = None

    # Whether fini/ffin (the run's requested date range) are matched against the
    # document's publication date (f_public) rather than its providencia date
    # (f_providencia). Most sources' own search APIs only support filtering by
    # providencia date, so that's the default; a family overrides this only when
    # it can genuinely filter (or, like JEP, precisely re-filter client-side)
    # by publication date instead.
    filters_by_publication_date = False

    def scrap(self, fini, ffin, q="", limit=100, stop_event=None, on_progress=None):
        raise NotImplementedError("Subclasses must implement this method.")
