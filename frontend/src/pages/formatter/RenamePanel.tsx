import { useState } from "react";
import { ErrorBanner } from "../../components/ErrorBanner";
import { Button } from "../../components/ui/button";
import { Input } from "../../components/ui/input";
import {
  analyzeDirectory,
  applyCorrections,
  computeFinalName,
  FormatterError,
  type Correction,
  type FormatterPlan,
} from "../../lib/formatter/analyze";
import { copyFormattedFiles } from "../../lib/formatter/copy";
import { TABLE, TABLE_SCROLL, TABLE_SHELL, TBODY_ROW, TD, TH, THEAD_ROW } from "../../lib/tableStyles";

type FormatterState =
  | { step: "idle"; notice?: string }
  | { step: "unsupported" }
  | { step: "error"; message: string }
  | { step: "loaded"; inputRoot: FileSystemDirectoryHandle; plan: FormatterPlan; corrections: Map<string, Correction> }
  | { step: "copying"; done: number; total: number };

const REASON_LABEL: Record<string, string> = {
  "no-year": "Año no detectado",
  "no-number": "Número no detectado",
  duplicate: "Número duplicado",
};

function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === "AbortError";
}

export function RenamePanel() {
  const [state, setState] = useState<FormatterState>(() =>
    "showDirectoryPicker" in window ? { step: "idle" } : { step: "unsupported" }
  );

  async function handlePickInput() {
    try {
      const root = await window.showDirectoryPicker();
      const plan = await analyzeDirectory(root);
      setState({ step: "loaded", inputRoot: root, plan, corrections: new Map() });
    } catch (error) {
      if (isAbortError(error)) return;
      const message = error instanceof FormatterError ? error.message : "No se pudo leer la carpeta.";
      setState({ step: "error", message });
    }
  }

  function handleCorrectionChange(path: string, field: keyof Correction, value: string) {
    if (state.step !== "loaded") return;
    const entry = state.plan.entries.find((candidate) => candidate.path === path);
    if (!entry) return;
    const corrections = new Map(state.corrections);
    const current =
      corrections.get(path) ?? { year: String(entry.detectedYear ?? ""), number: String(entry.detectedNumber ?? "") };
    corrections.set(path, { ...current, [field]: value });
    setState({ ...state, corrections });
  }

  async function handleCopy() {
    if (state.step !== "loaded") return;
    const resolvedPlan = applyCorrections(state.plan, state.corrections);
    const resolvedNames = new Map<string, string>();
    for (const entry of resolvedPlan.entries) {
      const name = computeFinalName(resolvedPlan.config, entry);
      if (name) {
        resolvedNames.set(entry.path, name);
      } else if (entry.reason === "no-number") {
        // No number could be determined and the user didn't correct it — copy
        // the file through with its original name instead of blocking the
        // whole batch on a number nobody can reliably guess.
        resolvedNames.set(entry.path, entry.filename);
      }
    }

    let outputRoot: FileSystemDirectoryHandle;
    try {
      outputRoot = await window.showDirectoryPicker({ mode: "readwrite" });
    } catch (error) {
      if (isAbortError(error)) return;
      setState({ step: "error", message: "No se pudo abrir la carpeta de salida." });
      return;
    }

    if (await state.inputRoot.isSameEntry(outputRoot)) {
      setState({ step: "error", message: "La carpeta de salida no puede ser la misma que la de entrada." });
      return;
    }

    setState({ step: "copying", done: 0, total: resolvedNames.size });
    try {
      const { copiedCount, skippedCount } = await copyFormattedFiles(
        outputRoot,
        resolvedPlan,
        resolvedNames,
        (done, total) => {
          if (done % 20 === 0 || done === total) setState({ step: "copying", done, total });
        }
      );
      const copiedLabel = `${copiedCount} archivo${copiedCount === 1 ? "" : "s"} copiado${copiedCount === 1 ? "" : "s"}`;
      setState({
        step: "idle",
        notice:
          skippedCount > 0
            ? `${copiedLabel}, ${skippedCount} omitido${skippedCount === 1 ? "" : "s"} por error de lectura.`
            : `${copiedLabel}.`,
      });
    } catch {
      setState({ step: "error", message: "No se pudo completar la copia." });
    }
  }

  return (
    <div className="space-y-6">
      {state.step === "unsupported" && (
        <ErrorBanner message="Esta función necesita Chrome o Edge; tu navegador actual no es compatible." />
      )}

      {state.step === "idle" && (
        <div className={TABLE_SHELL}>
          <div className="flex flex-col items-center gap-3 px-4 py-10 text-center">
            {state.notice && <p className="text-xs text-muted-foreground">{state.notice}</p>}
            <p className="text-sm text-muted-foreground">
              Elige la carpeta para renombrar los archivos.
            </p>
            <Button onClick={() => void handlePickInput()}>Elegir carpeta de entrada</Button>
          </div>
        </div>
      )}

      {state.step === "error" && <ErrorBanner message={state.message} onRetry={() => setState({ step: "idle" })} />}

      {state.step === "copying" && (
        <p className="text-sm text-muted-foreground">
          Copiando {state.done} / {state.total}…
        </p>
      )}

      {state.step === "loaded" &&
        (() => {
          const resolvedPlan = applyCorrections(state.plan, state.corrections);
          // A "no-number" entry never blocks the copy on its own — left uncorrected,
          // it just passes through with its original filename (see handleCopy).
          const pending = resolvedPlan.entries.filter((entry) => entry.reason !== null && entry.reason !== "no-number");
          const passthrough = resolvedPlan.entries.filter((entry) => entry.reason === "no-number");
          // An untouched "no-number" entry never gets a row: it always passes
          // through with its original filename, so listing it would just read
          // as unfinished work. But once the user starts editing it (e.g.
          // clearing a duplicate's number field mid-correction transiently
          // makes it "no-number" too), it must stay visible — otherwise the
          // row would vanish out from under whatever they're typing.
          const visibleRows = resolvedPlan.entries.filter((entry) => {
            if (entry.reason === "no-number" && !state.corrections.has(entry.path)) return false;
            return entry.reason !== null || state.corrections.has(entry.path);
          });
          const ready = resolvedPlan.entries.length - pending.length - passthrough.length;
          const canCopy = pending.length === 0;

          return (
            <div className="space-y-4">
              <p className="text-sm text-muted-foreground">
                {ready} archivo{ready === 1 ? "" : "s"} listo{ready === 1 ? "" : "s"}
                {passthrough.length > 0
                  ? `, ${passthrough.length} sin número (se copiarán con su nombre original)`
                  : ""}
                {pending.length > 0 ? `, ${pending.length} por revisar` : ""}.
              </p>

              {visibleRows.length > 0 && (
                <div className={TABLE_SHELL}>
                  <div className={TABLE_SCROLL}>
                    <table className={TABLE}>
                      <thead>
                        <tr className={THEAD_ROW}>
                          <th className={TH}>Archivo</th>
                          <th className={TH}>Motivo</th>
                          <th className={TH}>Año</th>
                          <th className={TH}>Número</th>
                        </tr>
                      </thead>
                      <tbody>
                        {visibleRows.map((entry) => {
                          const correction = state.corrections.get(entry.path);
                          const yearValue = correction ? correction.year : String(entry.detectedYear ?? "");
                          const numberValue = correction ? correction.number : String(entry.detectedNumber ?? "");
                          return (
                            <tr key={entry.path} className={TBODY_ROW}>
                              <td className={TD}>{entry.path}</td>
                              <td className={TD}>{entry.reason ? REASON_LABEL[entry.reason] : "Resuelto"}</td>
                              <td className={TD}>
                                <Input
                                  aria-label={`Año para ${entry.path}`}
                                  value={yearValue}
                                  onChange={(event) => handleCorrectionChange(entry.path, "year", event.target.value)}
                                  className="w-24"
                                />
                              </td>
                              <td className={TD}>
                                <Input
                                  aria-label={`Número para ${entry.path}`}
                                  value={numberValue}
                                  onChange={(event) => handleCorrectionChange(entry.path, "number", event.target.value)}
                                  className="w-24"
                                />
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              <Button onClick={() => void handleCopy()} disabled={!canCopy}>
                Elegir carpeta de salida y copiar
              </Button>
            </div>
          );
        })()}
    </div>
  );
}
