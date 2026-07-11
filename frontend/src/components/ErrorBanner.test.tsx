import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ErrorBanner } from "./ErrorBanner";

describe("ErrorBanner", () => {
  it("renders the message", () => {
    render(<ErrorBanner message="Algo salió mal" />);
    expect(screen.getByText("Algo salió mal")).toBeInTheDocument();
  });

  it("calls onRetry when the retry button is clicked", async () => {
    const user = userEvent.setup();
    const onRetry = vi.fn();
    render(<ErrorBanner message="Algo salió mal" onRetry={onRetry} />);

    await user.click(screen.getByText("Reintentar"));

    expect(onRetry).toHaveBeenCalledOnce();
  });
});
