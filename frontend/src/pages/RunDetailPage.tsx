import { useState } from "react";
import { useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { downloadBlob } from "../api/documents";
import { cancelRun, fetchRun, fetchRunReportBlob, fetchRunSources, retryFailedRunSources } from "../api/runs";
import { EmptyState } from "../components/EmptyState";
import { ErrorBanner } from "../components/ErrorBanner";
import { StatusBadge } from "../components/StatusBadge";
import { TableRowsSkeleton } from "../components/TableSkeleton";
import { Button } from "../components/ui/button";
import { Skeleton } from "../components/ui/skeleton";
import { TABLE, TABLE_SCROLL, TABLE_SHELL, TBODY_ROW, TD, TD_MONO, TH, THEAD_ROW } from "../lib/tableStyles";
import { formatDate, formatDateTime, formatNumber } from "../lib/formatters";
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

// Shown while the run's own record is still loading — mirrors the real layout
// (title, the 5-field summary card, and the per-source table) so the page
// doesn't jump when the data lands.
function RunDetailSkeleton() {
  return (
    <div className="space-y-6" aria-busy="true">
      <div className="flex items-center justify-between">
        <Skeleton className="h-8 w-40" />
        <Skeleton className="h-6 w-24" />
      </div>
      <div className="grid grid-cols-5 gap-4 rounded-lg border border-border bg-card p-5 shadow-sm">
        {Array.from({ length: 5 }).map((_, index) => (
          <div key={index} className="space-y-2">
            <Skeleton className="h-3 w-20" />
            <Skeleton className="h-4 w-24" />
          </div>
        ))}
      </div>
      <div className={TABLE_SHELL}>
        <div className={TABLE_SCROLL}>
          <table className={TABLE} aria-busy="true">
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
              <TableRowsSkeleton rows={5} columns={6} widths={["w-32", "w-24", "w-10", "w-10", "w-10", "w-16"]} />
            </tbody>
          </table>
        </div>
      </div>
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

  const retryMutation = useMutation({
    mutationFn: () => retryFailedRunSources(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["run", id] });
      queryClient.invalidateQueries({ queryKey: ["run-sources", id] });
    },
  });

  const exportMutation = useMutation({
    mutationFn: () => fetchRunReportBlob(id),
    onSuccess: (blob) => downloadBlob(blob, `informe_run_${id}.xlsx`),
  });

  if (Number.isNaN(id)) return <ErrorBanner message="Run inválido." />;
  if (runQuery.isError) {
    return <ErrorBanner message="No se pudo cargar el run." onRetry={() => runQuery.refetch()} />;
  }
  if (!runQuery.data) return <RunDetailSkeleton />;
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
          variant="info"
          message="El run sigue activo, pero esta pantalla dejó de actualizarse sola. Usa 'Actualizar estado' para ver su progreso más reciente."
          retryLabel="Actualizar estado"
          onRetry={() => {
            setResumedAtMs(Date.now());
            runQuery.refetch();
            sourcesQuery.refetch();
          }}
        />
      )}

      <div className="flex flex-wrap items-center gap-3">
        {!isTerminalRunStatus(run.status) && (
          <Button
            variant="destructive"
            disabled={run.cancel_requested || cancelMutation.isPending}
            onClick={() => cancelMutation.mutate()}
          >
            {run.cancel_requested ? "Cancelación solicitada" : "Cancelar run"}
          </Button>
        )}

        {(run.status === "failed" || run.status === "completed_with_errors") && (
          <Button
            variant="outline"
            disabled={retryMutation.isPending}
            onClick={() => retryMutation.mutate()}
          >
            Reintentar fuentes fallidas
          </Button>
        )}

        <Button variant="outline" size="sm" disabled={exportMutation.isPending} onClick={() => exportMutation.mutate()}>
          {exportMutation.isPending ? "Generando informe..." : "Exportar a Excel"}
        </Button>
      </div>

      {exportMutation.isError && <ErrorBanner message="No se pudo generar el informe." onRetry={() => exportMutation.mutate()} />}

      <div className={TABLE_SHELL}>
        <div className={TABLE_SCROLL}>
          <table className={TABLE} aria-busy={sourcesQuery.isLoading}>
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
              {sourcesQuery.isLoading ? (
                <TableRowsSkeleton rows={5} columns={6} widths={["w-32", "w-24", "w-10", "w-10", "w-10", "w-16"]} />
              ) : (
                sourcesQuery.data?.map((runSource) => (
                <tr key={runSource.id} className={TBODY_ROW}>
                  <td className={TD}>{runSource.source_name}</td>
                  <td className={TD}>
                    <StatusBadge status={runSource.status} />
                  </td>
                  <td className={TD_MONO}>{formatNumber(runSource.docs_new)}</td>
                  <td className={TD_MONO}>{formatNumber(runSource.docs_updated)}</td>
                  <td className={TD_MONO}>{formatNumber(runSource.docs_errors)}</td>
                  <td className={`${TD} text-rojo`}>{runSource.error_message ?? "—"}</td>
                </tr>
                ))
              )}
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
