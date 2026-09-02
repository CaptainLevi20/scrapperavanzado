import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { FormatterPage } from "./FormatterPage";

describe("FormatterPage", () => {
  it("switches between the three Laboratorio tabs", async () => {
    const user = userEvent.setup();
    render(<FormatterPage />);

    expect(screen.getByRole("heading", { name: "Laboratorio" })).toBeInTheDocument();
    expect(screen.getByText(/necesita Chrome o Edge/)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Reorganización" }));
    expect(screen.getByLabelText("Ruta de la carpeta")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Decretos Cali" }));
    expect(screen.getByLabelText("Carpeta de destino")).toBeInTheDocument();
    expect(screen.queryByLabelText("Ruta de la carpeta")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Renombrado" }));
    expect(screen.getByText(/necesita Chrome o Edge/)).toBeInTheDocument();
  });
});
