import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { GitMerge } from "lucide-react";
import { fetchCaseLinks } from "../api/caseLinks";
import { EmptyState } from "../components/EmptyState";
import { ErrorBanner } from "../components/ErrorBanner";
import { formatDate, formatRadicado } from "../lib/formatters";

export function ExpedientesPage() {
  const expedientesQuery = useQuery({
    queryKey: ["case-links"],
    queryFn: fetchCaseLinks,
  });

  return (
    <div className="space-y-6">
      <div>
        <p className="flex items-center gap-1.5 text-xs font-medium tracking-[0.18em] text-muted-foreground uppercase">
          <GitMerge className="size-3.5" aria-hidden="true" />
          Expedientes
        </p>
        <h1 className="font-display text-3xl font-semibold tracking-tight text-foreground">
          Procesos que cruzan tribunales
        </h1>
      </div>

      {expedientesQuery.isError && (
        <ErrorBanner message="No se pudieron cargar los expedientes." onRetry={() => expedientesQuery.refetch()} />
      )}

      {!expedientesQuery.isLoading && (expedientesQuery.data?.length ?? 0) === 0 && !expedientesQuery.isError && (
        <EmptyState message="No hay expedientes todavía." />
      )}

      <div className="space-y-3">
        {expedientesQuery.data?.map((expediente) => (
          <div key={expediente.id} className="flex items-center justify-between gap-4 rounded-lg border border-border bg-card p-4">
            <div>
              <p className="font-medium text-foreground">
                {expediente.radicados[0] ? formatRadicado(expediente.radicados[0]) : "Sin radicado"}
              </p>
              <p className="text-xs text-muted-foreground">{expediente.source_names.join(" · ")}</p>
              <p className="text-xs text-muted-foreground">
                {expediente.stage_count} instancia{expediente.stage_count === 1 ? "" : "s"} ·{" "}
                {expediente.document_count} documento{expediente.document_count === 1 ? "" : "s"}
                {expediente.f_public_min &&
                  ` · ${formatDate(expediente.f_public_min)} – ${formatDate(expediente.f_public_max ?? expediente.f_public_min)}`}
              </p>
            </div>
            <Link
              to={`/expedientes/${expediente.id}`}
              className="shrink-0 text-sm font-medium text-primary underline-offset-2 hover:underline"
            >
              Ver expediente
            </Link>
          </div>
        ))}
      </div>
    </div>
  );
}
