import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { fetchSourceFamilies } from "../api/sourceFamilies";
import { createSource, fetchSources, updateSource } from "../api/sources";
import { ApiError } from "../api/client";
import type { Source, SourceFamily } from "../api/types";
import { ErrorBanner } from "../components/ErrorBanner";
import { Button } from "../components/ui/button";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from "../components/ui/dialog";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";

const PAGE_SIZE = 20;

function NewSourceDialog({ families }: { families: SourceFamily[] }) {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [familyKey, setFamilyKey] = useState("");
  const [name, setName] = useState("");
  const [paramsText, setParamsText] = useState("{}");
  const [error, setError] = useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: createSource,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["sources"] });
      setOpen(false);
      setName("");
      setParamsText("{}");
      setError(null);
    },
    onError: (err: unknown) => {
      setError(err instanceof ApiError ? err.message : "Error al crear la fuente");
    },
  });

  function handleSubmit() {
    let familyParams: Record<string, unknown>;
    try {
      familyParams = JSON.parse(paramsText);
    } catch {
      setError("Los parámetros deben ser JSON válido");
      return;
    }
    mutation.mutate({ family_key: familyKey, name, family_params: familyParams, active: true });
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button>Nueva fuente</Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Nueva fuente</DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          <div>
            <Label htmlFor="new-source-family">Familia de la fuente</Label>
            <select
              id="new-source-family"
              value={familyKey}
              onChange={(event) => setFamilyKey(event.target.value)}
              className="w-full rounded border px-2 py-1"
            >
              <option value="">Selecciona una familia</option>
              {families.map((family) => (
                <option key={family.key} value={family.key}>
                  {family.display_name}
                </option>
              ))}
            </select>
          </div>
          <div>
            <Label htmlFor="new-source-name">Nombre</Label>
            <Input id="new-source-name" value={name} onChange={(event) => setName(event.target.value)} />
          </div>
          <div>
            <Label htmlFor="new-source-params">Parámetros (JSON)</Label>
            <textarea
              id="new-source-params"
              value={paramsText}
              onChange={(event) => setParamsText(event.target.value)}
              className="w-full rounded border px-2 py-1 font-mono text-sm"
              rows={4}
            />
          </div>
          {error && <p className="text-sm text-red-600">{error}</p>}
        </div>
        <DialogFooter>
          <Button onClick={handleSubmit} disabled={!familyKey || !name || mutation.isPending}>
            {mutation.isPending ? "Creando…" : "Crear"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function EditParamsDialog({ source }: { source: Source }) {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [paramsText, setParamsText] = useState(() => JSON.stringify(source.family_params, null, 2));
  const [error, setError] = useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: (family_params: Record<string, unknown>) => updateSource(source.id, { family_params }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["sources"] });
      setOpen(false);
      setError(null);
    },
    onError: (err: unknown) => {
      setError(err instanceof ApiError ? err.message : "Error al actualizar la fuente");
    },
  });

  function handleSubmit() {
    let familyParams: Record<string, unknown>;
    try {
      familyParams = JSON.parse(paramsText);
    } catch {
      setError("Los parámetros deben ser JSON válido");
      return;
    }
    mutation.mutate(familyParams);
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(nextOpen) => {
        setOpen(nextOpen);
        if (nextOpen) {
          setParamsText(JSON.stringify(source.family_params, null, 2));
          setError(null);
        }
      }}
    >
      <DialogTrigger asChild>
        <button className="text-sm text-blue-600 underline">Editar parámetros</button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Editar parámetros</DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          <div>
            <Label htmlFor={`edit-params-${source.id}`}>Parámetros (JSON)</Label>
            <textarea
              id={`edit-params-${source.id}`}
              value={paramsText}
              onChange={(event) => setParamsText(event.target.value)}
              className="w-full rounded border px-2 py-1 font-mono text-sm"
              rows={4}
            />
          </div>
          {error && <p className="text-sm text-red-600">{error}</p>}
        </div>
        <DialogFooter>
          <Button onClick={handleSubmit} disabled={mutation.isPending}>
            {mutation.isPending ? "Guardando…" : "Guardar"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function SourceRow({ source }: { source: Source }) {
  const queryClient = useQueryClient();
  const toggleMutation = useMutation({
    mutationFn: () => updateSource(source.id, { active: !source.active }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["sources"] }),
  });

  return (
    <tr className="border-b">
      <td className="py-2">{source.name}</td>
      <td className="py-2">{source.family_key}</td>
      <td className="py-2">{source.active ? "Activa" : "Inactiva"}</td>
      <td className="py-2 flex items-center gap-3">
        <button onClick={() => toggleMutation.mutate()} className="text-sm text-blue-600 underline" disabled={toggleMutation.isPending}>
          {source.active ? "Desactivar" : "Activar"}
        </button>
        <EditParamsDialog source={source} />
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
      fetchSources({
        family_key: familyKey || undefined,
        active: activeFilter === "all" ? undefined : activeFilter === "true",
        limit: PAGE_SIZE,
        offset: page * PAGE_SIZE,
      }),
  });

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Fuentes</h1>
        <NewSourceDialog families={familiesQuery.data ?? []} />
      </div>

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
            <th className="py-2">Acciones</th>
          </tr>
        </thead>
        <tbody>
          {sourcesQuery.data?.map((source) => (
            <SourceRow key={source.id} source={source} />
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
