import type { ReactNode } from "react";
import { expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { server } from "../test/server";
import type { Document } from "../api/types";
import { AnexosDialog } from "./AnexosDialog";

const BASE_URL = "http://localhost:8000";

function wrap(ui: ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

it("lista los anexos del documento con botones de descarga", async () => {
  server.use(
    http.get(`${BASE_URL}/documents/5/anexos`, () =>
      HttpResponse.json([
        { id: 51, title: "C_SF_0020_2026_A01", nombre: "C_SF_0020_2026_A01" },
        { id: 52, title: "C_SF_0020_2026_A02", nombre: "C_SF_0020_2026_A02" },
      ])
    )
  );

  wrap(
    <AnexosDialog
      document={{ id: 5, title: "C_SF_0020_2026", nombre: "C_SF_0020_2026" } as Document}
      onClose={() => {}}
    />
  );

  expect(await screen.findByText("C_SF_0020_2026_A01")).toBeInTheDocument();
  expect(screen.getByText("C_SF_0020_2026_A02")).toBeInTheDocument();
  expect(screen.getAllByRole("button", { name: /descargar/i })).toHaveLength(2);
});

it("no renderiza nada cuando document es null", () => {
  wrap(<AnexosDialog document={null} onClose={() => {}} />);
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
});
