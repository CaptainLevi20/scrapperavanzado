import type { ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { Activity, FileText, Radar, type LucideIcon } from "lucide-react";
import { fetchDocuments } from "../api/documents";
import { fetchRuns } from "../api/runs";
import { fetchAllActiveSources } from "../api/sources";
import { StatusBadge } from "../components/StatusBadge";
import { EmptyState } from "../components/EmptyState";
import { formatDateTime } from "../lib/formatters";
import { TABLE, TABLE_SCROLL, TABLE_SHELL, TBODY_ROW, TD, TD_MONO, TH, THEAD_ROW } from "../lib/tableStyles";

const TWENTY_FOUR_HOURS_MS = 24 * 60 * 60 * 1000;

function StatCard({
  icon: Icon,
  label,
  value,
  detail,
}: {
  icon: LucideIcon;
  label: string;
  value: ReactNode;
  detail?: string;
}) {
  return (
    <div className="rounded-lg border border-border bg-card p-5 shadow-sm">
      <div className="flex items-center gap-2 text-muted-foreground">
        <Icon className="size-4" aria-hidden="true" />
        <p className="text-xs font-medium tracking-wide uppercase">{label}</p>
      </div>
      <p className="mt-3 font-mono-num text-3xl font-semibold text-foreground">{value}</p>
      {detail && <p className="mt-1 text-xs text-muted-foreground">{detail}</p>}
    </div>
  );
}

export function OverviewPage() {
  const activeSourcesQuery = useQuery({
    queryKey: ["sources", "active-count"],
    queryFn: fetchAllActiveSources,
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

  const recentRuns = recentRunsQuery.data ?? [];

  return (
    <div className="space-y-8">
      <div>
        <p className="text-xs font-medium tracking-[0.18em] text-muted-foreground uppercase">Panel de control</p>
        <h1 className="font-display text-3xl font-semibold tracking-tight text-foreground">Resumen</h1>
      </div>

      <div className="grid grid-cols-3 gap-4">
        <StatCard icon={Radar} label="Fuentes activas" value={activeSourcesQuery.data?.length ?? "—"} />
        <StatCard
          icon={Activity}
          label="Runs (24h)"
          value={runsLast24h.length}
          detail={`${byStatus.pending} pendientes · ${byStatus.running} en curso · ${byStatus.completed} completados`}
        />
        <StatCard icon={FileText} label="Documentos totales" value={documentsCountQuery.data?.total ?? "—"} />
      </div>

      <div className="space-y-3">
        <h2 className="font-display text-lg font-semibold text-foreground">Últimos runs</h2>
        <div className={TABLE_SHELL}>
          <div className={TABLE_SCROLL}>
            <table className={TABLE}>
              <thead>
                <tr className={THEAD_ROW}>
                  <th className={TH}>ID</th>
                  <th className={TH}>Estado</th>
                  <th className={TH}>Creado</th>
                </tr>
              </thead>
              <tbody>
                {recentRuns.slice(0, 5).map((run) => (
                  <tr key={run.id} className={TBODY_ROW}>
                    <td className={TD_MONO}>
                      <Link to={`/runs/${run.id}`} className="font-semibold text-sello-ink hover:underline">
                        #{run.id}
                      </Link>
                    </td>
                    <td className={TD}>
                      <StatusBadge status={run.status} />
                    </td>
                    <td className={TD}>{formatDateTime(run.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {recentRuns.length === 0 && <EmptyState message="Todavía no se ha ejecutado ningún run." />}
        </div>
      </div>
    </div>
  );
}
