import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { FormatterPage } from "./FormatterPage";
import { fakeInputDirectory, fakeOutputDirectory } from "../lib/formatter/testFsFakes";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("FormatterPage", () => {
  it("shows a ready summary and an enabled copy button when every file resolves cleanly", async () => {
    const inputRoot = fakeInputDirectory("Acuerdos Cali", {
      "ACUERDOS 1962": {
        "Acuerdo 0005 de 1962.pdf": "contenido",
        "Acuerdo 0006 de 1962.pdf": "contenido",
      },
    });
    vi.stubGlobal("showDirectoryPicker", vi.fn().mockResolvedValue(inputRoot));

    render(<FormatterPage />);
    await userEvent.click(screen.getByRole("button", { name: /elegir carpeta de entrada/i }));

    expect(await screen.findByText(/2 archivos listos/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /elegir carpeta de salida y copiar/i })).toBeEnabled();
  });

  it("passes an unresolved no-number file through with its original name and never lists it for review", async () => {
    const inputRoot = fakeInputDirectory("Acuerdos Cali", {
      "ACUERDOS 2016": { "decretos.rar": "contenido" },
    });
    const output = fakeOutputDirectory("salida");
    const picker = vi.fn().mockResolvedValueOnce(inputRoot).mockResolvedValueOnce(output.handle);
    vi.stubGlobal("showDirectoryPicker", picker);

    const user = userEvent.setup();
    render(<FormatterPage />);
    await user.click(screen.getByRole("button", { name: /elegir carpeta de entrada/i }));

    expect(await screen.findByText(/sin número \(se copiarán con su nombre original\)/i)).toBeInTheDocument();
    expect(screen.queryByText(/número no detectado/i)).not.toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();

    const copyButton = screen.getByRole("button", { name: /elegir carpeta de salida y copiar/i });
    expect(copyButton).toBeEnabled();
    await user.click(copyButton);

    await waitFor(() => expect(screen.getByText(/1 archivo copiado/i)).toBeInTheDocument());
    expect(output.readAll()).toEqual({ "ACUERDOS 2016/decretos.rar": "contenido" });
  });

  it("keeps a duplicate row editable through a multi-digit correction, resolving the collision once disambiguated", async () => {
    const inputRoot = fakeInputDirectory("Acuerdos Cali", {
      "ACUERDOS 1962": {
        "Acuerdo 0005 primero.pdf": "contenido-a",
        "Acuerdo 0005 segundo.pdf": "contenido-b",
      },
    });
    const output = fakeOutputDirectory("salida");
    const picker = vi.fn().mockResolvedValueOnce(inputRoot).mockResolvedValueOnce(output.handle);
    vi.stubGlobal("showDirectoryPicker", picker);

    const user = userEvent.setup();
    render(<FormatterPage />);
    await user.click(screen.getByRole("button", { name: /elegir carpeta de entrada/i }));

    await screen.findAllByText(/número duplicado/i);
    expect(screen.getByRole("button", { name: /elegir carpeta de salida y copiar/i })).toBeDisabled();

    const numberFields = screen.getAllByLabelText(/número para/i);
    await user.clear(numberFields[0]);
    await user.type(numberFields[0], "12");
    expect(numberFields[0]).toHaveValue("12");

    const copyButton = screen.getByRole("button", { name: /elegir carpeta de salida y copiar/i });
    await waitFor(() => expect(copyButton).toBeEnabled());
    await user.click(copyButton);

    await waitFor(() => expect(screen.getByText(/2 archivos copiados/i)).toBeInTheDocument());
    expect(output.readAll()).toEqual({
      "ACUERDOS 1962/A_CONCALI_0012_1962.pdf": "contenido-a",
      "ACUERDOS 1962/A_CONCALI_0005_1962.pdf": "contenido-b",
    });
  });

  it("shows an error when the output folder is the same as the input folder", async () => {
    const sameRoot = fakeInputDirectory("Acuerdos Cali", {
      "ACUERDOS 1962": { "Acuerdo 0005 de 1962.pdf": "contenido" },
    });
    vi.stubGlobal("showDirectoryPicker", vi.fn().mockResolvedValue(sameRoot));

    const user = userEvent.setup();
    render(<FormatterPage />);
    await user.click(screen.getByRole("button", { name: /elegir carpeta de entrada/i }));

    await screen.findByText(/1 archivo listo/);
    await user.click(screen.getByRole("button", { name: /elegir carpeta de salida y copiar/i }));

    expect(await screen.findByText(/la carpeta de salida no puede ser la misma/i)).toBeInTheDocument();
  });

  it("shows an error banner for a folder whose name isn't recognized", async () => {
    const inputRoot = fakeInputDirectory("Resoluciones Bogota", { "2020": { "algo.pdf": "x" } });
    vi.stubGlobal("showDirectoryPicker", vi.fn().mockResolvedValue(inputRoot));

    render(<FormatterPage />);
    await userEvent.click(screen.getByRole("button", { name: /elegir carpeta de entrada/i }));

    expect(await screen.findByText(/no se reconoce el tipo de documento o la ciudad/i)).toBeInTheDocument();
  });

  it("does not show an error when the user cancels the directory picker", async () => {
    const abortError = new DOMException("The user aborted a request.", "AbortError");
    vi.stubGlobal("showDirectoryPicker", vi.fn().mockRejectedValue(abortError));

    render(<FormatterPage />);
    await userEvent.click(screen.getByRole("button", { name: /elegir carpeta de entrada/i }));

    await waitFor(() => expect(screen.getByRole("button", { name: /elegir carpeta de entrada/i })).toBeInTheDocument());
    expect(screen.queryByText(/no se pudo/i)).not.toBeInTheDocument();
  });

  it("shows the unsupported-browser message when showDirectoryPicker doesn't exist", () => {
    render(<FormatterPage />);

    expect(screen.getByText(/necesita chrome o edge/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /elegir carpeta de entrada/i })).not.toBeInTheDocument();
  });
});
