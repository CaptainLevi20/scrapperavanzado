import { describe, expect, it, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { http, HttpResponse } from "msw";
import { server } from "../test/server";
import { clearStoredToken, getStoredToken } from "../api/client";
import { AuthProvider } from "../auth/AuthContext";
import { RegisterPage } from "./RegisterPage";

const BASE_URL = "http://localhost:8000";

function renderRegisterPage() {
  return render(
    <MemoryRouter>
      <AuthProvider>
        <RegisterPage />
      </AuthProvider>
    </MemoryRouter>
  );
}

describe("RegisterPage", () => {
  beforeEach(() => clearStoredToken());

  it("registers and logs in automatically on success", async () => {
    const user = userEvent.setup();
    let sentBody: unknown = null;
    server.use(
      http.post(`${BASE_URL}/auth/register`, async ({ request }) => {
        sentBody = await request.json();
        return HttpResponse.json({ token: "new-token", username: "ana" });
      })
    );
    renderRegisterPage();

    await user.type(screen.getByPlaceholderText("Usuario"), "ana");
    await user.type(screen.getByPlaceholderText("Mínimo 8 caracteres"), "Password123");
    await user.type(screen.getByPlaceholderText("Repite la contraseña"), "Password123");
    await user.type(screen.getByPlaceholderText("Código de invitación"), "equipo-2026");
    await user.click(screen.getByRole("button", { name: /crear cuenta/i }));

    expect(await screen.findByRole("button", { name: /crear cuenta/i })).toBeEnabled();
    expect(getStoredToken()).toBe("new-token");
    expect(sentBody).toEqual({ username: "ana", password: "Password123", invite_code: "equipo-2026" });
  });

  it("shows an error when the passwords don't match, without calling the API", async () => {
    const user = userEvent.setup();
    let called = false;
    server.use(
      http.post(`${BASE_URL}/auth/register`, () => {
        called = true;
        return HttpResponse.json({ token: "x", username: "ana" });
      })
    );
    renderRegisterPage();

    await user.type(screen.getByPlaceholderText("Usuario"), "ana");
    await user.type(screen.getByPlaceholderText("Mínimo 8 caracteres"), "Password123");
    await user.type(screen.getByPlaceholderText("Repite la contraseña"), "Different456");
    await user.type(screen.getByPlaceholderText("Código de invitación"), "equipo-2026");
    await user.click(screen.getByRole("button", { name: /crear cuenta/i }));

    expect(await screen.findByText("Las contraseñas no coinciden")).toBeInTheDocument();
    expect(called).toBe(false);
  });

  it("shows the backend's error on an invalid invite code", async () => {
    const user = userEvent.setup();
    server.use(
      http.post(`${BASE_URL}/auth/register`, () =>
        HttpResponse.json({ detail: "Código de invitación inválido" }, { status: 401 })
      )
    );
    renderRegisterPage();

    await user.type(screen.getByPlaceholderText("Usuario"), "ana");
    await user.type(screen.getByPlaceholderText("Mínimo 8 caracteres"), "Password123");
    await user.type(screen.getByPlaceholderText("Repite la contraseña"), "Password123");
    await user.type(screen.getByPlaceholderText("Código de invitación"), "wrong-code");
    await user.click(screen.getByRole("button", { name: /crear cuenta/i }));

    expect(await screen.findByText("Código de invitación inválido")).toBeInTheDocument();
    expect(getStoredToken()).toBeNull();
  });
});
