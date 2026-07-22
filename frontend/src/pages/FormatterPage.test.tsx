import { describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import JSZip from "jszip";
import { FormatterPage } from "./FormatterPage";
import { buildFormattedZip } from "../lib/formatter/build";

// Keeps the real implementation by default so unrelated tests still exercise
// actual zip-building; individual tests can override it with mockRejectedValueOnce.
vi.mock("../lib/formatter/build", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../lib/formatter/build")>();
  return { ...actual, buildFormattedZip: vi.fn(actual.buildFormattedZip) };
});

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

  it("shows an error banner instead of getting stuck on 'Generando el ZIP…' when the build fails", async () => {
    const file = await buildZipFile({
      "Acuerdos Cali/ACUERDOS 1962/Acuerdo 0005 de 1962.pdf": "contenido",
    });
    vi.mocked(buildFormattedZip).mockRejectedValueOnce(new Error("boom"));

    const user = userEvent.setup();
    render(<FormatterPage />);
    const input = screen.getByLabelText(/seleccionar archivo zip/i);
    await user.upload(input, file);

    const downloadButton = await screen.findByRole("button", { name: /descargar zip/i });
    expect(downloadButton).toBeEnabled();
    await user.click(downloadButton);

    expect(await screen.findByText(/no se pudo generar el zip/i)).toBeInTheDocument();
    expect(screen.queryByText(/generando el zip/i)).not.toBeInTheDocument();
  });
});
