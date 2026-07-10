class BaseScrapper:
    source = None

    def scrap(self, fini, ffin, q="", limit=100, stop_event=None, on_progress=None):
        raise NotImplementedError("Subclasses must implement this method.")
