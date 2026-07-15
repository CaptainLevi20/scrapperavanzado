// Shared class recipes so every data table in the app ("manifiesto" style —
// hairline rules, sticky header, hover highlight) looks and feels consistent,
// without introducing a table abstraction that would change the underlying
// <table>/<thead>/<tbody> DOM structure tests already rely on.

export const TABLE_SHELL = "overflow-hidden rounded-lg border border-border bg-card shadow-sm";

// Wraps the <table> itself: lets wide tables scroll horizontally instead of
// squeezing every column illegibly, without clipping TABLE_SHELL's rounded
// corners (that clipping lives on the outer element instead).
export const TABLE_SCROLL = "overflow-x-auto";

export const TABLE = "w-full border-collapse text-left text-sm";

export const THEAD_ROW = "border-b border-border bg-secondary/60";

export const TH = "px-4 py-3 text-xs font-semibold tracking-wide text-muted-foreground uppercase";

export const TBODY_ROW = "border-b border-border/70 last:border-b-0 transition-colors hover:bg-secondary/40";

export const TD = "px-4 py-3 align-middle";

export const TD_MONO = `${TD} font-mono-num text-[0.8rem] text-foreground/90`;
