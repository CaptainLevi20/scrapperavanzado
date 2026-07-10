import { describe, expect, it, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { http, HttpResponse } from "msw";
import { server } from "../test/server";
import { clearStoredApiKey, getStoredApiKey } from "../api/client";
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
  beforeEach(() => clearStoredApiKey());

  it("stores the key and clears the error on a valid key", async () => {
    const user = userEvent.setup();
    server.use(http.get(`${BASE_URL}/source-families`, () => HttpResponse.json([])));
    renderLoginPage();

    await user.type(screen.getByPlaceholderText("API key"), "good-key");
    await user.click(screen.getByRole("button", { name: /entrar/i }));

    expect(await screen.findByRole("button", { name: /entrar/i })).toBeEnabled();
    expect(getStoredApiKey()).toBe("good-key");
  });

  it("shows an error and does not store the key on an invalid key", async () => {
    const user = userEvent.setup();
    server.use(http.get(`${BASE_URL}/source-families`, () => new HttpResponse(null, { status: 401 })));
    renderLoginPage();

    await user.type(screen.getByPlaceholderText("API key"), "bad-key");
    await user.click(screen.getByRole("button", { name: /entrar/i }));

    expect(await screen.findByText("API key inválida")).toBeInTheDocument();
    expect(getStoredApiKey()).toBeNull();
  });
});
