import { describe, expect, it } from "vitest";
import { render } from "@testing-library/react";
import { TableRowsSkeleton } from "./TableSkeleton";

function renderInTable(ui: React.ReactNode) {
  return render(
    <table>
      <tbody>{ui}</tbody>
    </table>
  );
}

describe("TableRowsSkeleton", () => {
  it("renders one placeholder per cell for the given rows × columns", () => {
    const { container } = renderInTable(<TableRowsSkeleton rows={3} columns={4} />);
    expect(container.querySelectorAll("tr")).toHaveLength(3);
    expect(container.querySelectorAll("td")).toHaveLength(12);
    expect(container.querySelectorAll('[data-slot="skeleton"]')).toHaveLength(12);
  });

  it("applies the per-column width class when provided", () => {
    const { container } = renderInTable(
      <TableRowsSkeleton rows={1} columns={3} widths={["w-40", "w-20", "w-24"]} />
    );
    const bars = container.querySelectorAll('[data-slot="skeleton"]');
    expect(bars[0]).toHaveClass("w-40");
    expect(bars[1]).toHaveClass("w-20");
    expect(bars[2]).toHaveClass("w-24");
  });

  it("marks the placeholder rows as decorative so screen readers skip them", () => {
    const { container } = renderInTable(<TableRowsSkeleton rows={2} columns={2} />);
    for (const row of container.querySelectorAll("tr")) {
      expect(row).toHaveAttribute("aria-hidden", "true");
    }
  });
});
