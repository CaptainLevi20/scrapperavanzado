import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchSourceFamilies } from "../api/sourceFamilies";
import { fetchSources } from "../api/sources";
import { ErrorBanner } from "../components/ErrorBanner";

const PAGE_SIZE = 20;

export function SourcesPage() {
  const [familyKey, setFamilyKey] = useState("");
  const [activeFilter, setActiveFilter] = useState("all");
  const [page, setPage] = useState(0);

  const familiesQuery = useQuery({ queryKey: ["source-families"], queryFn: fetchSourceFamilies });

  const sourcesQuery = useQuery({
    queryKey: ["sources", familyKey, activeFilter, page],
    queryFn: () =>
      fetchSources({
        family_key: familyKey || undefined,
        active: activeFilter === "all" ? undefined : activeFilter === "true",
        limit: PAGE_SIZE,
        offset: page * PAGE_SIZE,
      }),
  });

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold">Fuentes</h1>

      <div className="flex gap-3">
        <label className="flex items-center gap-2 text-sm">
          Familia
          <select
            value={familyKey}
            onChange={(event) => {
              setFamilyKey(event.target.value);
              setPage(0);
            }}
            className="rounded border px-2 py-1"
          >
            <option value="">Todas</option>
            {familiesQuery.data?.map((family) => (
              <option key={family.key} value={family.key}>
                {family.display_name}
              </option>
            ))}
          </select>
        </label>
        <label className="flex items-center gap-2 text-sm">
          Estado
          <select
            aria-label="Estado"
            value={activeFilter}
            onChange={(event) => {
              setActiveFilter(event.target.value);
              setPage(0);
            }}
            className="rounded border px-2 py-1"
          >
            <option value="all">Todas</option>
            <option value="true">Activas</option>
            <option value="false">Inactivas</option>
          </select>
        </label>
      </div>

      {sourcesQuery.isError && (
        <ErrorBanner message="No se pudieron cargar las fuentes." onRetry={() => sourcesQuery.refetch()} />
      )}

      <table className="w-full border-collapse text-left">
        <thead>
          <tr className="border-b">
            <th className="py-2">Nombre</th>
            <th className="py-2">Familia</th>
            <th className="py-2">Estado</th>
          </tr>
        </thead>
        <tbody>
          {sourcesQuery.data?.map((source) => (
            <tr key={source.id} className="border-b">
              <td className="py-2">{source.name}</td>
              <td className="py-2">{source.family_key}</td>
              <td className="py-2">{source.active ? "Activa" : "Inactiva"}</td>
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
          disabled={(sourcesQuery.data?.length ?? 0) < PAGE_SIZE}
          onClick={() => setPage((current) => current + 1)}
          className="rounded border px-3 py-1 disabled:opacity-50"
        >
          Siguiente
        </button>
      </div>
    </div>
  );
}
