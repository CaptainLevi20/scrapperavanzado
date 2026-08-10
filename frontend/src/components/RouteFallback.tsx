import { TABLE, TABLE_SCROLL, TABLE_SHELL, TH, THEAD_ROW } from "../lib/tableStyles";
import { TableRowsSkeleton } from "./TableSkeleton";
import { Skeleton } from "./ui/skeleton";

// Shown in the content area (inside AppLayout, so the sidebar and masthead stay
// put) while a lazily-loaded page's code chunk downloads. It's deliberately
// generic — a heading and a table shell — since it stands in for whichever page
// is on its way, and only flashes for the moment the chunk takes to arrive.
export function RouteFallback() {
  return (
    <div className="space-y-6" aria-busy="true">
      <div className="space-y-2">
        <Skeleton className="h-3 w-40" />
        <Skeleton className="h-8 w-64" />
      </div>
      <div className={TABLE_SHELL}>
        <div className={TABLE_SCROLL}>
          <table className={TABLE} aria-busy="true">
            <thead>
              <tr className={THEAD_ROW}>
                {Array.from({ length: 5 }).map((_, index) => (
                  <th key={index} className={TH}>
                    <Skeleton className="h-3 w-20" />
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              <TableRowsSkeleton rows={8} columns={5} />
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
