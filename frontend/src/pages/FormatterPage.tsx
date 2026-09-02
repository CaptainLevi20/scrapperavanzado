import { useState } from "react";
import { Wand2 } from "lucide-react";
import { RenamePanel } from "./formatter/RenamePanel";
import { ReorganizePanel } from "./formatter/ReorganizePanel";
import { CaliDecretosPanel } from "./formatter/CaliDecretosPanel";

type Tab = "rename" | "reorganize" | "cali-decretos";

const TABS: { id: Tab; label: string }[] = [
  { id: "rename", label: "Renombrado" },
  { id: "reorganize", label: "Reorganización" },
  { id: "cali-decretos", label: "Decretos Cali" },
];

function PanelActivo({ tab }: { tab: Tab }) {
  if (tab === "rename") return <RenamePanel />;
  if (tab === "reorganize") return <ReorganizePanel />;
  return <CaliDecretosPanel />;
}

export function FormatterPage() {
  const [tab, setTab] = useState<Tab>("rename");

  return (
    <div className="space-y-6">
      <div>
        <p className="flex items-center gap-1.5 text-xs font-medium tracking-[0.18em] text-muted-foreground uppercase">
          <Wand2 className="size-3.5" aria-hidden="true" />
          Herramientas de lote
        </p>
        <h1 className="font-display text-3xl font-semibold tracking-tight text-foreground">Laboratorio</h1>
      </div>

      <div className="flex gap-1 border-b border-border">
        {TABS.map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={`px-3 py-2 text-sm font-medium transition-colors ${
              tab === t.id
                ? "border-b-2 border-primary text-foreground"
                : "text-muted-foreground hover:text-foreground"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      <PanelActivo tab={tab} />
    </div>
  );
}
