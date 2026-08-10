import { useEffect, useRef, useState } from "react";
import { Document, Page, pdfjs } from "react-pdf";
import "react-pdf/dist/Page/TextLayer.css";

import { pickCurrentPage } from "../lib/pdfPage";

// Point pdf.js at its worker as a Vite asset URL (bundled, no CDN — the app's
// CSP wouldn't allow a remote worker anyway).
pdfjs.GlobalWorkerOptions.workerSrc = new URL(
  "pdfjs-dist/build/pdf.worker.min.mjs",
  import.meta.url
).toString();

// Only render page canvases within this many pages of the one in view, so a
// long document (a 100-page sentencia) never mounts 100 canvases at once. Pages
// outside the window keep their reserved height as a blank placeholder.
const RENDER_WINDOW = 3;
// height/width of a US Letter page — the reserved height for not-yet-rendered
// pages until the first real page reports its true aspect ratio.
const DEFAULT_ASPECT = 11 / 8.5;

// A scrollable pdf.js viewer that replaces the browser's native (opaque) PDF
// iframe so we can show a live "Página X de N" indicator — the native viewer
// gives no way to read the current page. Falls back to the native iframe if
// pdf.js can't open a particular file, so we never end up with nothing.
export function PdfViewer({ url, title }: { url: string; title: string }) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const pageEls = useRef<Map<number, HTMLElement>>(new Map());
  const ratios = useRef<Map<number, number>>(new Map());

  const [numPages, setNumPages] = useState(0);
  const [currentPage, setCurrentPage] = useState(1);
  const [pageWidth, setPageWidth] = useState(0);
  const [aspect, setAspect] = useState(DEFAULT_ASPECT);
  const [failed, setFailed] = useState(false);

  // Track the content width (minus the p-4 padding) so pages render fit-to-width
  // and re-fit when the dialog is resized.
  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    const measure = () => setPageWidth(Math.max(0, el.clientWidth - 32));
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(el);
    return () => observer.disconnect();
  }, [failed]);

  // Watch which page dominates the viewport → that's the "current" page.
  useEffect(() => {
    const root = scrollRef.current;
    if (!root || numPages === 0) return;
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          const page = Number((entry.target as HTMLElement).dataset.page);
          ratios.current.set(page, entry.isIntersecting ? entry.intersectionRatio : 0);
        }
        setCurrentPage(pickCurrentPage(ratios.current));
      },
      { root, threshold: [0, 0.25, 0.5, 0.75, 1] }
    );
    for (const el of pageEls.current.values()) observer.observe(el);
    return () => observer.disconnect();
  }, [numPages]);

  if (failed) {
    // Safety net: some malformed PDFs pdf.js can't open still render in the
    // browser's own viewer. #toolbar=0 keeps the native chrome hidden, as before.
    return <iframe title={`Vista previa de ${title}`} src={`${url}#toolbar=0`} className="size-full" />;
  }

  const reservedHeight = pageWidth > 0 ? pageWidth * aspect : 800;

  return (
    <div className="relative h-full">
      <div ref={scrollRef} className="h-full overflow-y-auto bg-secondary p-4">
        <Document
          file={url}
          onLoadSuccess={({ numPages }) => setNumPages(numPages)}
          onLoadError={() => setFailed(true)}
          loading={<div className="flex h-full items-center justify-center text-sm text-muted-foreground">Cargando…</div>}
          error={<div className="flex h-full items-center justify-center text-sm text-muted-foreground">No se pudo abrir el PDF.</div>}
        >
          {Array.from({ length: numPages }, (_, i) => i + 1).map((page) => {
            const inWindow = Math.abs(page - currentPage) <= RENDER_WINDOW;
            return (
              <div
                key={page}
                data-page={page}
                ref={(el) => {
                  if (el) pageEls.current.set(page, el);
                  else pageEls.current.delete(page);
                }}
                className="mx-auto mb-4 w-fit bg-white shadow-sm"
                style={{ minHeight: reservedHeight }}
              >
                {inWindow && pageWidth > 0 && (
                  <Page
                    pageNumber={page}
                    width={pageWidth}
                    renderAnnotationLayer={false}
                    onLoadSuccess={
                      page === 1
                        ? (p) => {
                            const viewport = p.getViewport({ scale: 1 });
                            setAspect(viewport.height / viewport.width);
                          }
                        : undefined
                    }
                    loading=""
                  />
                )}
              </div>
            );
          })}
        </Document>
      </div>

      {numPages > 0 && (
        <div className="pointer-events-none absolute bottom-3 left-1/2 -translate-x-1/2 rounded-full border border-border bg-card/95 px-3 py-1 text-xs font-medium text-foreground shadow-sm backdrop-blur">
          Página <span className="font-mono-num">{currentPage}</span> de <span className="font-mono-num">{numPages}</span>
        </div>
      )}
    </div>
  );
}
