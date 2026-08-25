import { useState } from "react";
import { analyzeReorganization, applyReorganization } from "../../api/reorganize";
import type { ApplyResult, BatchAnalysis, ReorganizeException, ResolvedMove } from "../../api/types";
import { ErrorBanner } from "../../components/ErrorBanner";
import { Button } from "../../components/ui/button";
import { Input } from "../../components/ui/input";
import { computeProposedPath, type Correction } from "../../lib/reorganize/proposePath";
import { TABLE, TABLE_SCROLL, TABLE_SHELL, TBODY_ROW, TD, TH, THEAD_ROW } from "../../lib/tableStyles";

type ReorganizeState =
  | { step: "idle" }
  | { step: "loading" }
  | { step: "error"; message: string }
  | { step: "loaded"; analysis: BatchAnalysis; corrections: Map<string, Correction> }
  | { step: "applying" }
  | { step: "applied"; result: ApplyResult };

function initialCorrection(entry: ReorganizeException): Correction {
  const year = entry.detected_year ?? entry.mtime_year_hint;
  return { entity: entry.detected_entity ?? "", year: year !== null ? String(year) : "" };
}

export function ReorganizePanel() {
  const [rootPath, setRootPath] = useState("");
  const [state, setState] = useState<ReorganizeState>({ step: "idle" });

  async function handleAnalyze() {
    setState({ step: "loading" });
    try {
      const analysis = await analyzeReorganization(rootPath);
      setState({ step: "loaded", analysis, corrections: new Map() });
    } catch {
      setState({ step: "error", message: "No se pudo analizar la carpeta." });
    }
  }

  function handleCorrectionChange(currentPath: string, field: keyof Correction, value: string) {
    if (state.step !== "loaded") return;
    const entry = state.analysis.exceptions.find((e) => e.current_path === currentPath);
    if (!entry) return;
    const corrections = new Map(state.corrections);
    const current = corrections.get(currentPath) ?? initialCorrection(entry);
    corrections.set(currentPath, { ...current, [field]: value });
    setState({ ...state, corrections });
  }

  async function handleApply() {
    if (state.step !== "loaded") return;
    const moves: ResolvedMove[] = [];
    for (const entry of state.analysis.exceptions) {
      const correction = state.corrections.get(entry.current_path) ?? initialCorrection(entry);
      const target = computeProposedPath(entry, correction);
      if (target) moves.push({ current_path: entry.current_path, target_path: target });
    }
    setState({ step: "applying" });
    try {
      const result = await applyReorganization(rootPath, moves);
      setState({ step: "applied", result });
    } catch {
      setState({ step: "error", message: "No se pudo aplicar la reorganización." });
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex items-end gap-2">
        <div className="flex-1 space-y-1">
          <label htmlFor="reorganize-root-path" className="text-sm font-medium text-foreground">
            Ruta de la carpeta
          </label>
          <Input
            id="reorganize-root-path"
            value={rootPath}
            onChange={(event) => setRootPath(event.target.value)}
            placeholder="D:\LOTE 2"
          />
        </div>
        <Button onClick={() => void handleAnalyze()} disabled={!rootPath || state.step === "loading"}>
          Analizar
        </Button>
      </div>

      {state.step === "error" && <ErrorBanner message={state.message} onRetry={() => setState({ step: "idle" })} />}
      {state.step === "loading" && <p className="text-sm text-muted-foreground">Analizando…</p>}
      {state.step === "applying" && <p className="text-sm text-muted-foreground">Aplicando…</p>}

      {state.step === "applied" && (
        <p className="text-sm text-muted-foreground">
          {state.result.results.filter((r) => r.moved).length} archivo(s) movido(s),{" "}
          {state.result.results.filter((r) => !r.moved).length} omitido(s).
        </p>
      )}

      {state.step === "loaded" &&
        (() => {
          const { analysis, corrections } = state;
          const rows = analysis.exceptions.map((entry) => {
            const correction = corrections.get(entry.current_path) ?? initialCorrection(entry);
            const proposedPath = computeProposedPath(entry, correction);
            return { entry, correction, proposedPath };
          });
          const canApply = rows.length > 0 && rows.every((row) => row.proposedPath !== null);

          return (
            <div className="space-y-4">
              <p className="text-sm text-muted-foreground">
                {analysis.total_files} archivo(s) analizados, {analysis.exceptions.length} excepción(es),{" "}
                {analysis.extra_depth.length} carpeta(s) con profundidad extra (informativo).
              </p>

              {rows.length > 0 && (
                <div className={TABLE_SHELL}>
                  <div className={TABLE_SCROLL}>
                    <table className={TABLE}>
                      <thead>
                        <tr className={THEAD_ROW}>
                          <th className={TH}>Tipo</th>
                          <th className={TH}>Ruta actual</th>
                          <th className={TH}>Entidad</th>
                          <th className={TH}>Año</th>
                          <th className={TH}>Ruta propuesta</th>
                        </tr>
                      </thead>
                      <tbody>
                        {rows.map(({ entry, correction, proposedPath }) => (
                          <tr key={entry.current_path} className={TBODY_ROW}>
                            <td className={TD}>{entry.tipo}</td>
                            <td className={TD}>{entry.current_path}</td>
                            <td className={TD}>
                              <Input
                                aria-label={`Entidad para ${entry.current_path}`}
                                value={correction.entity}
                                onChange={(event) =>
                                  handleCorrectionChange(entry.current_path, "entity", event.target.value)
                                }
                                className="w-28"
                              />
                            </td>
                            <td className={TD}>
                              <Input
                                aria-label={`Año para ${entry.current_path}`}
                                value={correction.year}
                                onChange={(event) =>
                                  handleCorrectionChange(entry.current_path, "year", event.target.value)
                                }
                                className="w-24"
                              />
                            </td>
                            <td className={TD}>{proposedPath ?? "—"}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              {analysis.extra_depth.length > 0 && (
                <div className={TABLE_SHELL}>
                  <div className={TABLE_SCROLL}>
                    <table className={TABLE}>
                      <thead>
                        <tr className={THEAD_ROW}>
                          <th className={TH}>Tipo</th>
                          <th className={TH}>Ruta (no se modifica)</th>
                        </tr>
                      </thead>
                      <tbody>
                        {analysis.extra_depth.map((item) => (
                          <tr key={item.current_path} className={TBODY_ROW}>
                            <td className={TD}>{item.tipo}</td>
                            <td className={TD}>{item.current_path}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              <Button onClick={() => void handleApply()} disabled={!canApply}>
                Aplicar
              </Button>
            </div>
          );
        })()}
    </div>
  );
}
