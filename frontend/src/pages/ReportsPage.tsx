import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FileBarChart2 } from "lucide-react";
import { ApiError } from "../api/client";
import { downloadFromUrl } from "../api/documents";
import { createReport, fetchReports, fetchReportUrl, type MonthlyReport } from "../api/reports";
import { EmptyState } from "../components/EmptyState";
import { ErrorBanner } from "../components/ErrorBanner";
import { StatusBadge } from "../components/StatusBadge";
import { TableRowsSkeleton } from "../components/TableSkeleton";
import { Button } from "../components/ui/button";
import { formatDateTime, formatMonth, getPreviousMonthString } from "../lib/formatters";
import { TABLE, TABLE_SCROLL, TABLE_SHELL, TBODY_ROW, TD, TD_MONO, TH, THEAD_ROW } from "../lib/tableStyles";

const POLL_INTERVAL_MS = 4000;
const TERMINAL_STATUSES = new Set(["completed", "failed"]);

export function ReportsPage() {
  const maxMonth = getPreviousMonthString();
  const [selectedMonth, setSelectedMonth] = useState(maxMonth);
  const [downloadError, setDownloadError] = useState<string | null>(null);
  const [generateError, setGenerateError] = useState<string | null>(null);
  const queryClient = useQueryClient();

  const reportsQuery = useQuery({
    queryKey: ["monthly-reports"],
    queryFn: () => fetchReports({ limit: 50 }),
    refetchInterval: (query) => {
      const data = query.state.data;
      const hasActive = data?.some((item) => !TERMINAL_STATUSES.has(item.status));
      return hasActive ? POLL_INTERVAL_MS : false;
    },
  });

  const generateMutation = useMutation({
    mutationFn: (period: string) => createReport(period),
    onSuccess: () => {
      setGenerateError(null);
      queryClient.invalidateQueries({ queryKey: ["monthly-reports"] });
    },
    onError: (error: unknown) =>
      setGenerateError(error instanceof ApiError ? error.message : "No se pudo generar el reporte."),
  });

  async function handleDownload(item: MonthlyReport) {
    setDownloadError(null);
    try {
      const url = await fetchReportUrl(item.id);
      await downloadFromUrl(url, `reporte_${item.period.slice(0, 7)}.pdf`);
    } catch {
      setDownloadError("No se pudo descargar el reporte. El enlace pudo haber expirado — intenta de nuevo.");
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <p className="flex items-center gap-1.5 text-xs font-medium tracking-[0.18em] text-muted-foreground uppercase">
          <FileBarChart2 className="size-3.5" aria-hidden="true" />
          Métricas de extracción
        </p>
        <h1 className="font-display text-3xl font-semibold tracking-tight text-foreground">Reportes</h1>
      </div>

      <div className="flex items-end gap-3">
        <div className="flex flex-col gap-1">
          <label htmlFor="report-month" className="text-xs font-medium text-muted-foreground">
            Mes
          </label>
          <input
            id="report-month"
            type="month"
            className="rounded-md border border-input bg-background px-3 py-1.5 text-sm"
            max={maxMonth}
            value={selectedMonth}
            onChange={(event) => setSelectedMonth(event.target.value)}
          />
        </div>
        <Button
          onClick={() => generateMutation.mutate(selectedMonth)}
          disabled={!selectedMonth || selectedMonth > maxMonth || generateMutation.isPending}
        >
          Generar
        </Button>
      </div>

      {reportsQuery.isError && (
        <ErrorBanner message="No se pudieron cargar los reportes." onRetry={() => reportsQuery.refetch()} />
      )}
      {downloadError && <ErrorBanner message={downloadError} />}
      {generateError && <ErrorBanner message={generateError} />}

      <div className={TABLE_SHELL}>
        <div className={TABLE_SCROLL}>
          <table className={TABLE} aria-busy={reportsQuery.isLoading}>
            <thead>
              <tr className={THEAD_ROW}>
                <th className={TH}>Mes</th>
                <th className={TH}>Estado</th>
                <th className={TH}>Creado</th>
                <th className={TH}>Acciones</th>
              </tr>
            </thead>
            <tbody>
              {reportsQuery.isLoading ? (
                <TableRowsSkeleton rows={6} columns={4} widths={["w-28", "w-24", "w-28", "w-24"]} />
              ) : (
                reportsQuery.data?.map((item) => (
                  <tr key={item.id} className={TBODY_ROW}>
                    <td className={TD}>{formatMonth(item.period)}</td>
                    <td className={TD}>
                      <StatusBadge status={item.status} />
                    </td>
                    <td className={TD_MONO}>{formatDateTime(item.created_at)}</td>
                    <td className={TD}>
                      {item.status === "completed" && (
                        <Button variant="outline" size="sm" onClick={() => handleDownload(item)}>
                          Descargar
                        </Button>
                      )}
                      {item.status === "failed" && <span className="text-xs text-rojo">{item.error_message}</span>}
                      {(item.status === "pending" || item.status === "running") && (
                        <span className="text-xs text-muted-foreground">—</span>
                      )}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
        {!reportsQuery.isLoading && (reportsQuery.data?.length ?? 0) === 0 && (
          <EmptyState message="Todavía no se ha generado ningún reporte." />
        )}
      </div>
    </div>
  );
}
