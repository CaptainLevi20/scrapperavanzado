import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { fetchDocuments } from "../api/documents";
import { fetchRuns } from "../api/runs";
import { fetchSources } from "../api/sources";
import { StatusBadge } from "../components/StatusBadge";
import { formatDateTime } from "../lib/formatters";

const TWENTY_FOUR_HOURS_MS = 24 * 60 * 60 * 1000;

export function OverviewPage() {
  const activeSourcesQuery = useQuery({
    queryKey: ["sources", "active-count"],
    queryFn: () => fetchSources({ active: true, limit: 100 }),
  });

  const recentRunsQuery = useQuery({
    queryKey: ["runs", "recent"],
    queryFn: () => fetchRuns({ limit: 50 }),
  });

  const documentsCountQuery = useQuery({
    queryKey: ["documents", "total-count"],
    queryFn: () => fetchDocuments({ limit: 1 }),
  });

  const runsLast24h = (recentRunsQuery.data ?? []).filter(
    (run) => Date.now() - new Date(run.created_at).getTime() <= TWENTY_FOUR_HOURS_MS
  );
  const byStatus: Record<string, number> = { pending: 0, running: 0, completed: 0 };
  for (const run of runsLast24h) byStatus[run.status] = (byStatus[run.status] ?? 0) + 1;

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">Resumen</h1>
      <div className="grid grid-cols-3 gap-4">
        <div className="rounded border p-4">
          <p className="text-sm text-gray-500">Fuentes activas</p>
          <p className="text-3xl font-bold">{activeSourcesQuery.data?.length ?? "—"}</p>
        </div>
        <div className="rounded border p-4">
          <p className="text-sm text-gray-500">Runs (24h)</p>
          <p className="text-3xl font-bold">{runsLast24h.length}</p>
          <p className="text-xs text-gray-500">
            {byStatus.pending} pendientes · {byStatus.running} en curso · {byStatus.completed} completados
          </p>
        </div>
        <div className="rounded border p-4">
          <p className="text-sm text-gray-500">Documentos totales</p>
          <p className="text-3xl font-bold">{documentsCountQuery.data?.total ?? "—"}</p>
        </div>
      </div>

      <div>
        <h2 className="mb-2 text-lg font-medium">Últimos runs</h2>
        <table className="w-full border-collapse text-left">
          <thead>
            <tr className="border-b">
              <th className="py-2">ID</th>
              <th className="py-2">Estado</th>
              <th className="py-2">Creado</th>
            </tr>
          </thead>
          <tbody>
            {(recentRunsQuery.data ?? []).slice(0, 5).map((run) => (
              <tr key={run.id} className="border-b">
                <td className="py-2">
                  <Link to={`/runs/${run.id}`} className="text-blue-600 underline">
                    #{run.id}
                  </Link>
                </td>
                <td className="py-2"><StatusBadge status={run.status} /></td>
                <td className="py-2">{formatDateTime(run.created_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
