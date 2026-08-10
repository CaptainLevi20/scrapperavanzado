import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";
import { PlayCircle } from "lucide-react";
import { createRun, fetchRuns } from "../api/runs";
import { fetchSourceFamilies } from "../api/sourceFamilies";
import { fetchAllActiveSources } from "../api/sources";
import type { Source } from "../api/types";
import { EmptyState } from "../components/EmptyState";
import { ErrorBanner } from "../components/ErrorBanner";
import { StatusBadge } from "../components/StatusBadge";
import { TableRowsSkeleton } from "../components/TableSkeleton";
import { Button } from "../components/ui/button";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from "../components/ui/dialog";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { NativeSelect } from "../components/ui/native-select";
import { TABLE, TABLE_SCROLL, TABLE_SHELL, TBODY_ROW, TD, TD_MONO, TH, THEAD_ROW } from "../lib/tableStyles";
import { formatDate, formatDateTime } from "../lib/formatters";
import { isStaleRun, shouldPollRun } from "../lib/runStatus";

const PAGE_SIZE = 20;
const POLL_INTERVAL_MS = 4000;

function NewRunDialog({ sources }: { sources: Source[] }) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [selectedIds, setSelectedIds] = useState<number[]>([]);
  const [fini, setFini] = useState("");
  const [ffin, setFfin] = useState("");

  const familiesQuery = useQuery({ queryKey: ["source-families"], queryFn: fetchSourceFamilies });
  const filtersByPublicationDateByFamily = useMemo(
    () => new Map((familiesQuery.data ?? []).map((family) => [family.key, family.filters_by_publication_date])),
    [familiesQuery.data]
  );

  function dateFieldLabelFor(source: Source): string {
    return filtersByPublicationDateByFamily.get(source.family_key) ? "fecha de publicación" : "fecha de providencia";
  }

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
          <DialogTitle className="font-display">Nuevo run</DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          <div className="space-y-1.5">
            <Label>Fuentes (vacío = todas las activas)</Label>
            <div className="max-h-40 space-y-0.5 overflow-y-auto rounded-md border-[1.5px] border-input bg-card p-2">
              {sources.map((source) => (
                <label
                  key={source.id}
                  className="flex items-center justify-between gap-2 rounded px-1.5 py-1 text-sm hover:bg-secondary/60"
                >
                  <span className="flex items-center gap-2">
                    <input
                      type="checkbox"
                      aria-label={source.name}
                      checked={selectedIds.includes(source.id)}
                      onChange={() => toggleSource(source.id)}
                      className="size-4 accent-sello"
                    />
                    {source.name}
                  </span>
                  <span className="text-xs text-muted-foreground">Filtra por {dateFieldLabelFor(source)}</span>
                </label>
              ))}
            </div>
          </div>
          <div className="flex gap-2">
            <div className="space-y-1.5">
              <Label htmlFor="run-fini">Desde</Label>
              <Input id="run-fini" type="date" value={fini} onChange={(event) => setFini(event.target.value)} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="run-ffin">Hasta</Label>
              <Input id="run-ffin" type="date" value={ffin} onChange={(event) => setFfin(event.target.value)} />
            </div>
          </div>
          <p className="text-xs text-muted-foreground">
            El rango "Desde"/"Hasta" se aplica según el criterio de cada fuente, indicado arriba.
          </p>
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
    queryFn: fetchAllActiveSources,
  });

  const runsQuery = useQuery({
    queryKey: ["runs", statusFilter, page],
    queryFn: () =>
      // Asks for one extra row beyond the page size — the backend has no total
      // count to compare against (unlike /documents), so this is how "Siguiente"
      // knows whether there's really another page instead of just guessing from
      // whether the current page happened to come back full.
      fetchRuns({
        status_filter: statusFilter || undefined,
        limit: PAGE_SIZE + 1,
        offset: page * PAGE_SIZE,
      }),
    refetchInterval: (query) => {
      const data = query.state.data;
      const hasPollableRun = data?.some((run) => shouldPollRun(run.created_at, run.status));
      return hasPollableRun ? POLL_INTERVAL_MS : false;
    },
  });
  const visibleRuns = runsQuery.data?.slice(0, PAGE_SIZE);
  const hasNextPage = (runsQuery.data?.length ?? 0) > PAGE_SIZE;
  const hasStaleRun = visibleRuns?.some((run) => isStaleRun(run.created_at, run.status));

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <p className="flex items-center gap-1.5 text-xs font-medium tracking-[0.18em] text-muted-foreground uppercase">
            <PlayCircle className="size-3.5" aria-hidden="true" />
            Bitácora de corridas
          </p>
          <h1 className="font-display text-3xl font-semibold tracking-tight text-foreground">Runs</h1>
        </div>
        <NewRunDialog sources={activeSourcesQuery.data ?? []} />
      </div>

      <label className="flex items-center gap-2 text-sm text-muted-foreground">
        Estado
        <NativeSelect
          aria-label="Estado del run"
          value={statusFilter}
          onChange={(event) => {
            setStatusFilter(event.target.value);
            setPage(0);
          }}
          className="w-40"
        >
          <option value="">Todos</option>
          <option value="pending">Pendiente</option>
          <option value="running">En curso</option>
          <option value="completed">Completado</option>
          <option value="failed">Fallido</option>
          <option value="cancelled">Cancelado</option>
        </NativeSelect>
      </label>

      {runsQuery.isError && (
        <ErrorBanner message="No se pudieron cargar los runs." onRetry={() => runsQuery.refetch()} />
      )}
      {!runsQuery.isError && hasStaleRun && (
        <ErrorBanner
          message="Alguno de estos runs lleva mucho tiempo sin actualizarse. Puede haberse quedado colgado — usa Reintentar para revisar su estado más reciente."
          onRetry={() => runsQuery.refetch()}
        />
      )}

      <div className={TABLE_SHELL}>
        <div className={TABLE_SCROLL}>
          <table className={TABLE} aria-busy={runsQuery.isLoading}>
            <thead>
              <tr className={THEAD_ROW}>
                <th className={TH}>ID</th>
                <th className={TH}>Disparado por</th>
                <th className={TH}>Estado</th>
                <th className={TH}>Desde</th>
                <th className={TH}>Hasta</th>
                <th className={TH}>Creado</th>
              </tr>
            </thead>
            <tbody>
              {runsQuery.isLoading ? (
                <TableRowsSkeleton rows={6} columns={6} widths={["w-10", "w-24", "w-20", "w-20", "w-20", "w-28"]} />
              ) : (
                visibleRuns?.map((run) => (
                <tr key={run.id} className={TBODY_ROW}>
                  <td className={TD_MONO}>
                    <Link to={`/runs/${run.id}`} className="font-semibold text-sello-ink hover:underline">
                      #{run.id}
                    </Link>
                  </td>
                  <td className={TD}>{run.triggered_by}</td>
                  <td className={TD}>
                    <StatusBadge status={run.status} />
                  </td>
                  <td className={TD_MONO}>{formatDate(run.fini)}</td>
                  <td className={TD_MONO}>{formatDate(run.ffin)}</td>
                  <td className={TD_MONO}>{formatDateTime(run.created_at)}</td>
                </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
        {!runsQuery.isLoading && (visibleRuns?.length ?? 0) === 0 && (
          <EmptyState message="No hay runs que coincidan con este filtro." />
        )}
      </div>

      <div className="flex justify-end gap-2">
        <Button variant="outline" size="sm" disabled={page === 0} onClick={() => setPage((current) => current - 1)}>
          Anterior
        </Button>
        <Button variant="outline" size="sm" disabled={!hasNextPage} onClick={() => setPage((current) => current + 1)}>
          Siguiente
        </Button>
      </div>
    </div>
  );
}
