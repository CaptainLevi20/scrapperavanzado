import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Archive } from "lucide-react";
import { fetchBulkDownloads, fetchBulkDownloadUrl } from "../api/bulkDownloads";
import { downloadFromUrl } from "../api/documents";
import { EmptyState } from "../components/EmptyState";
import { ErrorBanner } from "../components/ErrorBanner";
import { StatusBadge } from "../components/StatusBadge";
import { TableRowsSkeleton } from "../components/TableSkeleton";
import { Button } from "../components/ui/button";
import { formatDateTime, formatNumber } from "../lib/formatters";
import { TABLE, TABLE_SCROLL, TABLE_SHELL, TBODY_ROW, TD, TD_MONO, TH, THEAD_ROW } from "../lib/tableStyles";

const POLL_INTERVAL_MS = 4000;
const TERMINAL_STATUSES = new Set(["completed", "failed"]);

export function BulkDownloadsPage() {
  const bulkDownloadsQuery = useQuery({
    queryKey: ["bulk-downloads"],
    queryFn: () => fetchBulkDownloads({ limit: 50 }),
    refetchInterval: (query) => {
      const data = query.state.data;
      const hasActive = data?.some((item) => !TERMINAL_STATUSES.has(item.status));
      return hasActive ? POLL_INTERVAL_MS : false;
    },
  });

  const [downloadError, setDownloadError] = useState<string | null>(null);

  async function handleDownload(id: number) {
    setDownloadError(null);
    try {
      const url = await fetchBulkDownloadUrl(id);
      await downloadFromUrl(url, `descarga_masiva_${id}.zip`);
    } catch {
      setDownloadError("No se pudo descargar el archivo. El enlace pudo haber expirado — intenta de nuevo.");
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <p className="flex items-center gap-1.5 text-xs font-medium tracking-[0.18em] text-muted-foreground uppercase">
          <Archive className="size-3.5" aria-hidden="true" />
          Historial de descargas
        </p>
        <h1 className="font-display text-3xl font-semibold tracking-tight text-foreground">Descargas masivas</h1>
      </div>

      {bulkDownloadsQuery.isError && (
        <ErrorBanner
          message="No se pudieron cargar las descargas masivas."
          onRetry={() => bulkDownloadsQuery.refetch()}
        />
      )}

      {downloadError && <ErrorBanner message={downloadError} />}

      <div className={TABLE_SHELL}>
        <div className={TABLE_SCROLL}>
          <table className={TABLE} aria-busy={bulkDownloadsQuery.isLoading}>
            <thead>
              <tr className={THEAD_ROW}>
                <th className={TH}>ID</th>
                <th className={TH}>Estado</th>
                <th className={TH}>Documentos</th>
                <th className={TH}>Creado</th>
                <th className={TH}>Descarga</th>
              </tr>
            </thead>
            <tbody>
              {bulkDownloadsQuery.isLoading ? (
                <TableRowsSkeleton rows={6} columns={5} widths={["w-10", "w-24", "w-16", "w-28", "w-24"]} />
              ) : (
                bulkDownloadsQuery.data?.map((item) => (
                <tr key={item.id} className={TBODY_ROW}>
                  <td className={TD_MONO}>#{item.id}</td>
                  <td className={TD}>
                    <StatusBadge status={item.status} />
                  </td>
                  <td className={TD}>
                    {formatNumber(item.document_count)}
                    {item.failed_count > 0 && (
                      <span className="ml-1.5 text-xs text-muted-foreground">({formatNumber(item.failed_count)} omitidos)</span>
                    )}
                  </td>
                  <td className={TD_MONO}>{formatDateTime(item.created_at)}</td>
                  <td className={TD}>
                    {item.status === "completed" && (
                      <Button variant="outline" size="sm" onClick={() => handleDownload(item.id)}>
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
        {!bulkDownloadsQuery.isLoading && (bulkDownloadsQuery.data?.length ?? 0) === 0 && (
          <EmptyState message="Todavía no se ha generado ninguna descarga masiva." />
        )}
      </div>
    </div>
  );
}
