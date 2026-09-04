import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Download } from "lucide-react";
import { buildDownloadFilename, downloadDocumentFile, fetchDocumentAnexos } from "../api/documents";
import type { Document } from "../api/types";
import { ErrorBanner } from "./ErrorBanner";
import { Button } from "./ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "./ui/dialog";

interface AnexosDialogProps {
  document: Document | null;
  onClose: () => void;
}

export function AnexosDialog({ document, onClose }: AnexosDialogProps) {
  const [downloadError, setDownloadError] = useState<string | null>(null);

  const anexosQuery = useQuery({
    queryKey: ["document-anexos", document?.id],
    queryFn: () => fetchDocumentAnexos(document!.id),
    enabled: document != null,
  });

  useEffect(() => {
    setDownloadError(null);
  }, [document?.id]);

  if (document == null) return null;

  async function handleDownload(anexo: Document) {
    try {
      setDownloadError(null);
      await downloadDocumentFile(anexo.id, buildDownloadFilename(anexo));
    } catch {
      setDownloadError("Error al descargar el anexo");
    }
  }

  return (
    <Dialog
      open
      onOpenChange={(nextOpen) => {
        if (!nextOpen) onClose();
      }}
    >
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Anexos de {document.nombre}</DialogTitle>
        </DialogHeader>

        {downloadError && <ErrorBanner message={downloadError} onRetry={() => setDownloadError(null)} />}

        {anexosQuery.isLoading && <p className="text-sm text-muted-foreground">Cargando…</p>}
        {anexosQuery.isError && (
          <ErrorBanner message="No se pudieron cargar los anexos" onRetry={() => anexosQuery.refetch()} />
        )}

        <ul className="flex flex-col gap-2">
          {anexosQuery.data?.map((anexo) => (
            <li key={anexo.id} className="flex items-center justify-between gap-3">
              <span className="font-mono text-sm">{anexo.nombre}</span>
              <Button variant="outline" size="sm" onClick={() => handleDownload(anexo)}>
                <Download className="size-3.5" aria-hidden="true" />
                Descargar
              </Button>
            </li>
          ))}
        </ul>
      </DialogContent>
    </Dialog>
  );
}
