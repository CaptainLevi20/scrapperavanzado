import { describe, expect, it, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { server } from "../test/server";
import { clearStoredToken, getStoredToken, setStoredToken } from "../api/client";
import { AuthProvider, useAuth } from "./AuthContext";

const BASE_URL = "http://localhost:8000";

function Probe() {
  const { username, token, isAdmin, isLoading, login, logout } = useAuth();
  if (isLoading) return <span data-testid="loading">loading</span>;
  return (
    <div>
      <span data-testid="token">{token ?? "none"}</span>
      <span data-testid="username">{username ?? "none"}</span>
      <span data-testid="is-admin">{String(isAdmin)}</span>
      <button onClick={() => login("new-token", "ana", true)}>login</button>
      <button onClick={() => logout()}>logout</button>
    </div>
  );
}

describe("AuthContext", () => {
  beforeEach(() => clearStoredToken());

  it("starts with no session when localStorage is empty", async () => {
    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>
    );

    expect(await screen.findByTestId("token")).toHaveTextContent("none");
  });

  it("validates a stored token against /auth/me on mount", async () => {
    setStoredToken("existing-token");
    server.use(http.get(`${BASE_URL}/auth/me`, () => HttpResponse.json({ username: "ana" })));

    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>
    );

    expect(await screen.findByTestId("username")).toHaveTextContent("ana");
    expect(screen.getByTestId("token")).toHaveTextContent("existing-token");
  });

  it("clears a stored token that /auth/me rejects", async () => {
    setStoredToken("stale-token");
    server.use(http.get(`${BASE_URL}/auth/me`, () => new HttpResponse(null, { status: 401 })));

    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>
    );

    expect(await screen.findByTestId("token")).toHaveTextContent("none");
    expect(getStoredToken()).toBeNull();
  });

  it("login stores the token/username and updates state", async () => {
    const user = userEvent.setup();
    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>
    );
    await screen.findByTestId("token");

    await user.click(screen.getByText("login"));

    expect(screen.getByTestId("token")).toHaveTextContent("new-token");
    expect(screen.getByTestId("username")).toHaveTextContent("ana");
    expect(getStoredToken()).toBe("new-token");
  });

  it("logout calls the backend, then clears the token and updates state", async () => {
    const user = userEvent.setup();
    setStoredToken("existing-token");
    server.use(
      http.get(`${BASE_URL}/auth/me`, () => HttpResponse.json({ username: "ana" })),
      http.post(`${BASE_URL}/auth/logout`, () => new HttpResponse(null, { status: 204 }))
    );
    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>
    );
    await screen.findByTestId("username");

    await user.click(screen.getByText("logout"));

    await waitFor(() => expect(screen.getByTestId("token")).toHaveTextContent("none"));
    expect(getStoredToken()).toBeNull();
  });

  it("populates isAdmin from /auth/me on mount", async () => {
    setStoredToken("existing-token");
    server.use(http.get(`${BASE_URL}/auth/me`, () => HttpResponse.json({ username: "ana", is_admin: true })));

    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>
    );

    expect(await screen.findByTestId("is-admin")).toHaveTextContent("true");
  });

  it("login updates isAdmin immediately, without waiting on /auth/me", async () => {
    const user = userEvent.setup();
    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>
    );
    await screen.findByTestId("token");

    await user.click(screen.getByText("login"));

    expect(screen.getByTestId("is-admin")).toHaveTextContent("true");
  });
});
