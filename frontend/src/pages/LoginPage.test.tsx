import { describe, expect, it, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { http, HttpResponse } from "msw";
import { server } from "../test/server";
import { clearStoredToken, getStoredToken } from "../api/client";
import { AuthProvider } from "../auth/AuthContext";
import { LoginPage } from "./LoginPage";

const BASE_URL = "http://localhost:8000";

function renderLoginPage() {
  return render(
    <MemoryRouter>
      <AuthProvider>
        <LoginPage />
      </AuthProvider>
    </MemoryRouter>
  );
}

describe("LoginPage", () => {
  beforeEach(() => clearStoredToken());

  it("logs in with valid credentials and stores the returned session", async () => {
    const user = userEvent.setup();
    server.use(
      http.post(`${BASE_URL}/auth/login`, () => HttpResponse.json({ token: "new-token", username: "ana" }))
    );
    renderLoginPage();

    await user.type(screen.getByPlaceholderText("Usuario"), "ana");
    await user.type(screen.getByPlaceholderText("Contraseña"), "Password123");
    await user.click(screen.getByRole("button", { name: /entrar/i }));

    expect(await screen.findByRole("button", { name: /entrar/i })).toBeEnabled();
    expect(getStoredToken()).toBe("new-token");
  });

  it("shows an error and does not store a session on invalid credentials", async () => {
    const user = userEvent.setup();
    server.use(
      http.post(`${BASE_URL}/auth/login`, () =>
        HttpResponse.json({ detail: "Usuario o contraseña incorrectos" }, { status: 401 })
      )
    );
    renderLoginPage();

    await user.type(screen.getByPlaceholderText("Usuario"), "ana");
    await user.type(screen.getByPlaceholderText("Contraseña"), "wrong-password");
    await user.click(screen.getByRole("button", { name: /entrar/i }));

    expect(await screen.findByText("Usuario o contraseña incorrectos")).toBeInTheDocument();
    expect(getStoredToken()).toBeNull();
  });
});
