const STATUS_STYLES: Record<string, string> = {
  pending: "border-grafito/40 text-grafito",
  running: "border-sello/60 text-sello-ink",
  completed: "border-verde/50 text-verde",
  failed: "border-rojo/50 text-rojo",
  cancelled: "border-grafito/60 text-grafito",
};

export function StatusBadge({ status }: { status: string }) {
  const className = STATUS_STYLES[status] ?? "border-grafito/40 text-grafito";
  const isLive = status === "running";

  return (
    <span className={`stamp bg-card ${className}`}>
      <span className={`stamp-dot ${isLive ? "pulse-dot" : ""}`} />
      {status}
    </span>
  );
}
