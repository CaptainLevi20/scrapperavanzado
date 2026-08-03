import { useState } from "react";
import { useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { cancelRun, fetchRun, fetchRunSources } from "../api/runs";
import { EmptyState } from "../components/EmptyState";
import { ErrorBanner } from "../components/ErrorBanner";
import { StatusBadge } from "../components/StatusBadge";
import { Button } from "../components/ui/button";
import { TABLE, TABLE_SCROLL, TABLE_SHELL, TBODY_ROW, TD, TD_MONO, TH, THEAD_ROW } from "../lib/tableStyles";
import { formatDate, formatDateTime } from "../lib/formatters";
import { isStaleRun, isTerminalRunStatus, shouldPollRun } from "../lib/runStatus";

const POLL_INTERVAL_MS = 4000;

function InfoField({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-xs font-medium tracking-wide text-muted-foreground uppercase">{label}</dt>
      <dd className="font-mono-num text-sm text-foreground">{value}</dd>
    </div>
  );
}

export function RunDetailPage() {
  const { runId } = useParams<{ runId: string }>();
  const id = Number(runId);
  const queryClient = useQueryClient();
  // Set when the user clicks "Reintentar" on a stale run, to resume live
  // tracking for another MAX_POLL_AGE_MS window instead of a single check —
  // see isStaleRun's resumedAtMs param.
  const [resumedAtMs, setResumedAtMs] = useState<number | undefined>(undefined);

  const runQuery = useQuery({
    queryKey: ["run", id],
    queryFn: () => fetchRun(id),
    refetchInterval: (query) => {
      const data = query.state.data;
      return !data || shouldPollRun(data.created_at, data.status, Date.now(), resumedAtMs) ? POLL_INTERVAL_MS : false;
    },
    enabled: !Number.isNaN(id),
  });

  const runIsStale = runQuery.data
    ? isStaleRun(runQuery.data.created_at, runQuery.data.status, Date.now(), resumedAtMs)
    : false;

  const sourcesQuery = useQuery({
    queryKey: ["run-sources", id],
    queryFn: () => fetchRunSources(id),
    refetchInterval: (query) => {
      if (runIsStale) return false;
      const items = query.state.data;
      const hasActive = items?.some((runSource) => runSource.status === "pending" || runSource.status === "running");
      const runInProgress = runQuery.data ? !isTerminalRunStatus(runQuery.data.status) : true;
      return hasActive || runInProgress ? POLL_INTERVAL_MS : false;
    },
    enabled: !Number.isNaN(id),
  });

  const cancelMutation = useMutation({
    mutationFn: () => cancelRun(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["run", id] }),
  });

  if (Number.isNaN(id)) return <ErrorBanner message="Run inválido." />;
  if (runQuery.isError) {
    return <ErrorBanner message="No se pudo cargar el run." onRetry={() => runQuery.refetch()} />;
  }
  if (!runQuery.data) return <p className="text-sm text-muted-foreground">Cargando…</p>;
  const run = runQuery.data;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="font-display text-3xl font-semibold tracking-tight text-foreground">Run #{run.id}</h1>
        <StatusBadge status={run.status} />
      </div>

      <dl className="grid grid-cols-5 gap-4 rounded-lg border border-border bg-card p-5 shadow-sm">
        <InfoField label="Disparado por" value={run.triggered_by} />
        <InfoField label="Desde" value={formatDate(run.fini)} />
        <InfoField label="Hasta" value={formatDate(run.ffin)} />
        <InfoField label="Iniciado" value={formatDateTime(run.started_at)} />
        <InfoField label="Finalizado" value={formatDateTime(run.finished_at)} />
      </dl>

      {runIsStale && (
        <ErrorBanner
          message="Dejamos de actualizar esta pantalla automáticamente porque el run lleva más de 30 minutos activo (puede seguir trabajando igual, solo dejamos de refrescar solos para no sobrecargar el navegador). Usa Reintentar para retomar las actualizaciones automáticas."
          onRetry={() => {
            setResumedAtMs(Date.now());
            runQuery.refetch();
            sourcesQuery.refetch();
          }}
        />
      )}

      {!isTerminalRunStatus(run.status) && (
        <Button
          variant="destructive"
          disabled={run.cancel_requested || cancelMutation.isPending}
          onClick={() => cancelMutation.mutate()}
        >
          {run.cancel_requested ? "Cancelación solicitada" : "Cancelar run"}
        </Button>
      )}

      <div className={TABLE_SHELL}>
        <div className={TABLE_SCROLL}>
          <table className={TABLE}>
            <thead>
              <tr className={THEAD_ROW}>
                <th className={TH}>Fuente</th>
                <th className={TH}>Estado</th>
                <th className={TH}>Docs nuevos</th>
                <th className={TH}>Actualizados</th>
                <th className={TH}>Docs con error</th>
                <th className={TH}>Error</th>
              </tr>
            </thead>
            <tbody>
              {sourcesQuery.data?.map((runSource) => (
                <tr key={runSource.id} className={TBODY_ROW}>
                  <td className={TD}>{runSource.source_name}</td>
                  <td className={TD}>
                    <StatusBadge status={runSource.status} />
                  </td>
                  <td className={TD_MONO}>{runSource.docs_new}</td>
                  <td className={TD_MONO}>{runSource.docs_updated}</td>
                  <td className={TD_MONO}>{runSource.docs_errors}</td>
                  <td className={`${TD} text-rojo`}>{runSource.error_message ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {!sourcesQuery.isLoading && (sourcesQuery.data?.length ?? 0) === 0 && (
          <EmptyState message="Todavía no hay fuentes procesadas en este run." />
        )}
      </div>
    </div>
  );
}
