import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Power, Radar } from "lucide-react";
import { fetchAllSources, fetchSourceHealth, fetchSources, updateSource } from "../api/sources";
import type { Source, SourceHealth } from "../api/types";
import { EmptyState } from "../components/EmptyState";
import { SourceHealthStamp } from "../components/SourceHealthStamp";
import { ErrorBanner } from "../components/ErrorBanner";
import { TableRowsSkeleton } from "../components/TableSkeleton";
import { Button } from "../components/ui/button";
import { NativeSelect } from "../components/ui/native-select";
import { useAuth } from "../auth/AuthContext";
import { formatDate } from "../lib/formatters";
import { TABLE, TABLE_SCROLL, TABLE_SHELL, TBODY_ROW, TD, TH, THEAD_ROW } from "../lib/tableStyles";

const PAGE_SIZE = 20;

function SourceRow({ source, health }: { source: Source; health: SourceHealth | undefined }) {
  const queryClient = useQueryClient();
  const { isAdmin } = useAuth();
  const toggleMutation = useMutation({
    mutationFn: () => updateSource(source.id, { active: !source.active }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["sources"] }),
  });

  return (
    <tr className={TBODY_ROW}>
      <td className={`${TD} font-medium text-foreground`}>{source.name}</td>
      <td className={TD}>
        <span className={`stamp bg-card ${source.active ? "border-verde/50 text-verde" : "border-grafito/40 text-grafito"}`}>
          <span className="stamp-dot" />
          {source.active ? "Activa" : "Inactiva"}
        </span>
      </td>
      <td className={TD}>
        {/* Solo las fuentes activas se vigilan: una inactiva no tiene fila de salud. */}
        <div className="flex flex-col items-start gap-1">
          <span className="font-mono-num">{formatDate(health?.ultimo_documento ?? null)}</span>
          {health?.alerta && <SourceHealthStamp alerta={health.alerta} detalle={health.detalle} />}
          {health?.alerta && <span className="text-xs text-muted-foreground">{health.detalle}</span>}
        </div>
      </td>
      <td className={TD}>
        {isAdmin && (
          <Button variant="outline" size="sm" onClick={() => toggleMutation.mutate()} disabled={toggleMutation.isPending}>
            <Power className="size-3.5" aria-hidden="true" />
            {source.active ? "Desactivar" : "Activar"}
          </Button>
        )}
      </td>
    </tr>
  );
}

export function SourcesPage() {
  const [sourceId, setSourceId] = useState("");
  const [activeFilter, setActiveFilter] = useState("all");
  const [page, setPage] = useState(0);

  const allSourcesQuery = useQuery({ queryKey: ["all-sources-for-filter"], queryFn: fetchAllSources });
  const sortedSourceOptions = [...(allSourcesQuery.data ?? [])].sort((a, b) => a.name.localeCompare(b.name));

  const sourcesQuery = useQuery({
    queryKey: ["sources", sourceId, activeFilter, page],
    queryFn: () =>
      // Asks for one extra row beyond the page size — the backend has no total
      // count to compare against (unlike /documents), so this is how "Siguiente"
      // knows whether there's really another page instead of just guessing from
      // whether the current page happened to come back full.
      fetchSources({
        id: sourceId ? Number(sourceId) : undefined,
        active: activeFilter === "all" ? undefined : activeFilter === "true",
        limit: PAGE_SIZE + 1,
        offset: page * PAGE_SIZE,
      }),
  });
  const visibleSources = sourcesQuery.data?.slice(0, PAGE_SIZE);

  const sourceHealthQuery = useQuery({ queryKey: ["sources", "health"], queryFn: fetchSourceHealth });
  const healthBySourceId = new Map((sourceHealthQuery.data ?? []).map((health) => [health.source_id, health]));
  const hasNextPage = (sourcesQuery.data?.length ?? 0) > PAGE_SIZE;

  return (
    <div className="space-y-6">
      <div>
        <p className="flex items-center gap-1.5 text-xs font-medium tracking-[0.18em] text-muted-foreground uppercase">
          <Radar className="size-3.5" aria-hidden="true" />
          Estaciones de vigilancia
        </p>
        <h1 className="font-display text-3xl font-semibold tracking-tight text-foreground">Fuentes</h1>
      </div>

      <div className="flex gap-3">
        <label className="flex items-center gap-2 text-sm text-muted-foreground">
          Fuente
          <NativeSelect
            value={sourceId}
            onChange={(event) => {
              setSourceId(event.target.value);
              setPage(0);
            }}
            className="w-44"
          >
            <option value="">Todas</option>
            {sortedSourceOptions.map((source) => (
              <option key={source.id} value={source.id}>
                {source.name}
              </option>
            ))}
          </NativeSelect>
        </label>
        <label className="flex items-center gap-2 text-sm text-muted-foreground">
          Estado
          <NativeSelect
            aria-label="Estado"
            value={activeFilter}
            onChange={(event) => {
              setActiveFilter(event.target.value);
              setPage(0);
            }}
            className="w-36"
          >
            <option value="all">Todas</option>
            <option value="true">Activas</option>
            <option value="false">Inactivas</option>
          </NativeSelect>
        </label>
      </div>

      {sourcesQuery.isError && (
        <ErrorBanner message="No se pudieron cargar las fuentes." onRetry={() => sourcesQuery.refetch()} />
      )}

      <div className={TABLE_SHELL}>
        <div className={TABLE_SCROLL}>
          <table className={TABLE} aria-busy={sourcesQuery.isLoading}>
            <thead>
              <tr className={THEAD_ROW}>
                <th className={TH}>Nombre</th>
                <th className={TH}>Estado</th>
                <th className={TH}>Último documento</th>
                <th className={TH}>Acciones</th>
              </tr>
            </thead>
            <tbody>
              {sourcesQuery.isLoading ? (
                <TableRowsSkeleton rows={6} columns={4} widths={["w-48", "w-20", "w-28", "w-24"]} />
              ) : (
                visibleSources?.map((source) => (
                  <SourceRow key={source.id} source={source} health={healthBySourceId.get(source.id)} />
                ))
              )}
            </tbody>
          </table>
        </div>
        {!sourcesQuery.isLoading && (visibleSources?.length ?? 0) === 0 && (
          <EmptyState message="No hay fuentes que coincidan con estos filtros." />
        )}
      </div>

      <div className="flex justify-end gap-2">
        <Button
          variant="outline"
          size="sm"
          disabled={page === 0}
          onClick={() => setPage((current) => current - 1)}
        >
          Anterior
        </Button>
        <Button variant="outline" size="sm" disabled={!hasNextPage} onClick={() => setPage((current) => current + 1)}>
          Siguiente
        </Button>
      </div>
    </div>
  );
}
