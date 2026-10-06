import type { SourceHealthAlert } from "../api/types";

const ALERT_LABELS: Record<SourceHealthAlert, string> = {
  silencio: "Sin novedades",
  caida: "Trae muy poco",
};

// Sello (dorado), no rojo: no es una falla confirmada sino algo a revisar —
// la fuente puede estar fallando o el sitio simplemente no publicó.
export function SourceHealthStamp({ alerta, detalle }: { alerta: SourceHealthAlert; detalle: string | null }) {
  return (
    <span className="stamp border-sello/50 bg-card text-sello-ink" title={detalle ?? undefined}>
      <span className="stamp-dot" />
      Revisar: {ALERT_LABELS[alerta]}
    </span>
  );
}
