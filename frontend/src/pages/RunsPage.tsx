import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchRuns } from "../api/runs";
import { ErrorBanner } from "../components/ErrorBanner";
import { StatusBadge } from "../components/StatusBadge";
import { formatDateTime } from "../lib/formatters";

const PAGE_SIZE = 20;
const POLL_INTERVAL_MS = 4000;

export function RunsPage() {
  const [statusFilter, setStatusFilter] = useState("");
  const [page, setPage] = useState(0);

  const runsQuery = useQuery({
    queryKey: ["runs", statusFilter, page],
    queryFn: () =>
      fetchRuns({
        status_filter: statusFilter || undefined,
        limit: PAGE_SIZE,
        offset: page * PAGE_SIZE,
      }),
    refetchInterval: (query) => {
      const data = query.state.data;
      const hasActiveRun = data?.some((run) => run.status !== "completed");
      return hasActiveRun ? POLL_INTERVAL_MS : false;
    },
  });

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold">Runs</h1>

      <label className="flex items-center gap-2 text-sm">
        Estado
        <select
          aria-label="Estado del run"
          value={statusFilter}
          onChange={(event) => {
            setStatusFilter(event.target.value);
            setPage(0);
          }}
          className="rounded border px-2 py-1"
        >
          <option value="">Todos</option>
          <option value="pending">Pendiente</option>
          <option value="running">En curso</option>
          <option value="completed">Completado</option>
        </select>
      </label>

      {runsQuery.isError && (
        <ErrorBanner message="No se pudieron cargar los runs." onRetry={() => runsQuery.refetch()} />
      )}

      <table className="w-full border-collapse text-left">
        <thead>
          <tr className="border-b">
            <th className="py-2">ID</th>
            <th className="py-2">Disparado por</th>
            <th className="py-2">Estado</th>
            <th className="py-2">Creado</th>
          </tr>
        </thead>
        <tbody>
          {runsQuery.data?.map((run) => (
            <tr key={run.id} className="border-b">
              <td className="py-2">{run.id}</td>
              <td className="py-2">{run.triggered_by}</td>
              <td className="py-2"><StatusBadge status={run.status} /></td>
              <td className="py-2">{formatDateTime(run.created_at)}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <div className="flex justify-end gap-2">
        <button
          disabled={page === 0}
          onClick={() => setPage((current) => current - 1)}
          className="rounded border px-3 py-1 disabled:opacity-50"
        >
          Anterior
        </button>
        <button
          disabled={(runsQuery.data?.length ?? 0) < PAGE_SIZE}
          onClick={() => setPage((current) => current + 1)}
          className="rounded border px-3 py-1 disabled:opacity-50"
        >
          Siguiente
        </button>
      </div>
    </div>
  );
}
