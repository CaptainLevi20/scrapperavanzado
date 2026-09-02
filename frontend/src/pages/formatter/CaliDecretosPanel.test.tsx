import { describe, expect, it } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { server } from "../../test/server";
import { CaliDecretosPanel } from "./CaliDecretosPanel";

const BASE_URL = "http://localhost:8000";

function estado(overrides: Record<string, unknown> = {}) {
  return {
    version: 1,
    estado: "en_curso",
    iniciado: "2026-09-02T14:00:00Z",
    actualizado: "2026-09-02T14:05:00Z",
    terminado: null,
    total_registros_sitio: 71969,
    total_paginas: 7195,
    ultima_pagina_completada: 100,
    descargados: 990,
    ya_existian: 0,
    duplicados: 2,
    fallidos_count: 3,
    avisos_count: 0,
    detener_solicitado: false,
    concurrencia_actual: 8,
    avisos: [],
    fallidos: [],
    ...overrides,
  };
}

describe("CaliDecretosPanel", () => {
  it("starts a download and shows progress", async () => {
    server.use(
      http.get(`${BASE_URL}/cali-decretos/status`, () => new HttpResponse(null, { status: 404 })),
      http.post(`${BASE_URL}/cali-decretos/start`, () => HttpResponse.json(estado())),
    );
    const user = userEvent.setup();
    render(<CaliDecretosPanel />);

    await user.type(screen.getByLabelText("Carpeta de destino"), "/descargas/cali");
    await user.click(screen.getByRole("button", { name: "Iniciar" }));

    expect(await screen.findByText(/Página 100 de 7\.195/)).toBeInTheDocument();
    expect(screen.getByText("990")).toBeInTheDocument(); // descargados
    expect(screen.getByRole("button", { name: "Detener" })).toBeInTheDocument();
  });

  it("shows the summary and a retry button for terminado_con_fallos", async () => {
    server.use(
      http.get(`${BASE_URL}/cali-decretos/status`, () =>
        HttpResponse.json(
          estado({
            estado: "terminado_con_fallos",
            ultima_pagina_completada: 7195,
            descargados: 71900,
            fallidos_count: 69,
            fallidos: [
              { numero: "0044", anio: 1984, url: "ftp://x/y.pdf", motivo: "ftp-no-disponible", intentos: 4 },
            ],
          }),
        ),
      ),
    );
    const user = userEvent.setup();
    render(<CaliDecretosPanel />);
    await user.type(screen.getByLabelText("Carpeta de destino"), "/descargas/cali");
    await user.tab(); // triggers onBlur → status fetch

    expect(await screen.findByText(/Terminado con fallos/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Reintentar fallidos" })).toBeInTheDocument();
    expect(screen.getByText(/1 por FTP no disponible/)).toBeInTheDocument();
  });

  it("stops a running download", async () => {
    server.use(
      http.get(`${BASE_URL}/cali-decretos/status`, () => HttpResponse.json(estado())),
      http.post(`${BASE_URL}/cali-decretos/stop`, () =>
        HttpResponse.json(estado({ estado: "detenido", detener_solicitado: true })),
      ),
    );
    const user = userEvent.setup();
    render(<CaliDecretosPanel />);
    await user.type(screen.getByLabelText("Carpeta de destino"), "/descargas/cali");
    await user.tab();

    await user.click(await screen.findByRole("button", { name: "Detener" }));
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Reanudar" })).toBeInTheDocument(),
    );
  });
});
