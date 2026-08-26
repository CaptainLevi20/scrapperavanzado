import { useState } from "react";
import { ApiError } from "../../api/client";
import { analyzeReorganization, applyReorganization } from "../../api/reorganize";
import type { ApplyResult, BatchAnalysis, ResolvedFolderRename, ResolvedMove } from "../../api/types";
import { ErrorBanner } from "../../components/ErrorBanner";
import { Button } from "../../components/ui/button";
import { Input } from "../../components/ui/input";
import {
  computeFolderRenameTarget,
  computeProposedPath,
  initialCorrection,
  isConfidentException,
  type Correction,
} from "../../lib/reorganize/proposePath";
import { TABLE, TABLE_SCROLL, TABLE_SHELL, TBODY_ROW, TD, TH, THEAD_ROW } from "../../lib/tableStyles";

// Full file/folder paths can be long — wrap them instead of letting them
// force the table wider than the viewport, which would push the Aprobar
// button out past a horizontal scrollbar.
const TD_PATH = `${TD} max-w-xs break-words`;

type ReorganizeState =
  | { step: "idle" }
  | { step: "loading" }
  | { step: "error"; message: string }
  | {
      step: "loaded";
      analysis: BatchAnalysis;
      corrections: Map<string, Correction>;
      folderRenameCorrections: Map<string, string>;
      // Opt-in: a row only counts toward Aplicar once explicitly approved —
      // there is no "everything applies unless you opt out" default.
      approved: Set<string>;
    }
  | { step: "applying" }
  | { step: "applied"; result: ApplyResult };

export function ReorganizePanel() {
  const [rootPath, setRootPath] = useState("");
  const [state, setState] = useState<ReorganizeState>({ step: "idle" });

  async function handleAnalyze() {
    setState({ step: "loading" });
    try {
      const analysis = await analyzeReorganization(rootPath);
      // Pre-approve exceptions that don't need a human decision — the missing
      // piece was read confidently from the filename itself, and it isn't an
      // entity_mismatch (the folder and filename actively disagreeing is
      // always a judgment call). Folder renames are pre-approved too: the
      // backend only ever suggests one once a strict majority of that
      // folder's own files already agree on the alternate entity, so by the
      // time it reaches the UI it has already cleared a real confidence bar.
      const approved = new Set([
        ...analysis.exceptions.filter(isConfidentException).map((entry) => entry.current_path),
        ...analysis.folder_renames.map((fr) => fr.current_path),
      ]);
      setState({
        step: "loaded",
        analysis,
        corrections: new Map(),
        folderRenameCorrections: new Map(),
        approved,
      });
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

  function handleFolderRenameChange(currentPath: string, value: string) {
    if (state.step !== "loaded") return;
    const folderRenameCorrections = new Map(state.folderRenameCorrections);
    folderRenameCorrections.set(currentPath, value);
    setState({ ...state, folderRenameCorrections });
  }

  function handleToggleApproved(currentPath: string) {
    if (state.step !== "loaded") return;
    const approved = new Set(state.approved);
    if (approved.has(currentPath)) {
      approved.delete(currentPath);
    } else {
      approved.add(currentPath);
    }
    setState({ ...state, approved });
  }

  async function handleApply() {
    if (state.step !== "loaded") return;
    const moves: ResolvedMove[] = [];
    for (const entry of state.analysis.exceptions) {
      if (!state.approved.has(entry.current_path)) continue;
      const correction = state.corrections.get(entry.current_path) ?? initialCorrection(entry);
      const target = computeProposedPath(entry, correction);
      if (target) moves.push({ current_path: entry.current_path, target_path: target });
    }
    const folderRenames: ResolvedFolderRename[] = [];
    for (const fr of state.analysis.folder_renames) {
      if (!state.approved.has(fr.current_path)) continue;
      const entityName = state.folderRenameCorrections.get(fr.current_path) ?? fr.suggested_entity;
      const target = computeFolderRenameTarget(fr.tipo, entityName);
      if (target) folderRenames.push({ current_path: fr.current_path, target_path: target });
    }
    setState({ step: "applying" });
    try {
      // Send the root that was actually analyzed (and that these moves were
      // computed against), not the live textbox value — the admin may have
      // edited the path after analyzing but before applying.
      const result = await applyReorganization(state.analysis.root_path, moves, folderRenames);
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
          const skippedRenames = state.result.folder_rename_results.filter((r) => !r.renamed);
          return (
            <div className="space-y-4">
              <p className="text-sm text-muted-foreground">
                {state.result.folder_rename_results.filter((r) => r.renamed).length} carpeta(s) renombrada(s),{" "}
                {skippedRenames.length} carpeta(s) omitida(s).{" "}
                {state.result.results.filter((r) => r.moved).length} archivo(s) movido(s), {skipped.length} omitido(s).
              </p>

              {skippedRenames.length > 0 && (
                <div className={TABLE_SHELL}>
                  <div className={TABLE_SCROLL}>
                    <table className={TABLE}>
                      <thead>
                        <tr className={THEAD_ROW}>
                          <th className={TH}>Carpeta actual</th>
                          <th className={TH}>Motivo</th>
                        </tr>
                      </thead>
                      <tbody>
                        {skippedRenames.map((r) => (
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
          const { analysis, corrections, folderRenameCorrections, approved } = state;
          const rows = analysis.exceptions.map((entry) => {
            const correction = corrections.get(entry.current_path) ?? initialCorrection(entry);
            const proposedPath = computeProposedPath(entry, correction);
            return { entry, correction, proposedPath, isApproved: approved.has(entry.current_path) };
          });
          const autoRows = rows.filter((row) => isConfidentException(row.entry));
          const reviewRows = rows.filter((row) => !isConfidentException(row.entry));
          const renameRows = analysis.folder_renames.map((fr) => {
            const entityName = folderRenameCorrections.get(fr.current_path) ?? fr.suggested_entity;
            const proposedPath = computeFolderRenameTarget(fr.tipo, entityName);
            return { fr, entityName, proposedPath, isApproved: approved.has(fr.current_path) };
          });
          const approvedRows = rows.filter((row) => row.isApproved);
          const approvedRenameRows = renameRows.filter((row) => row.isApproved);
          const canApply =
            approvedRows.length + approvedRenameRows.length > 0 &&
            approvedRows.every((row) => row.proposedPath !== null) &&
            approvedRenameRows.every((row) => row.proposedPath !== null);

          return (
            <div className="space-y-4">
              <p className="text-sm text-muted-foreground">
                {analysis.total_files} archivo(s) analizados, {analysis.exceptions.length} excepción(es)
                {autoRows.length > 0 ? ` (${autoRows.length} resuelta(s) automáticamente)` : ""},{" "}
                {renameRows.length} carpeta(s) para renombrar
                {renameRows.length > 0 ? " (aprobadas automáticamente)" : ""},{" "}
                {analysis.extra_depth_total} archivo(s) con profundidad extra (informativo, no se modifican).
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

              {reviewRows.length > 0 && (
                <div className="space-y-2">
                  <p className="text-sm font-medium text-foreground">
                    Requieren tu revisión (la carpeta y el nombre del archivo no coinciden)
                  </p>
                  <div className={TABLE_SHELL}>
                    <div className={TABLE_SCROLL}>
                      <table className={TABLE}>
                        <thead>
                          <tr className={THEAD_ROW}>
                            <th className={TH}></th>
                            <th className={TH}>Tipo</th>
                            <th className={TH}>Ruta actual</th>
                            <th className={TH}>Entidad</th>
                            <th className={TH}>Año</th>
                            <th className={TH}>Ruta propuesta</th>
                          </tr>
                        </thead>
                        <tbody>
                          {reviewRows.map(({ entry, correction, proposedPath, isApproved }) => (
                            <tr key={entry.current_path} className={`${TBODY_ROW} ${isApproved ? "bg-primary/5" : ""}`}>
                              <td className={TD}>
                                <Button
                                  type="button"
                                  variant={isApproved ? "secondary" : "outline"}
                                  size="xs"
                                  onClick={() => handleToggleApproved(entry.current_path)}
                                >
                                  {isApproved ? "Deshacer" : "Aprobar"}
                                </Button>
                              </td>
                              <td className={TD}>{entry.tipo}</td>
                              <td className={TD_PATH}>{entry.current_path}</td>
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
                                {entry.detected_year === null && (
                                  <p className="mt-1 text-xs text-destructive">
                                    Sin confirmar — revisa el documento
                                  </p>
                                )}
                              </td>
                              <td className={TD_PATH}>{proposedPath ?? "—"}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                </div>
              )}

              {renameRows.length > 0 && (
                <details className="space-y-2">
                  <summary className="cursor-pointer text-sm font-medium text-foreground">
                    {renameRows.length} carpeta(s) para renombrar (una mayoría clara de sus archivos coincide en otra
                    entidad — no necesitan tu aprobación, pero puedes revisarlas o deshacerlas aquí)
                  </summary>
                  <div className={TABLE_SHELL}>
                    <div className={TABLE_SCROLL}>
                      <table className={TABLE}>
                        <thead>
                          <tr className={THEAD_ROW}>
                            <th className={TH}></th>
                            <th className={TH}>Tipo</th>
                            <th className={TH}>Carpeta actual</th>
                            <th className={TH}>Nueva entidad</th>
                            <th className={TH}>Archivos afectados</th>
                            <th className={TH}>Carpeta propuesta</th>
                          </tr>
                        </thead>
                        <tbody>
                          {renameRows.map(({ fr, entityName, proposedPath, isApproved }) => (
                            <tr key={fr.current_path} className={`${TBODY_ROW} ${isApproved ? "bg-primary/5" : ""}`}>
                              <td className={TD}>
                                <Button
                                  type="button"
                                  variant={isApproved ? "secondary" : "outline"}
                                  size="xs"
                                  onClick={() => handleToggleApproved(fr.current_path)}
                                >
                                  {isApproved ? "Deshacer" : "Aprobar"}
                                </Button>
                              </td>
                              <td className={TD}>{fr.tipo}</td>
                              <td className={TD_PATH}>{fr.current_path}</td>
                              <td className={TD}>
                                <Input
                                  aria-label={`Nueva entidad para ${fr.current_path}`}
                                  value={entityName}
                                  onChange={(event) => handleFolderRenameChange(fr.current_path, event.target.value)}
                                  className="w-28"
                                />
                              </td>
                              <td className={TD}>{fr.file_count}</td>
                              <td className={TD_PATH}>{proposedPath ?? "—"}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                </details>
              )}

              {autoRows.length > 0 && (
                <details className="space-y-2">
                  <summary className="cursor-pointer text-sm font-medium text-foreground">
                    {autoRows.length} resuelto(s) automáticamente (entidad y año ya coincidían con el nombre del
                    archivo — no necesitan tu aprobación, pero puedes revisarlos o deshacerlos aquí)
                  </summary>
                  <div className={TABLE_SHELL}>
                    <div className={TABLE_SCROLL}>
                      <table className={TABLE}>
                        <thead>
                          <tr className={THEAD_ROW}>
                            <th className={TH}></th>
                            <th className={TH}>Tipo</th>
                            <th className={TH}>Ruta actual</th>
                            <th className={TH}>Entidad</th>
                            <th className={TH}>Año</th>
                            <th className={TH}>Ruta propuesta</th>
                          </tr>
                        </thead>
                        <tbody>
                          {autoRows.map(({ entry, correction, proposedPath, isApproved }) => (
                            <tr key={entry.current_path} className={`${TBODY_ROW} ${isApproved ? "bg-primary/5" : ""}`}>
                              <td className={TD}>
                                <Button
                                  type="button"
                                  variant={isApproved ? "secondary" : "outline"}
                                  size="xs"
                                  onClick={() => handleToggleApproved(entry.current_path)}
                                >
                                  {isApproved ? "Deshacer" : "Aprobar"}
                                </Button>
                              </td>
                              <td className={TD}>{entry.tipo}</td>
                              <td className={TD_PATH}>{entry.current_path}</td>
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
                              <td className={TD_PATH}>{proposedPath ?? "—"}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                </details>
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
