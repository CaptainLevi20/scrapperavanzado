import { cn } from "@/lib/utils";
import { TBODY_ROW, TD } from "@/lib/tableStyles";
import { Skeleton } from "./ui/skeleton";

// Placeholder rows to drop straight into a table's <tbody> while its data
// loads. It reuses the shared TBODY_ROW / TD recipes so the skeleton lines up
// with the real rows exactly — the header and column layout stay put, so
// nothing jumps when the data arrives (no layout shift).
//
// `widths` optionally sets a Tailwind width class per column (index-aligned) so
// the bars mimic each column's real content rhythm; columns without an entry
// fall back to a sensible default.
export function TableRowsSkeleton({
  rows = 6,
  columns,
  widths,
}: {
  rows?: number;
  columns: number;
  widths?: string[];
}) {
  return (
    <>
      {Array.from({ length: rows }).map((_, rowIndex) => (
        <tr key={rowIndex} className={TBODY_ROW} aria-hidden="true">
          {Array.from({ length: columns }).map((_, colIndex) => (
            <td key={colIndex} className={TD}>
              <Skeleton className={cn("h-4", widths?.[colIndex] ?? "w-24")} />
            </td>
          ))}
        </tr>
      ))}
    </>
  );
}
