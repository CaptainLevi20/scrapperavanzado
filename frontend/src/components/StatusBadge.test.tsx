import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { StatusBadge } from "./StatusBadge";

describe("StatusBadge", () => {
  it("renders the status label in Spanish, not the raw English enum value", () => {
    render(<StatusBadge status="completed" />);
    expect(screen.getByText("Completado")).toBeInTheDocument();
    expect(screen.queryByText("completed")).not.toBeInTheDocument();
  });

  it("translates every known run status", () => {
    const cases: [string, string][] = [
      ["pending", "Pendiente"],
      ["running", "En curso"],
      ["completed", "Completado"],
      ["completed_with_errors", "Completado con errores"],
      ["failed", "Fallido"],
      ["cancelled", "Cancelado"],
    ];
    for (const [status, label] of cases) {
      const { unmount } = render(<StatusBadge status={status} />);
      expect(screen.getByText(label)).toBeInTheDocument();
      unmount();
    }
  });

  it("falls back to the raw value for an unknown status", () => {
    render(<StatusBadge status="unknown-status" />);
    expect(screen.getByText("unknown-status")).toBeInTheDocument();
  });

  it("renders the cancelled status in Spanish", () => {
    render(<StatusBadge status="cancelled" />);
    expect(screen.getByText("Cancelado")).toBeInTheDocument();
  });
});
