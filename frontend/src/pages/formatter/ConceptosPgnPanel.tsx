import { useEffect, useState } from "react";
import { ErrorBanner } from "../../components/ErrorBanner";
import { Button } from "../../components/ui/button";
import { Input } from "../../components/ui/input";
import {
  analyzeConceptBatch,
  applyManualFixes,
  ConceptPgnError,
  isAlreadyFinal,
  isRenamable,
  type ConceptEntry,
  type ConceptPlan,
  type ManualFix,
  type ReviewReason,
} from "../../lib/conceptosPgn/analyze";
import { renameConcepts, type RenameSummary } from "../../lib/conceptosPgn/renameInPlace";
import { TABLE, TABLE_SCROLL, TABLE_SHELL, TBODY_ROW, TD, TH, THEAD_ROW } from "../../lib/tableStyles";

type PanelState =
  | { step: "idle" }
  | { step: "unsupported" }
  | { step: "error"; message: string }
  | { step: "loaded"; plan: ConceptPlan; fixes: Map<string, ManualFix>; confirming: boolean }
  | { step: "renaming"; done: number; total: number }
  | { step: "done"; summary: RenameSummary };

const REASON_LABEL: Record<ReviewReason, string> = {
  "no-number": "Sin número",
  "no-year": "Sin año",
  "year-mismatch": "Año distinto a la carpeta",
  duplicate: "Nombre repetido en la carpeta",
};

function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === "AbortError";
}

function plural(count: number, singular: string, pluralForm: string): string {
  return `${count} ${count === 1 ? singular : pluralForm}`;
}

function numberText(entry: ConceptEntry): string {
  return entry.number ? `${entry.number.value}${entry.number.letter}` : "";
}

function FirstPagePreview({ entry, onClose }: { entry: ConceptEntry; onClose: () => void }) {
  const [url, setUrl] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);
  const { fileHandle } = entry;

  // Keyed on the file handle, not the entry: entries are rebuilt on every
  // keystroke, and reloading the PDF would lose the user's zoom and scroll.
  useEffect(() => {
    let objectUrl: string | null = null;
    let cancelled = false;
    setFailed(false);
    fileHandle
      .getFile()
      .then((file) => {
        if (cancelled) return;
        objectUrl = URL.createObjectURL(file);
        setUrl(objectUrl);
      })
      .catch(() => {
        if (!cancelled) setFailed(true);
      });
    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [fileHandle]);

  return (
    <div className={`${TABLE_SHELL} space-y-2 p-3`}>
      <div className="flex items-center justify-between gap-2">
        <p className="text-sm font-medium text-foreground">{entry.path}</p>
        <Button variant="outline" size="sm" onClick={onClose}>
          Cerrar
        </Button>
      </div>
      {failed && <p className="text-sm text-muted-foreground">No se pudo abrir el archivo.</p>}
      {url && !failed && (
        <iframe
          title={`Primera página de ${entry.filename}`}
          src={`${url}#page=1`}
          className="h-[70vh] w-full rounded border border-border"
        />
      )}
    </div>
  );
}

export function ConceptosPgnPanel() {
  const [state, setState] = useState<PanelState>(() =>
    "showDirectoryPicker" in window ? { step: "idle" } : { step: "unsupported" }
  );
  const [previewPath, setPreviewPath] = useState<string | null>(null);

  async function handlePick() {
    try {
      const root = await window.showDirectoryPicker({ mode: "readwrite" });
      const plan = await analyzeConceptBatch(root);
      setPreviewPath(null);
      setState({ step: "loaded", plan, fixes: new Map(), confirming: false });
    } catch (error) {
      if (isAbortError(error)) return;
      const message = error instanceof ConceptPgnError ? error.message : "No se pudo leer la carpeta.";
      setState({ step: "error", message });
    }
  }

  function handleFixChange(entry: ConceptEntry, field: keyof ManualFix, value: string) {
    if (state.step !== "loaded") return;
    const fixes = new Map(state.fixes);
    const current = fixes.get(entry.path) ?? { year: String(entry.year ?? entry.folderYear ?? ""), number: numberText(entry) };
    fixes.set(entry.path, { ...current, [field]: value });
    setState({ ...state, fixes });
  }

  async function handleRename(plan: ConceptPlan) {
    const total = plan.entries.filter(isRenamable).length;
    setPreviewPath(null);
    setState({ step: "renaming", done: 0, total });
    try {
      const summary = await renameConcepts(plan, {
        onProgress: (done, count) => {
          if (done % 20 === 0 || done === count) setState({ step: "renaming", done, total: count });
        },
      });
      setState({ step: "done", summary });
    } catch {
      setState({ step: "error", message: "No se pudo completar el renombre. Revisa el registro en la carpeta del lote." });
    }
  }

  return (
    <div className="space-y-6">
      <p className="text-sm text-muted-foreground">
        Renombra en su sitio los conceptos de la Procuraduría a CTO_PGN_0000000_AAAA(C).
      </p>

      {state.step === "unsupported" && (
        <ErrorBanner message="Esta función necesita Chrome o Edge; tu navegador actual no es compatible." />
      )}

      {state.step === "idle" && (
        <div className={TABLE_SHELL}>
          <div className="flex flex-col items-center gap-3 px-4 py-10 text-center">
            <Button onClick={() => void handlePick()}>Elegir carpeta del lote</Button>
          </div>
        </div>
      )}

      {state.step === "error" && <ErrorBanner message={state.message} onRetry={() => setState({ step: "idle" })} />}

      {state.step === "renaming" && (
        <p className="text-sm text-muted-foreground">
          Renombrando {state.done} / {state.total}…
        </p>
      )}

      {state.step === "done" && (
        <div className="space-y-3">
          <p className="text-sm text-foreground">
            {plural(state.summary.renamedCount, "renombrado", "renombrados")} ·{" "}
            {plural(state.summary.skippedCount, "saltado", "saltados")}
          </p>
          {state.summary.skippedCount > 0 && (
            <ul className="list-disc space-y-1 pl-5 text-sm text-muted-foreground">
              {state.summary.outcomes
                .filter((outcome) => !outcome.renamed)
                .map((outcome) => (
                  <li key={outcome.path}>
                    {outcome.path}: {outcome.skipReason}
                  </li>
                ))}
            </ul>
          )}
          <p className="text-sm text-muted-foreground">
            Registro guardado en {state.summary.logName}. Retíralo antes de subir a Azure si no quieres que se suba.
          </p>
          <Button variant="outline" onClick={() => setState({ step: "idle" })}>
            Elegir otro lote
          </Button>
        </div>
      )}

      {state.step === "loaded" &&
        (() => {
          const resolved = applyManualFixes(state.plan, state.fixes);
          const renamable = resolved.entries.filter(isRenamable);
          const alreadyFinal = resolved.entries.filter(isAlreadyFinal);
          // A row the user is editing must not vanish once its fix resolves it,
          // so review rows come from the original analysis plus any fixed path.
          const reviewPaths = new Set(
            state.plan.entries.filter((entry) => entry.reason !== null).map((entry) => entry.path)
          );
          for (const entry of resolved.entries) if (entry.reason !== null) reviewPaths.add(entry.path);
          const reviewRows = resolved.entries.filter((entry) => reviewPaths.has(entry.path));
          const previewEntry = resolved.entries.find((entry) => entry.path === previewPath) ?? null;

          if (state.confirming) {
            return (
              <div className={`${TABLE_SHELL} space-y-3 p-4`}>
                <p className="text-sm text-foreground">
                  Esto cambia los nombres de los archivos originales y no se puede deshacer desde aquí. Se guardará un
                  registro en la carpeta raíz del lote.
                </p>
                <div className="flex gap-2">
                  <Button onClick={() => void handleRename(resolved)}>Sí, renombrar</Button>
                  <Button variant="outline" onClick={() => setState({ ...state, confirming: false })}>
                    Cancelar
                  </Button>
                </div>
              </div>
            );
          }

          return (
            <div className="space-y-4">
              <div className="space-y-1 text-sm text-muted-foreground">
                <p className="text-foreground">
                  Lote {resolved.rootName} · {plural(resolved.entries.length, "documento", "documentos")}
                </p>
                <p>{renamable.length} listos para renombrar</p>
                <p>{alreadyFinal.length} ya tienen el nombre final</p>
                <p>{reviewRows.length} requieren tu revisión</p>
              </div>

              {renamable.length > 0 && (
                <details className="text-sm">
                  <summary className="cursor-pointer text-muted-foreground">Ver todos (antes → después)</summary>
                  <div className={`${TABLE_SHELL} mt-2`}>
                    <div className={`${TABLE_SCROLL} max-h-96 overflow-y-auto`}>
                      <table className={TABLE}>
                        <thead>
                          <tr className={THEAD_ROW}>
                            <th className={TH}>Archivo</th>
                            <th className={TH}>Nombre nuevo</th>
                          </tr>
                        </thead>
                        <tbody>
                          {renamable.map((entry) => (
                            <tr key={entry.path} className={TBODY_ROW}>
                              <td className={`${TD} max-w-xs break-words`}>{entry.path}</td>
                              <td className={TD}>{entry.finalName}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                </details>
              )}

              {reviewRows.length > 0 && (
                <div className="space-y-2">
                  <h2 className="text-sm font-medium text-foreground">Requieren tu revisión</h2>
                  <div className={TABLE_SHELL}>
                    <div className={TABLE_SCROLL}>
                      <table className={TABLE}>
                        <thead>
                          <tr className={THEAD_ROW}>
                            <th className={TH}>Archivo</th>
                            <th className={TH}>Motivo</th>
                            <th className={TH}>Año</th>
                            <th className={TH}>Número</th>
                            <th className={TH}>Nombre nuevo</th>
                            <th className={TH}></th>
                          </tr>
                        </thead>
                        <tbody>
                          {reviewRows.map((entry) => {
                            const original = state.plan.entries.find((candidate) => candidate.path === entry.path)!;
                            const fix = state.fixes.get(entry.path);
                            const reason = entry.reason ?? original.reason;
                            return (
                              <tr key={entry.path} className={TBODY_ROW}>
                                <td className={`${TD} max-w-xs break-words`}>{entry.path}</td>
                                <td className={TD}>{reason ? REASON_LABEL[reason] : "Resuelto"}</td>
                                <td className={TD}>
                                  <Input
                                    aria-label={`Año de ${entry.path}`}
                                    value={fix ? fix.year : String(original.year ?? original.folderYear ?? "")}
                                    onChange={(event) => handleFixChange(original, "year", event.target.value)}
                                    className="w-20"
                                  />
                                </td>
                                <td className={TD}>
                                  <Input
                                    aria-label={`Número de ${entry.path}`}
                                    value={fix ? fix.number : numberText(original)}
                                    onChange={(event) => handleFixChange(original, "number", event.target.value)}
                                    className="w-24"
                                  />
                                </td>
                                <td className={TD}>
                                  {entry.finalName && entry.reason !== "duplicate" ? entry.finalName : "(queda igual)"}
                                </td>
                                <td className={TD}>
                                  {entry.filename.toLowerCase().endsWith(".pdf") && (
                                    <Button variant="outline" size="sm" onClick={() => setPreviewPath(entry.path)}>
                                      Ver
                                    </Button>
                                  )}
                                </td>
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                    </div>
                  </div>
                </div>
              )}

              {previewEntry && <FirstPagePreview entry={previewEntry} onClose={() => setPreviewPath(null)} />}

              {(resolved.crossFolderRepeats.length > 0 || resolved.photoOnlyFolders.length > 0) && (
                <div className="space-y-2 text-sm text-muted-foreground">
                  <h2 className="font-medium text-foreground">Avisos (no bloquean)</h2>
                  {resolved.crossFolderRepeats.length > 0 && (
                    <details>
                      <summary className="cursor-pointer">
                        {resolved.crossFolderRepeats.length} números aparecen en más de un tomo
                      </summary>
                      <ul className="mt-1 list-disc space-y-1 pl-5">
                        {resolved.crossFolderRepeats.map((repeat) => (
                          <li key={repeat.finalName}>
                            {repeat.finalName}: {repeat.paths.join(" · ")}
                          </li>
                        ))}
                      </ul>
                    </details>
                  )}
                  {resolved.photoOnlyFolders.length > 0 && (
                    <details>
                      <summary className="cursor-pointer">
                        {resolved.photoOnlyFolders.length} carpetas tienen solo fotos, sin documento
                      </summary>
                      <ul className="mt-1 list-disc space-y-1 pl-5">
                        {resolved.photoOnlyFolders.map((folder) => (
                          <li key={folder}>{folder}</li>
                        ))}
                      </ul>
                    </details>
                  )}
                </div>
              )}

              <Button disabled={renamable.length === 0} onClick={() => setState({ ...state, confirming: true })}>
                Renombrar {renamable.length} archivos
              </Button>
            </div>
          );
        })()}
    </div>
  );
}
