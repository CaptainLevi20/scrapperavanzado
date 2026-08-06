import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useParams } from "react-router-dom";
import { fetchCaseLink, separateCaseLinkStage } from "../api/caseLinks";
import { downloadBlob, fetchDocumentBlob } from "../api/documents";
import type { CaseLinkStage } from "../api/types";
import { Button } from "../components/ui/button";
import { ErrorBanner } from "../components/ErrorBanner";
import { formatDate } from "../lib/formatters";

function stageSortKey(stage: CaseLinkStage): string {
  // Por fecha de publicación ascendente: la etapa cuya providencia se publicó
  // primero va primero. Es el mismo orden que usa el subtítulo del listado de
  // expedientes (source_names), para que listado y línea de tiempo coincidan.
  return stage.f_public_min ?? "9999-99-99";
}

export function CaseLinkDetailPage() {
  const { caseLinkId } = useParams<{ caseLinkId: string }>();
  const id = Number(caseLinkId);
  const queryClient = useQueryClient();
  const [actionError, setActionError] = useState<string | null>(null);

  const caseLinkQuery = useQuery({
    queryKey: ["case-link", id],
    queryFn: () => fetchCaseLink(id),
    enabled: Number.isFinite(id),
  });

  const removeMutation = useMutation({
    mutationFn: (stageId: number) => separateCaseLinkStage(id, stageId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["case-link", id] });
      queryClient.invalidateQueries({ queryKey: ["case-links"] });
    },
    onError: () => setActionError("No se pudo quitar la etapa. Intenta de nuevo."),
  });

  async function openDocument(documentId: number, title: string) {
    try {
      const blob = await fetchDocumentBlob(documentId);
      downloadBlob(blob, title);
    } catch {
      setActionError("No se pudo abrir el documento.");
    }
  }

  const orderedStages = useMemo(
    () => [...(caseLinkQuery.data?.stages ?? [])].sort((a, b) => stageSortKey(a).localeCompare(stageSortKey(b))),
    [caseLinkQuery.data]
  );

  if (caseLinkQuery.isError) {
    return <ErrorBanner message="No se pudo cargar el expediente." onRetry={() => caseLinkQuery.refetch()} />;
  }

  return (
    <div className="space-y-6">
      <div>
        <p className="text-xs font-medium tracking-[0.18em] text-muted-foreground uppercase">Expediente</p>
        <h1 className="font-display text-3xl font-semibold tracking-tight text-foreground">
          Línea de tiempo del caso
        </h1>
      </div>

      {actionError && <ErrorBanner message={actionError} />}

      <ol className="space-y-4 border-l border-border pl-6">
        {orderedStages.map((stage) => (
          <li key={stage.stage_id} className="relative">
            <span className="absolute -left-[1.65rem] top-1 size-2.5 rounded-full bg-primary" aria-hidden="true" />
            <div className="flex items-start justify-between gap-4">
              <div>
                <h2 className="text-lg font-semibold text-foreground">{stage.source_name}</h2>
                <p className="text-xs text-muted-foreground">
                  {stage.f_public_min && formatDate(stage.f_public_min)}
                  {stage.f_public_max && stage.f_public_max !== stage.f_public_min && ` – ${formatDate(stage.f_public_max)}`}
                </p>
              </div>
              <Button
                variant="outline"
                size="sm"
                onClick={() => {
                  if (window.confirm("Esta instancia dejará de aparecer en el expediente y no se volverá a unir sola. ¿Continuar?")) {
                    removeMutation.mutate(stage.stage_id);
                  }
                }}
                disabled={removeMutation.isPending}
              >
                Quitar del expediente
              </Button>
            </div>
            <ul className="mt-2 space-y-1">
              {stage.documents.map((document) => (
                <li key={document.id} className="flex items-center gap-2 text-sm text-foreground">
                  <span>{document.title}</span>
                  <button
                    type="button"
                    onClick={() => openDocument(document.id, document.title)}
                    className="text-xs text-primary underline-offset-2 hover:underline"
                  >
                    Abrir
                  </button>
                </li>
              ))}
            </ul>
          </li>
        ))}
      </ol>
    </div>
  );
}
