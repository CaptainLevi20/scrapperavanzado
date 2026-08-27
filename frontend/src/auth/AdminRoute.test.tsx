import { describe, expect, it, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { http, HttpResponse } from "msw";
import { server } from "../test/server";
import { clearStoredToken, setStoredToken } from "../api/client";
import { AuthProvider } from "./AuthContext";
import { AdminRoute } from "./AdminRoute";

const BASE_URL = "http://localhost:8000";

function renderAtLaboratorio() {
  return render(
    <MemoryRouter initialEntries={["/laboratorio"]}>
      <AuthProvider>
        <Routes>
          <Route element={<AdminRoute />}>
            <Route path="/laboratorio" element={<div>Contenido admin</div>} />
          </Route>
          <Route path="/" element={<div>Dashboard</div>} />
        </Routes>
      </AuthProvider>
    </MemoryRouter>
  );
}

describe("AdminRoute", () => {
  beforeEach(() => clearStoredToken());

  it("redirects a non-admin user to the dashboard", async () => {
    setStoredToken("existing-token");
    server.use(http.get(`${BASE_URL}/auth/me`, () => HttpResponse.json({ username: "ana", is_admin: false })));

    renderAtLaboratorio();

    expect(await screen.findByText("Dashboard")).toBeInTheDocument();
    expect(screen.queryByText("Contenido admin")).not.toBeInTheDocument();
  });

  it("renders the protected content for an admin user", async () => {
    setStoredToken("existing-token");
    server.use(http.get(`${BASE_URL}/auth/me`, () => HttpResponse.json({ username: "ana", is_admin: true })));

    renderAtLaboratorio();

    expect(await screen.findByText("Contenido admin")).toBeInTheDocument();
  });
});
