import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { createRun, fetchRuns } from "../api/runs";
import { fetchSources } from "../api/sources";
import type { Source } from "../api/types";
import { ErrorBanner } from "../components/ErrorBanner";
import { StatusBadge } from "../components/StatusBadge";
import { Button } from "../components/ui/button";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from "../components/ui/dialog";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { formatDateTime } from "../lib/formatters";

const PAGE_SIZE = 20;
const POLL_INTERVAL_MS = 4000;

function NewRunDialog({ sources }: { sources: Source[] }) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [selectedIds, setSelectedIds] = useState<number[]>([]);
  const [fini, setFini] = useState("");
  const [ffin, setFfin] = useState("");

  const mutation = useMutation({
    mutationFn: createRun,
    onSuccess: (run) => {
      queryClient.invalidateQueries({ queryKey: ["runs"] });
      setOpen(false);
      navigate(`/runs/${run.id}`);
    },
  });

  function toggleSource(id: number) {
    setSelectedIds((prev) => (prev.includes(id) ? prev.filter((existing) => existing !== id) : [...prev, id]));
  }

  function handleSubmit() {
    mutation.mutate({
      source_ids: selectedIds.length > 0 ? selectedIds : undefined,
      fini: fini || undefined,
      ffin: ffin || undefined,
    });
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button>Nuevo run</Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Nuevo run</DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          <div>
            <Label>Fuentes (vacío = todas las activas)</Label>
            <div className="max-h-40 space-y-1 overflow-y-auto rounded border p-2">
              {sources.map((source) => (
                <label key={source.id} className="flex items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    aria-label={source.name}
                    checked={selectedIds.includes(source.id)}
                    onChange={() => toggleSource(source.id)}
                  />
                  {source.name}
                </label>
              ))}
            </div>
          </div>
          <div className="flex gap-2">
            <div>
              <Label htmlFor="run-fini">Desde</Label>
              <Input id="run-fini" type="date" value={fini} onChange={(event) => setFini(event.target.value)} />
            </div>
            <div>
              <Label htmlFor="run-ffin">Hasta</Label>
              <Input id="run-ffin" type="date" value={ffin} onChange={(event) => setFfin(event.target.value)} />
            </div>
          </div>
        </div>
        <DialogFooter>
          <Button onClick={handleSubmit} disabled={mutation.isPending}>
            {mutation.isPending ? "Creando…" : "Iniciar run"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export function RunsPage() {
  const [statusFilter, setStatusFilter] = useState("");
  const [page, setPage] = useState(0);

  const activeSourcesQuery = useQuery({
    queryKey: ["sources", "active-for-new-run"],
    queryFn: () => fetchSources({ active: true, limit: 100 }),
  });

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
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Runs</h1>
        <NewRunDialog sources={activeSourcesQuery.data ?? []} />
      </div>

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
