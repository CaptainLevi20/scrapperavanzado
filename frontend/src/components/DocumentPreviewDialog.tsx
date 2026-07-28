import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Download, Eye, Pencil, X } from "lucide-react";
import {
  buildDownloadFilename,
  buildPreviewDownloadFilename,
  buildVersionDownloadFilename,
  downloadDocumentFile,
  downloadFromUrl,
  fetchDocumentPreviewUrl,
  fetchDocumentVersionUrl,
  fetchDocumentVersions,
  updateDocumentReviewStatus,
  updateDocumentTitle,
} from "../api/documents";
import type { Document, DocumentReviewStatus, DocumentVersion } from "../api/types";
import { formatBytes, formatDate, formatDateTime } from "../lib/formatters";
import { ErrorBanner } from "./ErrorBanner";
import { Button } from "./ui/button";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "./ui/dialog";

interface DocumentPreviewDialogProps {
  documents: Document[];
  initialIndex: number;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  // Shows a list of the case's other actuaciones (title/detalle/date + their own
  // Previsualizar/Útil/No útil/Descargar actions) below the main preview — opt-in
  // so the general single-document-at-a-time preview flow (browsing the Documents
  // table) is entirely unaffected.
  showCaseActuaciones?: boolean;
}

const PREVIEWABLE_CONTENT_TYPES = new Set([
  "application/pdf",
  "application/rtf",
  "application/msword",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
]);

export function DocumentPreviewDialog({
  documents,
  initialIndex,
  open,
  onOpenChange,
  showCaseActuaciones = false,
}: DocumentPreviewDialogProps) {
  const [currentIndex, setCurrentIndex] = useState(initialIndex);
  const [markError, setMarkError] = useState<string | null>(null);
  const [lastMarkAttempt, setLastMarkAttempt] = useState<DocumentReviewStatus | null>(null);
  const [markOtherError, setMarkOtherError] = useState<string | null>(null);
  const [lastMarkOtherAttempt, setLastMarkOtherAttempt] = useState<{ id: number; status: DocumentReviewStatus } | null>(
    null
  );
  const [documentsSnapshot, setDocumentsSnapshot] = useState(documents);
  const [downloadError, setDownloadError] = useState<string | null>(null);
  const [isEditingTitle, setIsEditingTitle] = useState(false);
  const [titleDraft, setTitleDraft] = useState("");
  const [renameError, setRenameError] = useState<string | null>(null);
  const queryClient = useQueryClient();

  useEffect(() => {
    if (open) {
      setCurrentIndex(initialIndex);
      setDocumentsSnapshot(documents);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, initialIndex]);

  useEffect(() => {
    setMarkError(null);
    setDownloadError(null);
    setIsEditingTitle(false);
    setRenameError(null);
    setMarkOtherError(null);
    setLastMarkOtherAttempt(null);
  }, [currentIndex]);

  const currentDocument = documentsSnapshot[currentIndex];
  const isPreviewable = !!currentDocument && PREVIEWABLE_CONTENT_TYPES.has(currentDocument.content_type ?? "");
  const hasNativeRtf = currentDocument?.content_type === "application/rtf";
  const isFirst = currentIndex === 0;
  const isLast = currentIndex === documentsSnapshot.length - 1;

  const previewUrlQuery = useQuery({
    queryKey: ["document-preview-url", currentDocument?.id],
    queryFn: () => fetchDocumentPreviewUrl(currentDocument!.id),
    enabled: open && !!currentDocument && isPreviewable,
  });

  const versionsQuery = useQuery({
    queryKey: ["document-versions", currentDocument?.id],
    queryFn: () => fetchDocumentVersions(currentDocument!.id),
    enabled: open && !!currentDocument,
  });

  const markMutation = useMutation({
    mutationFn: ({ id, status }: { id: number; status: DocumentReviewStatus }) => updateDocumentReviewStatus(id, status),
    onSuccess: () => {
      setMarkError(null);
      queryClient.invalidateQueries({ queryKey: ["documents"] });
      if (isLast) {
        onOpenChange(false);
      } else {
        setCurrentIndex((index) => index + 1);
      }
    },
    onError: () => setMarkError("Error al marcar el documento"),
  });

  // Marking a SIBLING actuación from the list (not the currently-displayed
  // document) must only update that row in place — unlike the footer's
  // markMutation, it never advances currentIndex or closes the dialog, since
  // the user is still looking at a different document.
  const markOtherMutation = useMutation({
    mutationFn: ({ id, status }: { id: number; status: DocumentReviewStatus }) => updateDocumentReviewStatus(id, status),
    onSuccess: (updated) => {
      setMarkOtherError(null);
      queryClient.invalidateQueries({ queryKey: ["documents"] });
      setDocumentsSnapshot((snapshot) =>
        snapshot.map((doc) =>
          doc.id === updated.id ? { ...doc, review_status: updated.review_status, reviewed_at: updated.reviewed_at } : doc
        )
      );
    },
    onError: () => setMarkOtherError("Error al marcar la actuación"),
  });

  function handleMarkOther(id: number, status: DocumentReviewStatus) {
    setLastMarkOtherAttempt({ id, status });
    markOtherMutation.mutate({ id, status });
  }

  const renameMutation = useMutation({
    mutationFn: ({ id, title }: { id: number; title: string }) => updateDocumentTitle(id, title),
    onSuccess: (updated) => {
      setRenameError(null);
      setIsEditingTitle(false);
      setDocumentsSnapshot((snapshot) =>
        snapshot.map((doc, index) => (index === currentIndex ? { ...doc, title: updated.title } : doc))
      );
      queryClient.invalidateQueries({ queryKey: ["documents"] });
    },
    onError: () => setRenameError("Error al renombrar el documento"),
  });

  if (!currentDocument) return null;

  const busy = markMutation.isPending;

  function handleMark(status: DocumentReviewStatus) {
    setLastMarkAttempt(status);
    markMutation.mutate({ id: currentDocument.id, status });
  }

  function handleStartRename() {
    setRenameError(null);
    setTitleDraft(currentDocument.title);
    setIsEditingTitle(true);
  }

  function handleCancelRename() {
    setRenameError(null);
    setIsEditingTitle(false);
  }

  function handleSaveRename() {
    const trimmed = titleDraft.trim();
    if (!trimmed || trimmed === currentDocument.title) {
      setIsEditingTitle(false);
      return;
    }
    renameMutation.mutate({ id: currentDocument.id, title: trimmed });
  }

  async function handleDownloadRtf() {
    try {
      setDownloadError(null);
      await downloadDocumentFile(currentDocument.id, buildDownloadFilename(currentDocument));
    } catch {
      setDownloadError("Error al descargar el RTF");
    }
  }

  async function handleDownloadPdf() {
    if (!previewUrlQuery.data) return;
    try {
      setDownloadError(null);
      await downloadFromUrl(previewUrlQuery.data, buildPreviewDownloadFilename(currentDocument));
    } catch {
      setDownloadError("Error al descargar el PDF");
    }
  }

  async function handleDownloadOther(doc: Document) {
    try {
      setDownloadError(null);
      await downloadDocumentFile(doc.id, buildDownloadFilename(doc));
    } catch {
      setDownloadError("Error al descargar el documento");
    }
  }

  async function handleDownloadVersion(version: DocumentVersion) {
    try {
      setDownloadError(null);
      const url = await fetchDocumentVersionUrl(currentDocument.id, version.id);
      await downloadFromUrl(url, buildVersionDownloadFilename(currentDocument.title, version));
    } catch {
      setDownloadError("Error al descargar la versión anterior");
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="flex h-[85vh] flex-col sm:max-w-4xl">
        <DialogHeader>
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0 flex-1">
              {isEditingTitle ? (
                <>
                  <DialogTitle className="sr-only">{currentDocument.title}</DialogTitle>
                  <div className="flex items-center gap-2">
                    <input
                      value={titleDraft}
                      onChange={(event) => setTitleDraft(event.target.value)}
                      onKeyDown={(event) => {
                        if (event.key === "Enter") handleSaveRename();
                        if (event.key === "Escape") handleCancelRename();
                      }}
                      autoFocus
                      aria-label="Nuevo título del documento"
                      className="h-9 min-w-0 flex-1 rounded-md border-[1.5px] border-input bg-background px-2 font-display text-lg font-semibold outline-none focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50"
                    />
                    <Button
                      size="icon-sm"
                      variant="outline"
                      disabled={renameMutation.isPending}
                      onClick={handleSaveRename}
                      aria-label="Guardar título"
                    >
                      <Check className="size-3.5" aria-hidden="true" />
                    </Button>
                    <Button
                      size="icon-sm"
                      variant="ghost"
                      disabled={renameMutation.isPending}
                      onClick={handleCancelRename}
                      aria-label="Cancelar edición del título"
                    >
                      <X className="size-3.5" aria-hidden="true" />
                    </Button>
                  </div>
                </>
              ) : (
                <div className="flex items-center gap-1.5">
                  <DialogTitle className="font-display truncate">{currentDocument.title}</DialogTitle>
                  <Button
                    size="icon-xs"
                    variant="ghost"
                    onClick={handleStartRename}
                    aria-label="Renombrar título"
                    className="text-muted-foreground hover:text-foreground"
                  >
                    <Pencil aria-hidden="true" />
                  </Button>
                </div>
              )}
              <p className="text-sm text-muted-foreground">
                {currentDocument.tipo ?? "—"} · {formatDate(currentDocument.f_public)}
              </p>
            </div>
            {isPreviewable && (
              <div className="flex shrink-0 gap-2">
                {hasNativeRtf && (
                  <Button variant="outline" size="sm" onClick={handleDownloadRtf}>
                    <Download className="size-3.5" aria-hidden="true" />
                    Descargar RTF
                  </Button>
                )}
                <Button variant="outline" size="sm" disabled={!previewUrlQuery.data} onClick={handleDownloadPdf}>
                  <Download className="size-3.5" aria-hidden="true" />
                  Descargar PDF
                </Button>
              </div>
            )}
          </div>
        </DialogHeader>

        {downloadError && <ErrorBanner message={downloadError} onRetry={() => setDownloadError(null)} />}

        <div className="flex-1 overflow-hidden rounded-md border border-border bg-secondary">
          {isPreviewable ? (
            previewUrlQuery.isError ? (
              <div className="flex h-full items-center justify-center p-6">
                <ErrorBanner message="No se pudo cargar la vista previa" onRetry={() => previewUrlQuery.refetch()} />
              </div>
            ) : previewUrlQuery.data ? (
              // #toolbar=0 suppresses the browser's own built-in pdf viewer chrome
              // (Chrome/Firefox both honor it) — we offer download via our own
              // explicit buttons above instead, matching the RTF/PDF choice a
              // native download button couldn't express.
              <iframe
                title={`Vista previa de ${currentDocument.title}`}
                src={`${previewUrlQuery.data}#toolbar=0`}
                className="size-full"
              />
            ) : (
              <div className="flex h-full items-center justify-center text-sm text-muted-foreground">Cargando…</div>
            )
          ) : (
            <div className="flex h-full flex-col items-center justify-center gap-3 p-6 text-center">
              <p className="text-sm text-muted-foreground">Vista previa no disponible para este tipo de archivo.</p>
              <Button variant="outline" onClick={() => handleDownloadOther(currentDocument)}>
                <Download className="size-3.5" aria-hidden="true" />
                Descargar
              </Button>
            </div>
          )}
        </div>

        {showCaseActuaciones && documentsSnapshot.length > 1 && (
          <div className="rounded-md border border-border bg-secondary/40 p-3">
            <p className="text-xs font-semibold text-muted-foreground uppercase">Otras actuaciones de este caso</p>
            <ul className="mt-2 space-y-1.5">
              {documentsSnapshot.map((doc, index) =>
                index === currentIndex ? null : (
                  <li key={doc.id} className="flex items-center justify-between gap-3 text-sm">
                    <span className="text-muted-foreground">
                      {doc.detalle ?? "—"} · {formatDate(doc.f_public)}
                    </span>
                    <div className="flex shrink-0 gap-2">
                      <Button
                        variant="outline"
                        size="sm"
                        disabled={markOtherMutation.isPending}
                        onClick={() => setCurrentIndex(index)}
                      >
                        <Eye className="size-3.5" aria-hidden="true" />
                        Previsualizar
                      </Button>
                      <Button
                        variant="outline"
                        size="sm"
                        disabled={markOtherMutation.isPending}
                        onClick={() => handleMarkOther(doc.id, "useful")}
                        className="border-verde/50 text-verde hover:bg-verde-bg"
                      >
                        Útil
                      </Button>
                      <Button
                        variant="outline"
                        size="sm"
                        disabled={markOtherMutation.isPending}
                        onClick={() => handleMarkOther(doc.id, "not_useful")}
                        className="border-rojo/50 text-rojo hover:bg-rojo-bg"
                      >
                        No útil
                      </Button>
                      <Button variant="outline" size="sm" onClick={() => handleDownloadOther(doc)}>
                        <Download className="size-3.5" aria-hidden="true" />
                        Descargar
                      </Button>
                    </div>
                  </li>
                )
              )}
            </ul>
            {markOtherError && (
              <div className="mt-2">
                <ErrorBanner
                  message={markOtherError}
                  onRetry={() => lastMarkOtherAttempt && handleMarkOther(lastMarkOtherAttempt.id, lastMarkOtherAttempt.status)}
                />
              </div>
            )}
          </div>
        )}

        {(versionsQuery.data?.length ?? 0) > 0 && (
          <div className="rounded-md border border-border bg-secondary/40 p-3">
            <p className="text-xs font-semibold text-muted-foreground uppercase">
              {versionsQuery.data!.length} {versionsQuery.data!.length === 1 ? "versión anterior" : "versiones anteriores"}
            </p>
            <ul className="mt-2 space-y-1.5">
              {versionsQuery.data!.map((version) => (
                <li key={version.id} className="flex items-center justify-between gap-3 text-sm">
                  <span className="text-muted-foreground">
                    Reemplazada el {formatDateTime(version.superseded_at)} · {formatBytes(version.file_size_bytes)}
                  </span>
                  <Button variant="outline" size="sm" onClick={() => handleDownloadVersion(version)}>
                    <Download className="size-3.5" aria-hidden="true" />
                    Descargar
                  </Button>
                </li>
              ))}
            </ul>
          </div>
        )}

        {renameError && <ErrorBanner message={renameError} onRetry={handleSaveRename} />}

        {markError && (
          <ErrorBanner message={markError} onRetry={() => lastMarkAttempt && handleMark(lastMarkAttempt)} />
        )}

        <DialogFooter className="flex-row items-center justify-between sm:justify-between">
          <div className="flex gap-2">
            <Button
              variant="outline"
              size="sm"
              disabled={isFirst || busy}
              onClick={() => setCurrentIndex((index) => index - 1)}
            >
              Anterior
            </Button>
            <Button
              variant="outline"
              size="sm"
              disabled={isLast || busy}
              onClick={() => setCurrentIndex((index) => index + 1)}
            >
              Siguiente
            </Button>
          </div>
          <div className="flex gap-2">
            <Button
              variant="outline"
              size="sm"
              disabled={busy}
              onClick={() => handleMark("useful")}
              className="border-verde/50 text-verde hover:bg-verde-bg"
            >
              Útil
            </Button>
            <Button
              variant="outline"
              size="sm"
              disabled={busy}
              onClick={() => handleMark("not_useful")}
              className="border-rojo/50 text-rojo hover:bg-rojo-bg"
            >
              No útil
            </Button>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
