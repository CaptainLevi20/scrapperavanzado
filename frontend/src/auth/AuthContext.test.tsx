import { describe, expect, it, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { clearStoredApiKey, getStoredApiKey } from "../api/client";
import { AuthProvider, useAuth } from "./AuthContext";

function Probe() {
  const { apiKey, login, logout } = useAuth();
  return (
    <div>
      <span data-testid="key">{apiKey ?? "none"}</span>
      <button onClick={() => login("new-key")}>login</button>
      <button onClick={() => logout()}>logout</button>
    </div>
  );
}

describe("AuthContext", () => {
  beforeEach(() => clearStoredApiKey());

  it("starts with the key already in localStorage, if any", () => {
    localStorage.setItem("iurisync_api_key", "existing-key");
    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>
    );
    expect(screen.getByTestId("key")).toHaveTextContent("existing-key");
  });

  it("login stores the key and updates state", async () => {
    const user = userEvent.setup();
    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>
    );

    await user.click(screen.getByText("login"));

    expect(screen.getByTestId("key")).toHaveTextContent("new-key");
    expect(getStoredApiKey()).toBe("new-key");
  });

  it("logout clears the key and updates state", async () => {
    const user = userEvent.setup();
    localStorage.setItem("iurisync_api_key", "existing-key");
    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>
    );

    await user.click(screen.getByText("logout"));

    expect(screen.getByTestId("key")).toHaveTextContent("none");
    expect(getStoredApiKey()).toBeNull();
  });
});
