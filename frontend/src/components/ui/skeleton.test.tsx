import { describe, expect, it } from "vitest";
import { render } from "@testing-library/react";
import { Skeleton } from "./skeleton";

describe("Skeleton", () => {
  it("is hidden from assistive tech (it carries no information)", () => {
    const { container } = render(<Skeleton />);
    const el = container.querySelector('[data-slot="skeleton"]');
    expect(el).not.toBeNull();
    expect(el).toHaveAttribute("aria-hidden", "true");
  });

  it("pulses, but stops pulsing under prefers-reduced-motion", () => {
    const { container } = render(<Skeleton />);
    const el = container.querySelector('[data-slot="skeleton"]')!;
    expect(el).toHaveClass("animate-pulse");
    // The reduced-motion opt-out must ship on the base element, not be left to
    // each caller — users who ask for less motion should never see it pulse.
    expect(el).toHaveClass("motion-reduce:animate-none");
  });

  it("merges caller classes (size/width) onto the base element", () => {
    const { container } = render(<Skeleton className="h-8 w-16" />);
    const el = container.querySelector('[data-slot="skeleton"]')!;
    expect(el).toHaveClass("h-8");
    expect(el).toHaveClass("w-16");
  });
});
