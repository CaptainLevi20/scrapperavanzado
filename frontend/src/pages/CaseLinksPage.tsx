import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { GitMerge } from "lucide-react";
import {
  confirmCaseLinkSuggestion,
  createManualCaseLink,
  dismissCaseLinkSuggestion,
  fetchCaseLinkSuggestions,
} from "../api/caseLinks";
import { fetchSources } from "../api/sources";
import type { CaseGroup } from "../api/types";
import { EmptyState } from "../components/EmptyState";
import { ErrorBanner } from "../components/ErrorBanner";
import { Button } from "../components/ui/button";
import { NativeSelect } from "../components/ui/native-select";
import { formatDate } from "../lib/formatters";

function CaseSide({ group }: { group: CaseGroup }) {
  return (
    <div>
      <p className="font-medium text-foreground">{group.source_name}</p>
      <p className="text-xs text-muted-foreground">
        {group.document_count} documento{group.document_count === 1 ? "" : "s"}
        {group.f_public_min && ` · ${formatDate(group.f_public_min)} – ${formatDate(group.f_public_max ?? group.f_public_min)}`}
      </p>
    </div>
  );
}

export function CaseLinksPage() {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [actionError, setActionError] = useState<string | null>(null);

  const suggestionsQuery = useQuery({
    queryKey: ["case-link-suggestions"],
    queryFn: fetchCaseLinkSuggestions,
  });

  const confirmMutation = useMutation({
    mutationFn: (suggestionId: number) => confirmCaseLinkSuggestion(suggestionId),
    onSuccess: (caseLink) => {
      queryClient.invalidateQueries({ queryKey: ["case-link-suggestions"] });
      navigate(`/casos-por-confirmar/expedientes/${caseLink.id}`);
    },
    onError: () => setActionError("No se pudo confirmar la sugerencia. Intenta de nuevo."),
  });

  const dismissMutation = useMutation({
    mutationFn: (suggestionId: number) => dismissCaseLinkSuggestion(suggestionId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["case-link-suggestions"] }),
    onError: () => setActionError("No se pudo descartar la sugerencia. Intenta de nuevo."),
  });

  return (
    <div className="space-y-6">
      <div>
        <p className="flex items-center gap-1.5 text-xs font-medium tracking-[0.18em] text-muted-foreground uppercase">
          <GitMerge className="size-3.5" aria-hidden="true" />
          Casos por confirmar
        </p>
        <h1 className="font-display text-3xl font-semibold tracking-tight text-foreground">
          ¿Es el mismo caso?
        </h1>
      </div>

      {suggestionsQuery.isError && (
        <ErrorBanner message="No se pudieron cargar las sugerencias." onRetry={() => suggestionsQuery.refetch()} />
      )}
      {actionError && <ErrorBanner message={actionError} />}

      {!suggestionsQuery.isLoading && (suggestionsQuery.data?.length ?? 0) === 0 && !suggestionsQuery.isError && (
        <EmptyState message="No hay casos pendientes por confirmar." />
      )}

      <div className="space-y-3">
        {suggestionsQuery.data?.map((suggestion) => (
          <div key={suggestion.id} className="rounded-lg border border-border bg-card p-4">
            <div className="flex items-center justify-between gap-4">
              <div className="grid flex-1 grid-cols-2 gap-4">
                <CaseSide group={suggestion.case_a} />
                <CaseSide group={suggestion.case_b} />
              </div>
              <div className="flex shrink-0 items-center gap-2">
                <span className="text-xs text-muted-foreground">{suggestion.matched_digits} dígitos en común</span>
                <Button
                  size="sm"
                  onClick={() => confirmMutation.mutate(suggestion.id)}
                  disabled={confirmMutation.isPending}
                >
                  Confirmar
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => dismissMutation.mutate(suggestion.id)}
                  disabled={dismissMutation.isPending}
                >
                  Descartar
                </Button>
              </div>
            </div>
          </div>
        ))}
      </div>

      <ManualLinkForm onError={setActionError} />
    </div>
  );
}

function ManualLinkForm({ onError }: { onError: (message: string | null) => void }) {
  const queryClient = useQueryClient();
  const [sourceIdA, setSourceIdA] = useState("");
  const [radicadoA, setRadicadoA] = useState("");
  const [sourceIdB, setSourceIdB] = useState("");
  const [radicadoB, setRadicadoB] = useState("");

  const sourcesQuery = useQuery({
    queryKey: ["sources"],
    queryFn: () => fetchSources(),
  });
  const samaiSources = sourcesQuery.data?.filter((source) => source.family_key === "samai") ?? [];

  const manualLinkMutation = useMutation({
    mutationFn: createManualCaseLink,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["case-link-suggestions"] });
      setSourceIdA("");
      setRadicadoA("");
      setSourceIdB("");
      setRadicadoB("");
      onError(null);
    },
    onError: () => onError("No se pudo vincular manualmente. Verifica los datos."),
  });

  function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    manualLinkMutation.mutate({
      source_id_a: Number(sourceIdA),
      radicado_a: radicadoA,
      source_id_b: Number(sourceIdB),
      radicado_b: radicadoB,
    });
  }

  return (
    <form onSubmit={handleSubmit} className="rounded-lg border border-dashed border-border p-4">
      <p className="mb-3 text-sm font-medium text-foreground">Vincular manualmente</p>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <NativeSelect
          aria-label="Fuente A"
          value={sourceIdA}
          onChange={(e) => setSourceIdA(e.target.value)}
        >
          <option value="">Fuente A</option>
          {samaiSources.map((source) => (
            <option key={source.id} value={String(source.id)}>
              {source.name}
            </option>
          ))}
        </NativeSelect>
        <input
          className="rounded-md border border-input px-2 py-1 text-sm"
          placeholder="Radicado A"
          value={radicadoA}
          onChange={(e) => setRadicadoA(e.target.value)}
        />
        <NativeSelect
          aria-label="Fuente B"
          value={sourceIdB}
          onChange={(e) => setSourceIdB(e.target.value)}
        >
          <option value="">Fuente B</option>
          {samaiSources.map((source) => (
            <option key={source.id} value={String(source.id)}>
              {source.name}
            </option>
          ))}
        </NativeSelect>
        <input
          className="rounded-md border border-input px-2 py-1 text-sm"
          placeholder="Radicado B"
          value={radicadoB}
          onChange={(e) => setRadicadoB(e.target.value)}
        />
      </div>
      <Button type="submit" size="sm" className="mt-3" disabled={manualLinkMutation.isPending}>
        Vincular
      </Button>
    </form>
  );
}
