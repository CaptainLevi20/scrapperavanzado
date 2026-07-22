import { useState } from "react";
import JSZip from "jszip";
import { Wand2 } from "lucide-react";
import { downloadBlob } from "../api/documents";
import { ErrorBanner } from "../components/ErrorBanner";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import {
  analyzeZip,
  applyCorrections,
  computeFinalName,
  FormatterError,
  type Correction,
  type FormatterPlan,
} from "../lib/formatter/analyze";
import { buildFormattedZip } from "../lib/formatter/build";
import { TABLE, TABLE_SCROLL, TABLE_SHELL, TBODY_ROW, TD, TH, THEAD_ROW } from "../lib/tableStyles";

type FormatterState =
  | { step: "idle"; notice?: string }
  | { step: "error"; message: string }
  | { step: "loaded"; plan: FormatterPlan; zip: JSZip; corrections: Map<string, Correction> }
  | { step: "building"; plan: FormatterPlan; zip: JSZip; corrections: Map<string, Correction> };

const REASON_LABEL: Record<string, string> = {
  "no-year": "Año no detectado",
  "no-number": "Número no detectado",
  duplicate: "Número duplicado",
};

export function FormatterPage() {
  const [state, setState] = useState<FormatterState>({ step: "idle" });

  async function handleFileSelected(file: File) {
    try {
      const [plan, zip] = await Promise.all([analyzeZip(file), JSZip.loadAsync(file)]);
      setState({ step: "loaded", plan, zip, corrections: new Map() });
    } catch (error) {
      const message = error instanceof FormatterError ? error.message : "No se pudo leer el archivo ZIP.";
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

  async function handleDownload() {
    if (state.step !== "loaded") return;
    const resolvedPlan = applyCorrections(state.plan, state.corrections);
    const resolvedNames = new Map<string, string>();
    for (const entry of resolvedPlan.entries) {
      const name = computeFinalName(resolvedPlan.config, entry);
      if (name) resolvedNames.set(entry.path, name);
    }

    setState({ step: "building", plan: state.plan, zip: state.zip, corrections: state.corrections });
    try {
      const { blob, skippedCount } = await buildFormattedZip(state.zip, resolvedPlan, resolvedNames);
      downloadBlob(blob, `Formateador_${resolvedPlan.rootFolderName}.zip`);
      setState({
        step: "idle",
        notice:
          skippedCount > 0
            ? `${skippedCount} archivo${skippedCount === 1 ? "" : "s"} se omitieron por error de lectura.`
            : undefined,
      });
    } catch {
      setState({ step: "error", message: "No se pudo generar el ZIP." });
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <p className="flex items-center gap-1.5 text-xs font-medium tracking-[0.18em] text-muted-foreground uppercase">
          <Wand2 className="size-3.5" aria-hidden="true" />
          Renombrado de lotes
        </p>
        <h1 className="font-display text-3xl font-semibold tracking-tight text-foreground">Formateador</h1>
      </div>

      {state.step === "idle" && (
        <div className={TABLE_SHELL}>
          <div className="flex flex-col items-center gap-3 px-4 py-10 text-center">
            {state.notice && <p className="text-xs text-muted-foreground">{state.notice}</p>}
            <p className="text-sm text-muted-foreground">
              Sube un ZIP con la carpeta de acuerdos (subcarpetas por año) para renombrar los archivos.
            </p>
            <Input
              type="file"
              accept=".zip"
              aria-label="Seleccionar archivo ZIP"
              className="max-w-xs"
              onChange={(event) => {
                const file = event.target.files?.[0];
                if (file) void handleFileSelected(file);
              }}
            />
          </div>
        </div>
      )}

      {state.step === "error" && <ErrorBanner message={state.message} onRetry={() => setState({ step: "idle" })} />}

      {state.step === "building" && <p className="text-sm text-muted-foreground">Generando el ZIP…</p>}

      {state.step === "loaded" &&
        (() => {
          const resolvedPlan = applyCorrections(state.plan, state.corrections);
          const pending = resolvedPlan.entries.filter((entry) => entry.reason !== null);
          const visibleRows = resolvedPlan.entries.filter(
            (entry) => entry.reason !== null || state.corrections.has(entry.path)
          );
          const ready = resolvedPlan.entries.length - pending.length;
          const canDownload = pending.length === 0;

          return (
            <div className="space-y-4">
              <p className="text-sm text-muted-foreground">
                {ready} archivo{ready === 1 ? "" : "s"} listo{ready === 1 ? "" : "s"}
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

              <Button onClick={() => void handleDownload()} disabled={!canDownload}>
                Descargar ZIP
              </Button>
            </div>
          );
        })()}
    </div>
  );
}
