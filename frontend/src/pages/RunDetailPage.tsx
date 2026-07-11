import { useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { cancelRun, fetchRun, fetchRunSources } from "../api/runs";
import { StatusBadge } from "../components/StatusBadge";
import { Button } from "../components/ui/button";
import { formatDateTime } from "../lib/formatters";

const POLL_INTERVAL_MS = 4000;

export function RunDetailPage() {
  const { runId } = useParams<{ runId: string }>();
  const id = Number(runId);
  const queryClient = useQueryClient();

  const runQuery = useQuery({
    queryKey: ["run", id],
    queryFn: () => fetchRun(id),
    refetchInterval: (query) => (query.state.data?.status !== "completed" ? POLL_INTERVAL_MS : false),
  });

  const sourcesQuery = useQuery({
    queryKey: ["run-sources", id],
    queryFn: () => fetchRunSources(id),
    refetchInterval: (query) => {
      const items = query.state.data;
      const hasActive = items?.some((runSource) => runSource.status === "pending" || runSource.status === "running");
      return hasActive ? POLL_INTERVAL_MS : false;
    },
  });

  const cancelMutation = useMutation({
    mutationFn: () => cancelRun(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["run", id] }),
  });

  if (!runQuery.data) return <p>Cargando…</p>;
  const run = runQuery.data;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Run #{run.id}</h1>
        <StatusBadge status={run.status} />
      </div>
      <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-sm">
        <dt className="font-medium">Disparado por</dt>
        <dd>{run.triggered_by}</dd>
        <dt className="font-medium">Iniciado</dt>
        <dd>{formatDateTime(run.started_at)}</dd>
        <dt className="font-medium">Finalizado</dt>
        <dd>{formatDateTime(run.finished_at)}</dd>
      </dl>

      {run.status !== "completed" && (
        <Button
          variant="destructive"
          disabled={run.cancel_requested || cancelMutation.isPending}
          onClick={() => cancelMutation.mutate()}
        >
          {run.cancel_requested ? "Cancelación solicitada" : "Cancelar run"}
        </Button>
      )}

      <table className="w-full border-collapse text-left">
        <thead>
          <tr className="border-b">
            <th className="py-2">Fuente (id)</th>
            <th className="py-2">Estado</th>
            <th className="py-2">Docs nuevos</th>
            <th className="py-2">Docs con error</th>
            <th className="py-2">Error</th>
          </tr>
        </thead>
        <tbody>
          {sourcesQuery.data?.map((runSource) => (
            <tr key={runSource.id} className="border-b">
              <td className="py-2">{runSource.source_id}</td>
              <td className="py-2"><StatusBadge status={runSource.status} /></td>
              <td className="py-2">{runSource.docs_new}</td>
              <td className="py-2">{runSource.docs_errors}</td>
              <td className="py-2 text-red-600">{runSource.error_message ?? "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
