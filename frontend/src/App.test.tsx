import { describe, expect, it, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { clearStoredApiKey } from "./api/client";
import { App } from "./App";

describe("App", () => {
  beforeEach(() => {
    clearStoredApiKey();
    window.history.pushState({}, "", "/");
  });

  it("redirects to the login page when there is no stored API key", () => {
    render(<App />);
    expect(screen.getByPlaceholderText("API key")).toBeInTheDocument();
  });

  it("renders the Dashboard page when an API key is already stored", () => {
    localStorage.setItem("iurisync_api_key", "existing-key");
    render(<App />);
    expect(screen.getByRole("heading", { name: "Dashboard" })).toBeInTheDocument();
  });
});
