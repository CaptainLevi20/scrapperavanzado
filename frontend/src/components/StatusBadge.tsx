const STATUS_STYLES: Record<string, string> = {
  pending: "border-grafito/40 text-grafito",
  running: "border-sello/60 text-sello-ink",
  completed: "border-verde/50 text-verde",
  failed: "border-rojo/50 text-rojo",
  cancelled: "border-grafito/60 text-grafito",
};

// Spanish labels for the run/bulk-download status enum — the rest of the app
// (including the Runs page's own status filter) is in Spanish, so showing the
// raw English enum value on the badge read as an untranslated leak. An unknown
// status falls back to its raw value rather than rendering blank.
const STATUS_LABELS: Record<string, string> = {
  pending: "Pendiente",
  running: "En curso",
  completed: "Completado",
  failed: "Fallido",
  cancelled: "Cancelado",
};

export function StatusBadge({ status }: { status: string }) {
  const className = STATUS_STYLES[status] ?? "border-grafito/40 text-grafito";
  const isLive = status === "running";

  return (
    <span className={`stamp bg-card ${className}`}>
      <span className={`stamp-dot ${isLive ? "pulse-dot" : ""}`} />
      {STATUS_LABELS[status] ?? status}
    </span>
  );
}
