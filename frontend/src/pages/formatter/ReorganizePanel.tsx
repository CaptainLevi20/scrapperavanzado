import { useState } from "react";
import { ApiError } from "../../api/client";
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
  | { step: "loaded"; analysis: BatchAnalysis; corrections: Map<string, Correction>; dismissed: Set<string> }
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
      setState({ step: "loaded", analysis, corrections: new Map(), dismissed: new Set() });
    } catch (error) {
      setState({ step: "error", message: error instanceof ApiError ? error.message : "No se pudo analizar la carpeta." });
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

  function handleToggleDismissed(currentPath: string) {
    if (state.step !== "loaded") return;
    const dismissed = new Set(state.dismissed);
    if (dismissed.has(currentPath)) {
      dismissed.delete(currentPath);
    } else {
      dismissed.add(currentPath);
    }
    setState({ ...state, dismissed });
  }

  async function handleApply() {
    if (state.step !== "loaded") return;
    const moves: ResolvedMove[] = [];
    for (const entry of state.analysis.exceptions) {
      if (state.dismissed.has(entry.current_path)) continue;
      const correction = state.corrections.get(entry.current_path) ?? initialCorrection(entry);
      const target = computeProposedPath(entry, correction);
      if (target) moves.push({ current_path: entry.current_path, target_path: target });
    }
    setState({ step: "applying" });
    try {
      // Send the root that was actually analyzed (and that these moves were
      // computed against), not the live textbox value — the admin may have
      // edited the path after analyzing but before applying.
      const result = await applyReorganization(state.analysis.root_path, moves);
      setState({ step: "applied", result });
    } catch (error) {
      setState({ step: "error", message: error instanceof ApiError ? error.message : "No se pudo aplicar la reorganización." });
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

      {state.step === "applied" &&
        (() => {
          const skipped = state.result.results.filter((r) => !r.moved);
          return (
            <div className="space-y-4">
              <p className="text-sm text-muted-foreground">
                {state.result.results.filter((r) => r.moved).length} archivo(s) movido(s), {skipped.length} omitido(s).
              </p>

              {skipped.length > 0 && (
                <div className={TABLE_SHELL}>
                  <div className={TABLE_SCROLL}>
                    <table className={TABLE}>
                      <thead>
                        <tr className={THEAD_ROW}>
                          <th className={TH}>Ruta actual</th>
                          <th className={TH}>Motivo</th>
                        </tr>
                      </thead>
                      <tbody>
                        {skipped.map((r) => (
                          <tr key={r.current_path} className={TBODY_ROW}>
                            <td className={TD}>{r.current_path}</td>
                            <td className={TD}>{r.skip_reason}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </div>
          );
        })()}

      {state.step === "loaded" &&
        (() => {
          const { analysis, corrections, dismissed } = state;
          const rows = analysis.exceptions.map((entry) => {
            const correction = corrections.get(entry.current_path) ?? initialCorrection(entry);
            const proposedPath = computeProposedPath(entry, correction);
            return { entry, correction, proposedPath, isDismissed: dismissed.has(entry.current_path) };
          });
          const activeRows = rows.filter((row) => !row.isDismissed);
          const canApply = activeRows.length > 0 && activeRows.every((row) => row.proposedPath !== null);

          return (
            <div className="space-y-4">
              <p className="text-sm text-muted-foreground">
                {analysis.total_files} archivo(s) analizados, {analysis.exceptions.length} excepción(es),{" "}
                {analysis.extra_depth_total} archivo(s) con profundidad extra (informativo).
                {analysis.extra_depth_total > analysis.extra_depth.length
                  ? ` (mostrando los primeros ${analysis.extra_depth.length}).`
                  : ""}
              </p>

              {analysis.tipos.length > 0 && (
                <div className={TABLE_SHELL}>
                  <div className={TABLE_SCROLL}>
                    <table className={TABLE}>
                      <thead>
                        <tr className={THEAD_ROW}>
                          <th className={TH}>Tipo</th>
                          <th className={TH}>Archivos totales</th>
                          <th className={TH}>Excepciones</th>
                        </tr>
                      </thead>
                      <tbody>
                        {analysis.tipos.map((tipoSummary) => (
                          <tr key={tipoSummary.tipo} className={TBODY_ROW}>
                            <td className={TD}>{tipoSummary.tipo}</td>
                            <td className={TD}>{tipoSummary.total_files}</td>
                            <td className={TD}>{tipoSummary.exception_count}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

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
                          <th className={TH}></th>
                        </tr>
                      </thead>
                      <tbody>
                        {rows.map(({ entry, correction, proposedPath, isDismissed }) => (
                          <tr key={entry.current_path} className={`${TBODY_ROW} ${isDismissed ? "opacity-50" : ""}`}>
                            <td className={TD}>{entry.tipo}</td>
                            <td className={TD}>{entry.current_path}</td>
                            <td className={TD}>
                              <Input
                                aria-label={`Entidad para ${entry.current_path}`}
                                value={correction.entity}
                                onChange={(event) =>
                                  handleCorrectionChange(entry.current_path, "entity", event.target.value)
                                }
                                disabled={isDismissed}
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
                                disabled={isDismissed}
                                className="w-24"
                              />
                              {!isDismissed && entry.detected_year === null && (
                                <p className="mt-1 text-xs text-destructive">
                                  Sin confirmar — revisa el documento
                                </p>
                              )}
                            </td>
                            <td className={TD}>{isDismissed ? "No se moverá" : (proposedPath ?? "—")}</td>
                            <td className={TD}>
                              {(entry.kind === "entity_mismatch" || entry.kind === "year_mismatch") && (
                                <Button
                                  type="button"
                                  variant="outline"
                                  size="xs"
                                  onClick={() => handleToggleDismissed(entry.current_path)}
                                >
                                  {isDismissed ? "Deshacer" : "Dejar así"}
                                </Button>
                              )}
                            </td>
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
