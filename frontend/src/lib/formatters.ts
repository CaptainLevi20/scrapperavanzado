export function formatBytes(bytes: number | null): string {
  if (bytes === null) return "—";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

const DATE_ONLY_PATTERN = /^(\d{4})-(\d{2})-(\d{2})$/;

// A plain "YYYY-MM-DD" string is parsed by `new Date(value)` as UTC midnight —
// in any timezone west of UTC (Colombia included, UTC-5) that shifts to the
// previous day once displayed in local time. Confirmed for real against JEP
// documents whose stored f_public/f_providencia were correct but rendered one
// day earlier. Parsing the components explicitly as local-time avoids the shift
// (see the same fix already applied in dashboardStats.ts's yearMonthOf).
function parseDateOnlyAsLocal(value: string): Date {
  const match = DATE_ONLY_PATTERN.exec(value);
  if (!match) return new Date(value);
  const [, year, month, day] = match;
  return new Date(Number(year), Number(month) - 1, Number(day));
}

export function formatDate(value: string | null): string {
  if (!value) return "—";
  return parseDateOnlyAsLocal(value).toLocaleDateString("es-CO", { year: "numeric", month: "short", day: "numeric" });
}

export function formatDateTime(value: string | null): string {
  if (!value) return "—";
  return new Date(value).toLocaleString("es-CO");
}

const RELATIVE_TIME_UNITS: [Intl.RelativeTimeFormatUnit, number][] = [
  ["year", 1000 * 60 * 60 * 24 * 365],
  ["month", 1000 * 60 * 60 * 24 * 30],
  ["week", 1000 * 60 * 60 * 24 * 7],
  ["day", 1000 * 60 * 60 * 24],
  ["hour", 1000 * 60 * 60],
  ["minute", 1000 * 60],
];

const relativeTimeFormatter = new Intl.RelativeTimeFormat("es-CO", { numeric: "auto" });

export function formatRelativeTime(value: string | null): string {
  if (!value) return "—";
  const diffMs = new Date(value).getTime() - Date.now();

  for (const [unit, unitMs] of RELATIVE_TIME_UNITS) {
    if (Math.abs(diffMs) >= unitMs) {
      return relativeTimeFormatter.format(Math.round(diffMs / unitMs), unit);
    }
  }
  return relativeTimeFormatter.format(0, "minute");
}
