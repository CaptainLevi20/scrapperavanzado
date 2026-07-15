import { useQuery } from "@tanstack/react-query";
import { fetchAllActiveSources } from "../../api/sources";

const TODAY_LABEL = new Date().toLocaleDateString("es-CO", {
  weekday: "long",
  day: "numeric",
  month: "long",
});

export function Masthead() {
  // Same query key OverviewPage uses for its "Fuentes activas" stat — when both
  // are mounted together, React Query dedupes this into a single network call.
  const activeSourcesQuery = useQuery({
    queryKey: ["sources", "active-count"],
    queryFn: fetchAllActiveSources,
  });

  return (
    <header className="flex items-center justify-between border-b border-sidebar-border bg-sidebar px-6 py-2.5 text-sidebar-foreground">
      <div className="flex items-center gap-2 text-xs">
        <span className="relative flex size-2">
          <span className="pulse-dot absolute inline-flex size-2 rounded-full bg-sello" />
          <span className="relative inline-flex size-2 rounded-full bg-sello" />
        </span>
        <span className="text-sidebar-foreground/80">
          Monitoreando <span className="font-mono-num font-semibold text-sidebar-foreground">{activeSourcesQuery.data?.length ?? "—"}</span>{" "}
          fuentes oficiales
        </span>
      </div>
      <p className="text-xs text-sidebar-foreground/50 capitalize">{TODAY_LABEL}</p>
    </header>
  );
}
