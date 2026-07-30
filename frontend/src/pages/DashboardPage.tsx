import { useMemo, useState, type ReactNode } from "react";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { Activity, FileClock, FileText, Radar, type LucideIcon } from "lucide-react";
import { fetchDocuments, fetchDocumentStats } from "../api/documents";
import { fetchRuns } from "../api/runs";
import { fetchAllActiveSources } from "../api/sources";
import type { Document, DocumentReviewStatus } from "../api/types";
import { StatusBadge } from "../components/StatusBadge";
import { EmptyState } from "../components/EmptyState";
import { formatDateTime, formatRelativeTime, todayDateString } from "../lib/formatters";
import { sourceCountsToBuckets, tipoCountsToBuckets, type CountBucket } from "../lib/dashboardStats";
import { TABLE, TABLE_SCROLL, TABLE_SHELL, TBODY_ROW, TD, TD_MONO, TH, THEAD_ROW } from "../lib/tableStyles";
import { NativeSelect } from "../components/ui/native-select";

const TWENTY_FOUR_HOURS_MS = 24 * 60 * 60 * 1000;

const MONTH_LABELS = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"];

const REVIEW_LABELS: Record<DocumentReviewStatus, string> = {
  pending: "Sin revisar",
  useful: "Útil",
  not_useful: "No útil",
};

const REVIEW_STAMP_STYLES: Record<DocumentReviewStatus, string> = {
  pending: "border-grafito/40 text-grafito",
  useful: "border-verde/50 text-verde",
  not_useful: "border-rojo/50 text-rojo",
};

function ReviewStamp({ status }: { status: DocumentReviewStatus }) {
  return (
    <span className={`stamp bg-card ${REVIEW_STAMP_STYLES[status]}`}>
      <span className="stamp-dot" />
      {REVIEW_LABELS[status]}
    </span>
  );
}

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

function BarList({ data }: { data: CountBucket[] }) {
  if (data.length === 0) {
    return <p className="text-sm text-muted-foreground">Sin datos suficientes todavía.</p>;
  }
  const max = Math.max(...data.map((d) => d.count), 1);
  return (
    <div className="max-h-72 space-y-2.5 overflow-y-auto pr-1">
      {data.map((bucket) => (
        <div key={bucket.label} className="space-y-1">
          <div className="flex items-center justify-between gap-3 text-xs">
            <span className="truncate text-muted-foreground" title={bucket.label}>
              {bucket.label}
            </span>
            <span className="shrink-0 font-mono-num text-foreground">{bucket.count}</span>
          </div>
          <div className="h-2 overflow-hidden rounded-full bg-secondary">
            <div
              className="h-full rounded-full bg-sello transition-[width] motion-reduce:transition-none"
              style={{ width: `${(bucket.count / max) * 100}%` }}
            />
          </div>
        </div>
      ))}
    </div>
  );
}

function MonthlyBars({ counts }: { counts: number[] }) {
  const max = Math.max(...counts, 1);
  return (
    <div className="flex h-36 items-stretch gap-2">
      {counts.map((count, index) => (
        <div key={MONTH_LABELS[index]} className="flex h-full flex-1 flex-col items-center justify-end gap-1.5">
          <span className="font-mono-num text-[0.65rem] text-muted-foreground">{count > 0 ? count : ""}</span>
          <div
            className="w-full rounded-t bg-sello transition-[height] motion-reduce:transition-none"
            style={{ height: `${(count / max) * 100}%`, minHeight: count > 0 ? "4px" : "0px" }}
          />
          <span className="text-[0.65rem] text-muted-foreground">{MONTH_LABELS[index]}</span>
        </div>
      ))}
    </div>
  );
}

export function DashboardPage() {
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

  const pendingReviewQuery = useQuery({
    queryKey: ["documents", "pending-count"],
    queryFn: () => fetchDocuments({ review_status: "pending", limit: 1 }),
  });

  const today = todayDateString();
  const novedadesQuery = useQuery({
    queryKey: ["documents", "novedades", today],
    queryFn: () => fetchDocuments({ downloaded_from: today, downloaded_to: today, limit: 8 }),
  });

  const [selectedYear, setSelectedYear] = useState<number | null>(null);
  const [selectedMonth, setSelectedMonth] = useState<number | null>(null);
  const statsQuery = useQuery({
    queryKey: ["documents", "stats", selectedYear, selectedMonth],
    queryFn: () => fetchDocumentStats(selectedYear ?? undefined, selectedMonth ?? undefined),
    placeholderData: keepPreviousData,
  });

  const runsLast24h = (recentRunsQuery.data ?? []).filter(
    (run) => Date.now() - new Date(run.created_at).getTime() <= TWENTY_FOUR_HOURS_MS
  );
  const byStatus: Record<string, number> = { pending: 0, running: 0, completed: 0 };
  for (const run of runsLast24h) byStatus[run.status] = (byStatus[run.status] ?? 0) + 1;

  const recentRuns = recentRunsQuery.data ?? [];

  const tipoBuckets = useMemo(() => tipoCountsToBuckets(statsQuery.data?.by_tipo ?? []), [statsQuery.data]);
  const sourceBuckets = useMemo(() => sourceCountsToBuckets(statsQuery.data?.by_source ?? []), [statsQuery.data]);
  const years = statsQuery.data?.available_years ?? [];
  const effectiveYear = statsQuery.data?.year ?? selectedYear ?? new Date().getFullYear();
  const monthlyCounts = statsQuery.data?.by_month ?? new Array(12).fill(0);

  const sourceNameById = useMemo(
    () => new Map((activeSourcesQuery.data ?? []).map((source) => [source.id, source.name])),
    [activeSourcesQuery.data]
  );
  const novedades: Document[] = novedadesQuery.data?.items ?? [];

  return (
    <div className="space-y-8">
      <div>
        <p className="text-xs font-medium tracking-[0.18em] text-muted-foreground uppercase">Panel de control</p>
        <h1 className="font-display text-3xl font-semibold tracking-tight text-foreground">Dashboard</h1>
      </div>

      <div className="grid grid-cols-4 gap-4">
        <StatCard icon={Radar} label="Fuentes activas" value={activeSourcesQuery.data?.length ?? "—"} />
        <StatCard
          icon={FileClock}
          label="Sin revisar"
          value={pendingReviewQuery.data?.total ?? "—"}
        />
        <StatCard icon={FileText} label="Documentos totales" value={documentsCountQuery.data?.total ?? "—"} />
        <StatCard
          icon={Activity}
          label="Runs (24h)"
          value={runsLast24h.length}
          detail={`${byStatus.pending} pendientes · ${byStatus.running} en curso · ${byStatus.completed} completados`}
        />
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div className="rounded-lg border border-border bg-card p-5 shadow-sm">
          <h2 className="font-display text-lg font-semibold text-foreground">Documentos por tipo</h2>
          <div className="mt-4">
            <BarList data={tipoBuckets} />
          </div>
        </div>
        <div className="rounded-lg border border-border bg-card p-5 shadow-sm">
          <div className="flex items-center justify-between">
            <h2 className="font-display text-lg font-semibold text-foreground">Documentos por fuente</h2>
            <label className="flex items-center gap-2 text-sm text-muted-foreground">
              Mes
              <NativeSelect
                value={selectedMonth === null ? "" : String(selectedMonth)}
                onChange={(event) => setSelectedMonth(event.target.value === "" ? null : Number(event.target.value))}
                className="w-36"
              >
                <option value="">Histórico completo</option>
                {MONTH_LABELS.map((label, index) => (
                  <option key={label} value={index + 1}>
                    {label}
                  </option>
                ))}
              </NativeSelect>
            </label>
          </div>
          <div className="mt-4">
            <BarList data={sourceBuckets} />
          </div>
        </div>
      </div>

      <div className="rounded-lg border border-border bg-card p-5 shadow-sm">
        <div className="flex items-center justify-between">
          <h2 className="font-display text-lg font-semibold text-foreground">Actividad mensual</h2>
          {years.length > 0 && (
            <label className="flex items-center gap-2 text-sm text-muted-foreground">
              Año
              <NativeSelect
                value={String(effectiveYear)}
                onChange={(event) => setSelectedYear(Number(event.target.value))}
                className="w-28"
              >
                {years.map((year) => (
                  <option key={year} value={year}>
                    {year}
                  </option>
                ))}
              </NativeSelect>
            </label>
          )}
        </div>
        <div className="mt-4">
          <MonthlyBars counts={monthlyCounts} />
        </div>
      </div>

      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="font-display text-lg font-semibold text-foreground">Novedades</h2>
          <Link to="/documents" state={{ downloadedToday: true }} className="text-sm font-medium text-sello-ink hover:underline">
            Ver todos →
          </Link>
        </div>
        <div className={TABLE_SHELL}>
          <div className={TABLE_SCROLL}>
            <table className={TABLE}>
              <thead>
                <tr className={THEAD_ROW}>
                  <th className={TH}>Título</th>
                  <th className={TH}>Fuente</th>
                  <th className={TH}>Tipo</th>
                  <th className={`${TH} whitespace-nowrap`}>Agregado</th>
                  <th className={`${TH} whitespace-nowrap`}>Revisión</th>
                </tr>
              </thead>
              <tbody>
                {novedades.map((document) => (
                  <tr key={document.id} className={TBODY_ROW}>
                    <td className={`${TD} font-medium text-foreground`}>{document.title}</td>
                    <td className={TD}>{sourceNameById.get(document.source_id) ?? "—"}</td>
                    <td className={TD}>{document.tipo ?? "—"}</td>
                    <td className={`${TD_MONO} whitespace-nowrap`}>{formatRelativeTime(document.downloaded_at)}</td>
                    <td className={TD}>
                      <ReviewStamp status={document.review_status} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {novedades.length === 0 && <EmptyState message="No han llegado documentos hoy." />}
        </div>
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
