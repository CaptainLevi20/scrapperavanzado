import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Download, Eye, FileStack, Search } from "lucide-react";
import { Button } from "../components/ui/button";
import { DocumentPreviewDialog } from "../components/DocumentPreviewDialog";
import {
  buildDownloadFilename,
  bulkUpdateDocumentReviewStatus,
  downloadDocumentFile,
  fetchDocuments,
  fetchDocumentTipos,
  updateDocumentReviewStatus,
} from "../api/documents";
import { fetchSourceFamilies } from "../api/sourceFamilies";
import { fetchAllActiveSources } from "../api/sources";
import type { DocumentReviewStatus } from "../api/types";
import { EmptyState } from "../components/EmptyState";
import { ErrorBanner } from "../components/ErrorBanner";
import { NativeSelect } from "../components/ui/native-select";
import { TABLE, TABLE_SCROLL, TABLE_SHELL, TBODY_ROW, TD, TD_MONO, TH, THEAD_ROW } from "../lib/tableStyles";
import { formatBytes, formatDate } from "../lib/formatters";

const PAGE_SIZE = 50;

const REVIEW_BUTTON_BASE = "rounded-md border-[1.5px] px-2 py-1 text-xs font-semibold transition-colors";

export function DocumentsPage() {
  const [title, setTitle] = useState("");
  const [tipo, setTipo] = useState("");
  const [sourceId, setSourceId] = useState("");
  const [familyKey, setFamilyKey] = useState("");
  const [reviewStatus, setReviewStatus] = useState<DocumentReviewStatus | "">("");
  const [page, setPage] = useState(0);
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
  const [previewIndex, setPreviewIndex] = useState<number | null>(null);

  const queryClient = useQueryClient();

  const sourcesQuery = useQuery({
    queryKey: ["sources", "for-documents-filter"],
    queryFn: fetchAllActiveSources,
  });

  const familiesQuery = useQuery({ queryKey: ["source-families"], queryFn: fetchSourceFamilies });

  const tiposQuery = useQuery({ queryKey: ["documents", "tipos"], queryFn: fetchDocumentTipos });

  const sourceNameById = useMemo(
    () => new Map((sourcesQuery.data ?? []).map((source) => [source.id, source.name])),
    [sourcesQuery.data]
  );

  const documentsQuery = useQuery({
    queryKey: ["documents", title, tipo, sourceId, familyKey, reviewStatus, page],
    queryFn: () =>
      fetchDocuments({
        title: title || undefined,
        tipo: tipo || undefined,
        source_id: sourceId ? Number(sourceId) : undefined,
        family_key: familyKey || undefined,
        review_status: reviewStatus || undefined,
        limit: PAGE_SIZE,
        offset: page * PAGE_SIZE,
      }),
  });

  const [downloadError, setDownloadError] = useState<string | null>(null);
  const downloadMutation = useMutation({
    mutationFn: ({ id, filename }: { id: number; filename: string }) => downloadDocumentFile(id, filename),
    onError: () => setDownloadError("Error al descargar el documento"),
  });

  const [reviewError, setReviewError] = useState<string | null>(null);
  const reviewMutation = useMutation({
    mutationFn: ({ id, status }: { id: number; status: DocumentReviewStatus }) => updateDocumentReviewStatus(id, status),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["documents"] }),
    onError: () => setReviewError("Error al marcar el documento"),
  });

  const [bulkError, setBulkError] = useState<string | null>(null);
  const bulkReviewMutation = useMutation({
    mutationFn: ({ ids, status }: { ids: number[]; status: DocumentReviewStatus }) =>
      bulkUpdateDocumentReviewStatus(ids, status),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["documents"] });
      setSelectedIds(new Set());
    },
    onError: () => setBulkError("Error al marcar los documentos seleccionados"),
  });

  function toggleSelected(id: number) {
    setSelectedIds((current) => {
      const next = new Set(current);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  }

  const visibleIds = documentsQuery.data?.items.map((document) => document.id) ?? [];
  const allVisibleSelected = visibleIds.length > 0 && visibleIds.every((id) => selectedIds.has(id));

  function toggleSelectAll() {
    setSelectedIds((current) => {
      if (allVisibleSelected) {
        const next = new Set(current);
        visibleIds.forEach((id) => next.delete(id));
        return next;
      }
      return new Set([...current, ...visibleIds]);
    });
  }

  return (
    <div className="space-y-6">
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
              setSelectedIds(new Set());
            }}
            className="h-9 w-56 rounded-md border-[1.5px] border-input bg-background py-1 pr-3 pl-8 text-sm outline-none focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50"
          />
        </div>
        <label className="flex items-center gap-2 text-sm text-muted-foreground">
          Tipo
          <NativeSelect
            value={tipo}
            onChange={(event) => {
              setTipo(event.target.value);
              setPage(0);
              setSelectedIds(new Set());
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
          Fuente
          <NativeSelect
            value={sourceId}
            onChange={(event) => {
              setSourceId(event.target.value);
              setPage(0);
              setSelectedIds(new Set());
            }}
            className="w-40"
          >
            <option value="">Todas</option>
            {sourcesQuery.data?.map((source) => (
              <option key={source.id} value={String(source.id)}>
                {source.name}
              </option>
            ))}
          </NativeSelect>
        </label>
        <label className="flex items-center gap-2 text-sm text-muted-foreground">
          Familia
          <NativeSelect
            value={familyKey}
            onChange={(event) => {
              setFamilyKey(event.target.value);
              setPage(0);
              setSelectedIds(new Set());
            }}
            className="w-40"
          >
            <option value="">Todas</option>
            {familiesQuery.data?.map((family) => (
              <option key={family.key} value={family.key}>
                {family.display_name}
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
              setSelectedIds(new Set());
            }}
            className="w-32"
          >
            <option value="">Todos</option>
            <option value="pending">Sin revisar</option>
            <option value="useful">Útil</option>
            <option value="not_useful">No útil</option>
          </NativeSelect>
        </label>
      </div>

      {documentsQuery.isError && (
        <ErrorBanner message="No se pudieron cargar los documentos." onRetry={() => documentsQuery.refetch()} />
      )}
      {downloadError && <ErrorBanner message={downloadError} onRetry={() => setDownloadError(null)} />}
      {reviewError && <ErrorBanner message={reviewError} onRetry={() => setReviewError(null)} />}
      {bulkError && (
        <ErrorBanner
          message={bulkError}
          onRetry={() => {
            setBulkError(null);
            if (bulkReviewMutation.variables) {
              bulkReviewMutation.mutate(bulkReviewMutation.variables);
            }
          }}
        />
      )}

      {selectedIds.size > 0 && (
        <div className="flex items-center gap-3 rounded-lg border-[1.5px] border-sello/40 bg-sello/10 px-4 py-2.5">
          <span className="text-sm font-semibold text-sello-ink">{selectedIds.size} seleccionados</span>
          <button
            disabled={bulkReviewMutation.isPending}
            onClick={() => bulkReviewMutation.mutate({ ids: Array.from(selectedIds), status: "useful" })}
            className={`${REVIEW_BUTTON_BASE} border-verde/50 bg-card text-verde hover:bg-verde-bg disabled:opacity-50`}
          >
            Marcar como útil
          </button>
          <button
            disabled={bulkReviewMutation.isPending}
            onClick={() => bulkReviewMutation.mutate({ ids: Array.from(selectedIds), status: "not_useful" })}
            className={`${REVIEW_BUTTON_BASE} border-rojo/50 bg-card text-rojo hover:bg-rojo-bg disabled:opacity-50`}
          >
            Marcar como no útil
          </button>
        </div>
      )}

      <div className={TABLE_SHELL}>
        <div className={TABLE_SCROLL}>
          <table className={`${TABLE} min-w-[1380px]`}>
          <thead>
            <tr className={THEAD_ROW}>
              <th className={TH}>
                <input
                  type="checkbox"
                  aria-label="Seleccionar todos los documentos visibles"
                  checked={allVisibleSelected}
                  onChange={toggleSelectAll}
                  className="size-4 accent-sello"
                />
              </th>
              <th className={`${TH} min-w-[260px]`}>Título</th>
              <th className={TH}>Fuente</th>
              <th className={TH}>Tipo</th>
              <th className={TH}>Sección</th>
              <th className={TH}>Especialidad</th>
              <th className={TH}>Magistrado</th>
              <th className={`${TH} whitespace-nowrap`}>Fecha de publicación</th>
              <th className={`${TH} whitespace-nowrap`}>Fecha providencia</th>
              <th className={TH}>Tamaño</th>
              <th className={`${TH} whitespace-nowrap`}>Revisión</th>
              <th className={TH}>Acciones</th>
            </tr>
          </thead>
          <tbody>
            {documentsQuery.data?.items.map((document, index) => (
              <tr key={document.id} className={TBODY_ROW}>
                <td className={TD}>
                  <input
                    type="checkbox"
                    aria-label={`Seleccionar "${document.title}"`}
                    checked={selectedIds.has(document.id)}
                    onChange={() => toggleSelected(document.id)}
                    className="size-4 accent-sello"
                  />
                </td>
                <td className={`${TD} font-medium whitespace-nowrap text-foreground`} title={document.detalle ?? undefined}>
                  {document.title}
                </td>
                <td className={`${TD} whitespace-nowrap`}>{sourceNameById.get(document.source_id) ?? "—"}</td>
                <td className={`${TD} whitespace-nowrap`}>{document.tipo ?? "—"}</td>
                <td className={`${TD} whitespace-nowrap`}>{document.seccion ?? "—"}</td>
                <td className={`${TD} whitespace-nowrap`}>{document.especialidad ?? "—"}</td>
                <td className={`${TD} whitespace-nowrap`}>{document.magistrado ?? "—"}</td>
                <td className={`${TD_MONO} whitespace-nowrap`}>{formatDate(document.f_public)}</td>
                <td className={`${TD_MONO} whitespace-nowrap`}>{formatDate(document.f_providencia)}</td>
                <td className={`${TD_MONO} whitespace-nowrap`}>{formatBytes(document.file_size_bytes)}</td>
                <td className={TD}>
                  <div className="flex gap-1">
                    <button
                      onClick={() => reviewMutation.mutate({ id: document.id, status: "useful" })}
                      aria-label={`Marcar "${document.title}" como útil`}
                      aria-pressed={document.review_status === "useful"}
                      className={`${REVIEW_BUTTON_BASE} ${
                        document.review_status === "useful"
                          ? "border-verde bg-verde text-white"
                          : "border-border bg-card text-muted-foreground hover:border-verde/50 hover:text-verde"
                      }`}
                    >
                      Útil
                    </button>
                    <button
                      onClick={() => reviewMutation.mutate({ id: document.id, status: "not_useful" })}
                      aria-label={`Marcar "${document.title}" como no útil`}
                      aria-pressed={document.review_status === "not_useful"}
                      className={`${REVIEW_BUTTON_BASE} ${
                        document.review_status === "not_useful"
                          ? "border-rojo bg-rojo text-white"
                          : "border-border bg-card text-muted-foreground hover:border-rojo/50 hover:text-rojo"
                      }`}
                    >
                      No útil
                    </button>
                  </div>
                </td>
                <td className={TD}>
                  <div className="flex gap-1.5">
                    <Button variant="outline" size="sm" onClick={() => setPreviewIndex(index)}>
                      <Eye className="size-3.5" aria-hidden="true" />
                      Previsualizar
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => downloadMutation.mutate({ id: document.id, filename: buildDownloadFilename(document) })}
                    >
                      <Download className="size-3.5" aria-hidden="true" />
                      Descargar
                    </Button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
          </table>
        </div>
        {(documentsQuery.data?.items.length ?? 0) === 0 && (
          <EmptyState message="No hay documentos que coincidan con estos filtros." />
        )}
      </div>

      <div className="flex items-center justify-between">
        <p className="text-sm text-muted-foreground">
          Total: <span className="font-mono-num font-semibold text-foreground">{documentsQuery.data?.total ?? 0}</span>
        </p>
        <div className="flex gap-2">
          <button
            disabled={page === 0}
            onClick={() => {
              setPage((current) => current - 1);
              setSelectedIds(new Set());
            }}
            className="rounded-md border-[1.5px] border-input bg-card px-3 py-1 text-sm font-medium shadow-xs disabled:opacity-50"
          >
            Anterior
          </button>
          <button
            disabled={(documentsQuery.data?.items.length ?? 0) < PAGE_SIZE}
            onClick={() => {
              setPage((current) => current + 1);
              setSelectedIds(new Set());
            }}
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
