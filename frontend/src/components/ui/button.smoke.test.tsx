import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { Button } from "./button";

describe("shadcn/ui setup", () => {
  it("renders a Button component with Tailwind classes applied", () => {
    render(<Button>Probar</Button>);
    const button = screen.getByRole("button", { name: "Probar" });
    expect(button).toBeInTheDocument();
    expect(button.className.length).toBeGreaterThan(0);
  });
});
