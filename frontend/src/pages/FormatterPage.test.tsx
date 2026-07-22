import { describe, expect, it } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import JSZip from "jszip";
import { FormatterPage } from "./FormatterPage";

async function buildZipFile(entries: Record<string, string>, name = "Acuerdos Cali.zip"): Promise<File> {
  const zip = new JSZip();
  for (const [path, content] of Object.entries(entries)) {
    zip.file(path, content);
  }
  const blob = await zip.generateAsync({ type: "blob" });
  return new File([blob], name, { type: "application/zip" });
}

describe("FormatterPage", () => {
  it("shows a ready summary and an enabled download button when every file resolves cleanly", async () => {
    const file = await buildZipFile({
      "Acuerdos Cali/ACUERDOS 1962/Acuerdo 0005 de 1962.pdf": "contenido",
      "Acuerdos Cali/ACUERDOS 1962/Acuerdo 0006 de 1962.pdf": "contenido",
    });

    const user = userEvent.setup();
    render(<FormatterPage />);
    const input = screen.getByLabelText(/seleccionar archivo zip/i);
    await user.upload(input, file);

    expect(await screen.findByText(/2 archivos listos/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /descargar zip/i })).toBeEnabled();
  });

  it("keeps the download button disabled until an exception row is filled in, then enables it", async () => {
    const file = await buildZipFile({
      "Acuerdos Cali/ACUERDOS 1962/sin numero.pdf": "contenido",
    });

    const user = userEvent.setup();
    render(<FormatterPage />);
    const input = screen.getByLabelText(/seleccionar archivo zip/i);
    await user.upload(input, file);

    expect(await screen.findByText(/número no detectado/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /descargar zip/i })).toBeDisabled();

    const numberField = screen.getByLabelText(/número para/i);
    await user.type(numberField, "7");

    await waitFor(() => expect(screen.getByRole("button", { name: /descargar zip/i })).toBeEnabled());
  });

  it("shows an error banner for a zip whose root folder isn't recognized", async () => {
    const file = await buildZipFile(
      { "Resoluciones Bogota/2020/algo.pdf": "contenido" },
      "Resoluciones Bogota.zip"
    );

    const user = userEvent.setup();
    render(<FormatterPage />);
    const input = screen.getByLabelText(/seleccionar archivo zip/i);
    await user.upload(input, file);

    expect(await screen.findByText(/no se reconoce el tipo de documento o la ciudad/i)).toBeInTheDocument();
  });
});
