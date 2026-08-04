import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { useParams } from "react-router-dom";
import { fetchCaseLink } from "../api/caseLinks";
import type { CaseLinkStage } from "../api/types";
import { ErrorBanner } from "../components/ErrorBanner";
import { formatDate } from "../lib/formatters";

function stageSortKey(stage: CaseLinkStage): string {
  return stage.f_public_min ?? "9999-99-99";
}

export function CaseLinkDetailPage() {
  const { caseLinkId } = useParams<{ caseLinkId: string }>();
  const id = Number(caseLinkId);

  const caseLinkQuery = useQuery({
    queryKey: ["case-link", id],
    queryFn: () => fetchCaseLink(id),
    enabled: Number.isFinite(id),
  });

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

      <ol className="space-y-4 border-l border-border pl-6">
        {orderedStages.map((stage) => (
          <li key={`${stage.source_id}-${stage.radicado}`} className="relative">
            <span className="absolute -left-[1.65rem] top-1 size-2.5 rounded-full bg-primary" aria-hidden="true" />
            <h2 className="text-lg font-semibold text-foreground">{stage.source_name}</h2>
            <p className="text-xs text-muted-foreground">
              {stage.f_public_min && formatDate(stage.f_public_min)}
              {stage.f_public_max && stage.f_public_max !== stage.f_public_min && ` – ${formatDate(stage.f_public_max)}`}
            </p>
            <ul className="mt-2 space-y-1">
              {stage.documents.map((document) => (
                <li key={document.id} className="text-sm text-foreground">
                  {document.title}
                </li>
              ))}
            </ul>
          </li>
        ))}
      </ol>
    </div>
  );
}
