import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Power, Radar } from "lucide-react";
import { fetchSourceFamilies } from "../api/sourceFamilies";
import { fetchSources, updateSource } from "../api/sources";
import type { Source } from "../api/types";
import { EmptyState } from "../components/EmptyState";
import { ErrorBanner } from "../components/ErrorBanner";
import { Button } from "../components/ui/button";
import { NativeSelect } from "../components/ui/native-select";
import { TABLE, TABLE_SCROLL, TABLE_SHELL, TBODY_ROW, TD, TD_MONO, TH, THEAD_ROW } from "../lib/tableStyles";

const PAGE_SIZE = 20;

function SourceRow({ source }: { source: Source }) {
  const queryClient = useQueryClient();
  const toggleMutation = useMutation({
    mutationFn: () => updateSource(source.id, { active: !source.active }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["sources"] }),
  });

  return (
    <tr className={TBODY_ROW}>
      <td className={`${TD} font-medium text-foreground`}>{source.name}</td>
      <td className={`${TD_MONO}`}>{source.family_key}</td>
      <td className={TD}>
        <span className={`stamp bg-card ${source.active ? "border-verde/50 text-verde" : "border-grafito/40 text-grafito"}`}>
          <span className="stamp-dot" />
          {source.active ? "Activa" : "Inactiva"}
        </span>
      </td>
      <td className={TD}>
        <Button variant="outline" size="sm" onClick={() => toggleMutation.mutate()} disabled={toggleMutation.isPending}>
          <Power className="size-3.5" aria-hidden="true" />
          {source.active ? "Desactivar" : "Activar"}
        </Button>
      </td>
    </tr>
  );
}

export function SourcesPage() {
  const [familyKey, setFamilyKey] = useState("");
  const [activeFilter, setActiveFilter] = useState("all");
  const [page, setPage] = useState(0);

  const familiesQuery = useQuery({ queryKey: ["source-families"], queryFn: fetchSourceFamilies });

  const sourcesQuery = useQuery({
    queryKey: ["sources", familyKey, activeFilter, page],
    queryFn: () =>
      // Asks for one extra row beyond the page size — the backend has no total
      // count to compare against (unlike /documents), so this is how "Siguiente"
      // knows whether there's really another page instead of just guessing from
      // whether the current page happened to come back full.
      fetchSources({
        family_key: familyKey || undefined,
        active: activeFilter === "all" ? undefined : activeFilter === "true",
        limit: PAGE_SIZE + 1,
        offset: page * PAGE_SIZE,
      }),
  });
  const visibleSources = sourcesQuery.data?.slice(0, PAGE_SIZE);
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
          Familia
          <NativeSelect
            value={familyKey}
            onChange={(event) => {
              setFamilyKey(event.target.value);
              setPage(0);
            }}
            className="w-44"
          >
            <option value="">Todas</option>
            {familiesQuery.data?.map((family) => (
              <option key={family.key} value={family.key}>
                {family.display_name}
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
          <table className={TABLE}>
            <thead>
              <tr className={THEAD_ROW}>
                <th className={TH}>Nombre</th>
                <th className={TH}>Familia</th>
                <th className={TH}>Estado</th>
                <th className={TH}>Acciones</th>
              </tr>
            </thead>
            <tbody>
              {visibleSources?.map((source) => (
                <SourceRow key={source.id} source={source} />
              ))}
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
