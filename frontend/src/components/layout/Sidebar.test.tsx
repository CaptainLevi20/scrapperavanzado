import { describe, expect, it, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { server } from "../../test/server";
import { clearStoredToken, getStoredToken, setStoredToken } from "../../api/client";
import { AuthProvider } from "../../auth/AuthContext";
import { Sidebar } from "./Sidebar";

const BASE_URL = "http://localhost:8000";

function renderSidebar() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <AuthProvider>
          <Sidebar />
        </AuthProvider>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("Sidebar", () => {
  beforeEach(() => clearStoredToken());

  it("shows the logged-in username", async () => {
    setStoredToken("existing-token");
    server.use(http.get(`${BASE_URL}/auth/me`, () => HttpResponse.json({ username: "ana" })));

    renderSidebar();

    expect(await screen.findByText("ana")).toBeInTheDocument();
  });

  it("hides the Laboratorio link for a non-admin user", async () => {
    setStoredToken("existing-token");
    server.use(http.get(`${BASE_URL}/auth/me`, () => HttpResponse.json({ username: "ana", is_admin: false })));

    renderSidebar();

    await screen.findByText("ana");
    expect(screen.queryByText("Laboratorio")).not.toBeInTheDocument();
  });

  it("shows the Laboratorio link for an admin user", async () => {
    setStoredToken("existing-token");
    server.use(http.get(`${BASE_URL}/auth/me`, () => HttpResponse.json({ username: "ana", is_admin: true })));

    renderSidebar();

    expect(await screen.findByText("Laboratorio")).toBeInTheDocument();
  });

  it("calls the backend logout endpoint before clearing the local session", async () => {
    setStoredToken("existing-token");
    let logoutCalled = false;
    server.use(
      http.get(`${BASE_URL}/auth/me`, () => HttpResponse.json({ username: "ana" })),
      http.post(`${BASE_URL}/auth/logout`, () => {
        logoutCalled = true;
        return new HttpResponse(null, { status: 204 });
      })
    );
    const user = userEvent.setup();
    renderSidebar();
    await screen.findByText("ana");

    await user.click(screen.getByText("Cerrar sesión"));

    await waitFor(() => expect(logoutCalled).toBe(true));
    expect(getStoredToken()).toBeNull();
  });

  it("opens the change password dialog and submits a valid change", async () => {
    setStoredToken("existing-token");
    let changeBody: unknown = null;
    server.use(
      http.get(`${BASE_URL}/auth/me`, () => HttpResponse.json({ username: "ana" })),
      http.post(`${BASE_URL}/auth/change-password`, async ({ request }) => {
        changeBody = await request.json();
        return new HttpResponse(null, { status: 204 });
      })
    );
    const user = userEvent.setup();
    renderSidebar();
    await screen.findByText("ana");

    await user.click(screen.getByText("Cambiar contraseña"));
    await user.type(screen.getByLabelText("Contraseña actual"), "OldPassword1");
    await user.type(screen.getByLabelText("Nueva contraseña"), "NewPassword2");
    await user.type(screen.getByLabelText("Confirmar nueva contraseña"), "NewPassword2");
    await user.click(screen.getByText("Guardar"));

    expect(await screen.findByText("Contraseña actualizada.")).toBeInTheDocument();
    expect(changeBody).toEqual({ current_password: "OldPassword1", new_password: "NewPassword2" });
  });

  it("shows an error when the new passwords don't match, without calling the API", async () => {
    setStoredToken("existing-token");
    let called = false;
    server.use(
      http.get(`${BASE_URL}/auth/me`, () => HttpResponse.json({ username: "ana" })),
      http.post(`${BASE_URL}/auth/change-password`, () => {
        called = true;
        return new HttpResponse(null, { status: 204 });
      })
    );
    const user = userEvent.setup();
    renderSidebar();
    await screen.findByText("ana");

    await user.click(screen.getByText("Cambiar contraseña"));
    await user.type(screen.getByLabelText("Contraseña actual"), "OldPassword1");
    await user.type(screen.getByLabelText("Nueva contraseña"), "NewPassword2");
    await user.type(screen.getByLabelText("Confirmar nueva contraseña"), "Different3");
    await user.click(screen.getByText("Guardar"));

    expect(await screen.findByText("Las contraseñas no coinciden")).toBeInTheDocument();
    expect(called).toBe(false);
  });

  it("shows the backend's error and keeps the session when the current password is wrong", async () => {
    setStoredToken("existing-token");
    server.use(
      http.get(`${BASE_URL}/auth/me`, () => HttpResponse.json({ username: "ana" })),
      http.post(`${BASE_URL}/auth/change-password`, () =>
        HttpResponse.json({ detail: "La contraseña actual no es correcta" }, { status: 401 })
      )
    );
    const user = userEvent.setup();
    renderSidebar();
    await screen.findByText("ana");

    await user.click(screen.getByText("Cambiar contraseña"));
    await user.type(screen.getByLabelText("Contraseña actual"), "WrongPassword1");
    await user.type(screen.getByLabelText("Nueva contraseña"), "NewPassword2");
    await user.type(screen.getByLabelText("Confirmar nueva contraseña"), "NewPassword2");
    await user.click(screen.getByText("Guardar"));

    expect(await screen.findByText("La contraseña actual no es correcta")).toBeInTheDocument();
    expect(getStoredToken()).toBe("existing-token");
    expect(screen.getByText("ana")).toBeInTheDocument();
  });
});
