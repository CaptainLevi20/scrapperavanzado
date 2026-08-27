import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { FormatterPage } from "./FormatterPage";

describe("FormatterPage", () => {
  it("shows the Renombrado panel by default and switches to Reorganización on tab click", async () => {
    const user = userEvent.setup();
    render(<FormatterPage />);

    expect(screen.getByRole("heading", { name: "Laboratorio" })).toBeInTheDocument();
    expect(screen.getByText(/necesita Chrome o Edge/)).toBeInTheDocument();
    expect(screen.queryByLabelText("Ruta de la carpeta")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Reorganización" }));

    expect(screen.getByLabelText("Ruta de la carpeta")).toBeInTheDocument();
    expect(screen.queryByText(/necesita Chrome o Edge/)).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Renombrado" }));

    expect(screen.getByText(/necesita Chrome o Edge/)).toBeInTheDocument();
  });
});
