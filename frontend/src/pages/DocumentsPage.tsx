import { useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useLocation, useNavigate } from "react-router-dom";
import { Calendar, Download, Eye, FileStack, Search } from "lucide-react";
import { Button } from "../components/ui/button";
import { DocumentPreviewDialog } from "../components/DocumentPreviewDialog";
import { createBulkDownload } from "../api/bulkDownloads";
import { fetchDocuments, fetchDocumentTipos } from "../api/documents";
import { fetchAllActiveSourcesWithDocuments } from "../api/sources";
import type { DocumentReviewStatus } from "../api/types";
import { EmptyState } from "../components/EmptyState";
import { ErrorBanner } from "../components/ErrorBanner";
import { NativeSelect } from "../components/ui/native-select";
import { TABLE, TABLE_SCROLL, TABLE_SHELL, TBODY_ROW, TD, TD_MONO, TH, THEAD_ROW } from "../lib/tableStyles";
import { formatDate, todayDateString } from "../lib/formatters";

const PAGE_SIZE = 50;

const REVIEW_BADGE_BASE = "inline-block rounded-md border-[1.5px] px-2 py-1 text-xs font-semibold";

function ReviewBadge({ status }: { status: DocumentReviewStatus }) {
  if (status === "useful") {
    return <span className={`${REVIEW_BADGE_BASE} border-verde/50 bg-verde-bg text-verde`}>Útil</span>;
  }
  if (status === "not_useful") {
    return <span className={`${REVIEW_BADGE_BASE} border-rojo/50 bg-rojo-bg text-rojo`}>No útil</span>;
  }
  return <span className={`${REVIEW_BADGE_BASE} border-border bg-card text-muted-foreground`}>Sin revisar</span>;
}

function formatDateFilterLabel(from: string, to: string): string {
  if (!from && !to) return "Fecha de publicación";
  if (from && to) return `${formatDate(from)} – ${formatDate(to)}`;
  if (from) return `Desde ${formatDate(from)}`;
  return `Hasta ${formatDate(to)}`;
}

export function DocumentsPage() {
  const [title, setTitle] = useState("");
  const [tipo, setTipo] = useState("");
  const [sourceId, setSourceId] = useState("");
  const [reviewStatus, setReviewStatus] = useState<DocumentReviewStatus | "">("");
  const [fPublicFrom, setFPublicFrom] = useState("");
  const [fPublicTo, setFPublicTo] = useState("");
  const [dateFilterOpen, setDateFilterOpen] = useState(false);
  const location = useLocation();
  const seedToday = (location.state as { downloadedToday?: boolean } | null)?.downloadedToday === true;
  const [downloadedFrom, setDownloadedFrom] = useState(() => (seedToday ? todayDateString() : ""));
  const [downloadedTo, setDownloadedTo] = useState(() => (seedToday ? todayDateString() : ""));
  const [downloadedFilterOpen, setDownloadedFilterOpen] = useState(false);
  const [page, setPage] = useState(0);
  const [previewIndex, setPreviewIndex] = useState<number | null>(null);

  const dateFilterRef = useRef<HTMLDivElement>(null);
  const downloadedFilterRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!dateFilterOpen && !downloadedFilterOpen) return;
    function handleClickOutside(event: MouseEvent) {
      if (dateFilterOpen && dateFilterRef.current && !dateFilterRef.current.contains(event.target as Node)) {
        setDateFilterOpen(false);
      }
      if (downloadedFilterOpen && downloadedFilterRef.current && !downloadedFilterRef.current.contains(event.target as Node)) {
        setDownloadedFilterOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [dateFilterOpen, downloadedFilterOpen]);

  const sourcesQuery = useQuery({
    queryKey: ["sources", "for-documents-filter"],
    queryFn: fetchAllActiveSourcesWithDocuments,
  });

  const sortedSources = useMemo(
    () => [...(sourcesQuery.data ?? [])].sort((a, b) => a.name.localeCompare(b.name, "es")),
    [sourcesQuery.data]
  );

  // Scoped to the selected source so the Tipo dropdown only ever offers
  // values that actually exist for it (nested/cascading filters).
  const tiposQuery = useQuery({
    queryKey: ["documents", "tipos", sourceId],
    queryFn: () => fetchDocumentTipos(sourceId ? Number(sourceId) : undefined),
  });

  useEffect(() => {
    if (tipo && tiposQuery.data && !tiposQuery.data.includes(tipo)) {
      setTipo("");
    }
  }, [tipo, tiposQuery.data]);

  const sourceNameById = useMemo(
    () => new Map((sourcesQuery.data ?? []).map((source) => [source.id, source.name])),
    [sourcesQuery.data]
  );

  const documentsQuery = useQuery({
    queryKey: ["documents", title, tipo, sourceId, reviewStatus, fPublicFrom, fPublicTo, downloadedFrom, downloadedTo, page],
    queryFn: () =>
      fetchDocuments({
        title: title || undefined,
        tipo: tipo || undefined,
        source_id: sourceId ? Number(sourceId) : undefined,
        review_status: reviewStatus || undefined,
        f_public_from: fPublicFrom || undefined,
        f_public_to: fPublicTo || undefined,
        downloaded_from: downloadedFrom || undefined,
        downloaded_to: downloadedTo || undefined,
        limit: PAGE_SIZE,
        offset: page * PAGE_SIZE,
      }),
  });

  const navigate = useNavigate();
  const bulkDownloadMutation = useMutation({
    mutationFn: createBulkDownload,
    onSuccess: () => navigate("/bulk-downloads"),
  });

  const hasDateFilter = !!fPublicFrom || !!fPublicTo;
  const hasDownloadedFilter = !!downloadedFrom || !!downloadedTo;

  return (
    <div className="flex h-full flex-col gap-6">
      <div>
        <p className="flex items-center gap-1.5 text-xs font-medium tracking-[0.18em] text-muted-foreground uppercase">
          <FileStack className="size-3.5" aria-hidden="true" />
          Archivo de expedientes
        </p>
        <h1 className="font-display text-3xl font-semibold tracking-tight text-foreground">Documentos</h1>
      </div>

      <div className="flex flex-wrap items-center gap-3 rounded-lg border border-border bg-card p-3 shadow-sm">
        <div className="relative">
          <Search className="pointer-events-none absolute top-1/2 left-2.5 size-3.5 -translate-y-1/2 text-muted-foreground" />
          <input
            placeholder="Buscar por título"
            value={title}
            onChange={(event) => {
              setTitle(event.target.value);
              setPage(0);
            }}
            className="h-9 w-56 rounded-md border-[1.5px] border-input bg-background py-1 pr-3 pl-8 text-sm outline-none focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50"
          />
        </div>
        <label className="flex items-center gap-2 text-sm text-muted-foreground">
          Fuente
          <NativeSelect
            value={sourceId}
            onChange={(event) => {
              setSourceId(event.target.value);
              setPage(0);
            }}
            className="w-40"
          >
            <option value="">Todas</option>
            {sortedSources.map((source) => (
              <option key={source.id} value={String(source.id)}>
                {source.name}
              </option>
            ))}
          </NativeSelect>
        </label>
        <label className="flex items-center gap-2 text-sm text-muted-foreground">
          Tipo
          <NativeSelect
            value={tipo}
            onChange={(event) => {
              setTipo(event.target.value);
              setPage(0);
            }}
            className="w-32"
          >
            <option value="">Todos</option>
            {tiposQuery.data?.map((tipoOption) => (
              <option key={tipoOption} value={tipoOption}>
                {tipoOption}
              </option>
            ))}
          </NativeSelect>
        </label>
        <label className="flex items-center gap-2 text-sm text-muted-foreground">
          Revisión
          <NativeSelect
            value={reviewStatus}
            onChange={(event) => {
              setReviewStatus(event.target.value as DocumentReviewStatus | "");
              setPage(0);
            }}
            className="w-32"
          >
            <option value="">Todos</option>
            <option value="pending">Sin revisar</option>
            <option value="useful">Útil</option>
            <option value="not_useful">No útil</option>
          </NativeSelect>
        </label>

        <div className="relative" ref={dateFilterRef}>
          <button
            onClick={() => setDateFilterOpen((open) => !open)}
            className={`flex h-9 items-center gap-1.5 rounded-md border-[1.5px] px-3 text-sm font-medium transition-colors ${
              hasDateFilter
                ? "border-sello/50 bg-sello/10 text-sello-ink"
                : "border-input bg-background text-muted-foreground hover:text-foreground"
            }`}
          >
            <Calendar className="size-3.5" aria-hidden="true" />
            {formatDateFilterLabel(fPublicFrom, fPublicTo)}
          </button>
          {dateFilterOpen && (
            <div className="absolute top-full left-0 z-20 mt-2 flex w-64 flex-col gap-3 rounded-lg border border-border bg-card p-3 shadow-md">
              <label className="flex flex-col gap-1 text-xs font-medium text-muted-foreground">
                Desde
                <input
                  type="date"
                  value={fPublicFrom}
                  onChange={(event) => {
                    setFPublicFrom(event.target.value);
                    setPage(0);
                  }}
                  className="h-8 rounded-md border-[1.5px] border-input bg-background px-2 text-sm outline-none focus-visible:border-ring"
                />
              </label>
              <label className="flex flex-col gap-1 text-xs font-medium text-muted-foreground">
                Hasta
                <input
                  type="date"
                  value={fPublicTo}
                  onChange={(event) => {
                    setFPublicTo(event.target.value);
                    setPage(0);
                  }}
                  className="h-8 rounded-md border-[1.5px] border-input bg-background px-2 text-sm outline-none focus-visible:border-ring"
                />
              </label>
              {hasDateFilter && (
                <button
                  onClick={() => {
                    setFPublicFrom("");
                    setFPublicTo("");
                    setPage(0);
                  }}
                  className="text-left text-xs font-semibold text-muted-foreground underline underline-offset-2 hover:text-foreground"
                >
                  Limpiar
                </button>
              )}
            </div>
          )}
        </div>

        <div className="relative" ref={downloadedFilterRef}>
          <button
            onClick={() => setDownloadedFilterOpen((open) => !open)}
            className={`flex h-9 items-center gap-1.5 rounded-md border-[1.5px] px-3 text-sm font-medium transition-colors ${
              hasDownloadedFilter
                ? "border-sello/50 bg-sello/10 text-sello-ink"
                : "border-input bg-background text-muted-foreground hover:text-foreground"
            }`}
          >
            <Calendar className="size-3.5" aria-hidden="true" />
            {formatDateFilterLabel(downloadedFrom, downloadedTo) === "Fecha de publicación"
              ? "Agregado"
              : `Agregado: ${formatDateFilterLabel(downloadedFrom, downloadedTo)}`}
          </button>
          {downloadedFilterOpen && (
            <div className="absolute top-full left-0 z-20 mt-2 flex w-64 flex-col gap-3 rounded-lg border border-border bg-card p-3 shadow-md">
              <label className="flex flex-col gap-1 text-xs font-medium text-muted-foreground">
                Desde
                <input
                  type="date"
                  value={downloadedFrom}
                  onChange={(event) => {
                    setDownloadedFrom(event.target.value);
                    setPage(0);
                  }}
                  className="h-8 rounded-md border-[1.5px] border-input bg-background px-2 text-sm outline-none focus-visible:border-ring"
                />
              </label>
              <label className="flex flex-col gap-1 text-xs font-medium text-muted-foreground">
                Hasta
                <input
                  type="date"
                  value={downloadedTo}
                  onChange={(event) => {
                    setDownloadedTo(event.target.value);
                    setPage(0);
                  }}
                  className="h-8 rounded-md border-[1.5px] border-input bg-background px-2 text-sm outline-none focus-visible:border-ring"
                />
              </label>
              {hasDownloadedFilter && (
                <button
                  onClick={() => {
                    setDownloadedFrom("");
                    setDownloadedTo("");
                    setPage(0);
                  }}
                  className="text-left text-xs font-semibold text-muted-foreground underline underline-offset-2 hover:text-foreground"
                >
                  Limpiar
                </button>
              )}
            </div>
          )}
        </div>

        <Button
          variant="outline"
          onClick={() => bulkDownloadMutation.mutate()}
          disabled={bulkDownloadMutation.isPending}
        >
          <Download className="size-3.5" aria-hidden="true" />
          {bulkDownloadMutation.isPending ? "Generando…" : "Descarga masiva"}
        </Button>
      </div>

      {documentsQuery.isError && (
        <ErrorBanner message="No se pudieron cargar los documentos." onRetry={() => documentsQuery.refetch()} />
      )}

      <div className={`${TABLE_SHELL} flex min-h-0 flex-1 flex-col`}>
        <div className={`${TABLE_SCROLL} flex-1 overflow-y-auto`}>
          <table className={`${TABLE} h-full min-w-[1200px]`}>
          <thead className="sticky top-0 z-10">
            <tr className={THEAD_ROW}>
              <th className={`${TH} min-w-[260px]`}>Título</th>
              <th className={TH}>Fuente</th>
              <th className={TH}>Tipo</th>
              <th className={TH}>Sección</th>
              <th className={TH}>Especialidad</th>
              <th className={TH}>Magistrado</th>
              <th className={`${TH} whitespace-nowrap`}>Fecha de publicación</th>
              <th className={`${TH} whitespace-nowrap`}>Fecha providencia</th>
              <th className={`${TH} whitespace-nowrap`}>Revisión</th>
              <th className={TH}>Acciones</th>
            </tr>
          </thead>
          <tbody>
            {(documentsQuery.data?.items.length ?? 0) === 0 && (
              <tr>
                <td colSpan={10} className="h-full p-0">
                  <div className="flex h-full items-center justify-center">
                    <EmptyState message="No hay documentos que coincidan con estos filtros." />
                  </div>
                </td>
              </tr>
            )}
            {documentsQuery.data?.items.map((document, index) => (
              <tr key={document.id} className={TBODY_ROW}>
                <td className={`${TD} font-medium whitespace-nowrap text-foreground`} title={document.detalle ?? undefined}>
                  <button
                    type="button"
                    onClick={() => {
                      setTitle(document.title);
                      setPage(0);
                    }}
                    className="underline-offset-2 hover:underline"
                  >
                    {document.title}
                  </button>
                </td>
                <td className={`${TD} whitespace-nowrap`}>{sourceNameById.get(document.source_id) ?? "—"}</td>
                <td className={`${TD} whitespace-nowrap`}>{document.tipo ?? "—"}</td>
                <td className={`${TD} whitespace-nowrap`}>{document.seccion ?? "—"}</td>
                <td className={`${TD} whitespace-nowrap`}>{document.especialidad ?? "—"}</td>
                <td className={`${TD} whitespace-nowrap`}>{document.magistrado ?? "—"}</td>
                <td className={`${TD_MONO} whitespace-nowrap`}>{formatDate(document.f_public)}</td>
                <td className={`${TD_MONO} whitespace-nowrap`}>{formatDate(document.f_providencia)}</td>
                <td className={TD}>
                  <ReviewBadge status={document.review_status} />
                </td>
                <td className={TD}>
                  <Button variant="outline" size="sm" onClick={() => setPreviewIndex(index)}>
                    <Eye className="size-3.5" aria-hidden="true" />
                    Previsualizar
                  </Button>
                </td>
              </tr>
            ))}
          </tbody>
          </table>
        </div>
      </div>

      <div className="flex items-center justify-between">
        <p className="text-sm text-muted-foreground">
          Total: <span className="font-mono-num font-semibold text-foreground">{documentsQuery.data?.total ?? 0}</span>
        </p>
        <div className="flex gap-2">
          <button
            disabled={page === 0}
            onClick={() => setPage((current) => current - 1)}
            className="rounded-md border-[1.5px] border-input bg-card px-3 py-1 text-sm font-medium shadow-xs disabled:opacity-50"
          >
            Anterior
          </button>
          <button
            disabled={(documentsQuery.data?.items.length ?? 0) < PAGE_SIZE}
            onClick={() => setPage((current) => current + 1)}
            className="rounded-md border-[1.5px] border-input bg-card px-3 py-1 text-sm font-medium shadow-xs disabled:opacity-50"
          >
            Siguiente
          </button>
        </div>
      </div>

      {previewIndex !== null && documentsQuery.data && (
        <DocumentPreviewDialog
          documents={documentsQuery.data.items}
          initialIndex={previewIndex}
          open={previewIndex !== null}
          onOpenChange={(nextOpen) => {
            if (!nextOpen) setPreviewIndex(null);
          }}
        />
      )}
    </div>
  );
}
