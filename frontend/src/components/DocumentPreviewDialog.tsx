import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Download } from "lucide-react";
import { buildDownloadFilename, downloadDocumentFile, fetchDocumentBlob, updateDocumentReviewStatus } from "../api/documents";
import type { Document, DocumentReviewStatus } from "../api/types";
import { formatDate } from "../lib/formatters";
import { ErrorBanner } from "./ErrorBanner";
import { Button } from "./ui/button";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "./ui/dialog";

interface DocumentPreviewDialogProps {
  documents: Document[];
  initialIndex: number;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function DocumentPreviewDialog({ documents, initialIndex, open, onOpenChange }: DocumentPreviewDialogProps) {
  const [currentIndex, setCurrentIndex] = useState(initialIndex);
  const [objectUrl, setObjectUrl] = useState<string | null>(null);
  const [markError, setMarkError] = useState<string | null>(null);
  const [lastMarkAttempt, setLastMarkAttempt] = useState<DocumentReviewStatus | null>(null);
  const queryClient = useQueryClient();

  useEffect(() => {
    if (open) setCurrentIndex(initialIndex);
  }, [open, initialIndex]);

  useEffect(() => {
    setMarkError(null);
  }, [currentIndex]);

  const currentDocument = documents[currentIndex];
  const isPdf = currentDocument?.content_type === "application/pdf";
  const isFirst = currentIndex === 0;
  const isLast = currentIndex === documents.length - 1;

  const blobQuery = useQuery({
    queryKey: ["document-blob", currentDocument?.id],
    queryFn: () => fetchDocumentBlob(currentDocument!.id),
    enabled: open && !!currentDocument && isPdf,
  });

  useEffect(() => {
    if (!blobQuery.data) {
      setObjectUrl(null);
      return;
    }
    const url = URL.createObjectURL(blobQuery.data);
    setObjectUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [blobQuery.data]);

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

  if (!currentDocument) return null;

  const busy = markMutation.isPending;

  function handleMark(status: DocumentReviewStatus) {
    setLastMarkAttempt(status);
    markMutation.mutate({ id: currentDocument.id, status });
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="flex h-[85vh] flex-col sm:max-w-4xl">
        <DialogHeader>
          <DialogTitle className="font-display">{currentDocument.title}</DialogTitle>
          <p className="text-sm text-muted-foreground">
            {currentDocument.tipo ?? "—"} · {formatDate(currentDocument.f_public)}
          </p>
        </DialogHeader>

        <div className="flex-1 overflow-hidden rounded-md border border-border bg-secondary">
          {isPdf ? (
            blobQuery.isError ? (
              <div className="flex h-full items-center justify-center p-6">
                <ErrorBanner message="No se pudo cargar la vista previa" onRetry={() => blobQuery.refetch()} />
              </div>
            ) : objectUrl ? (
              <iframe title={`Vista previa de ${currentDocument.title}`} src={objectUrl} className="size-full" />
            ) : (
              <div className="flex h-full items-center justify-center text-sm text-muted-foreground">Cargando…</div>
            )
          ) : (
            <div className="flex h-full flex-col items-center justify-center gap-3 p-6 text-center">
              <p className="text-sm text-muted-foreground">Vista previa no disponible para este tipo de archivo.</p>
              <Button
                variant="outline"
                onClick={() => downloadDocumentFile(currentDocument.id, buildDownloadFilename(currentDocument))}
              >
                <Download className="size-3.5" aria-hidden="true" />
                Descargar
              </Button>
            </div>
          )}
        </div>

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
