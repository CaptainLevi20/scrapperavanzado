import { describe, expect, it, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { server } from "./test/server";
import { clearStoredToken, setStoredToken } from "./api/client";
import { App } from "./App";

const BASE_URL = "http://localhost:8000";

describe("App", () => {
  beforeEach(() => {
    clearStoredToken();
    window.history.pushState({}, "", "/");
  });

  it("redirects to the login page when there is no stored session", async () => {
    render(<App />);
    expect(await screen.findByPlaceholderText("Usuario")).toBeInTheDocument();
  });

  it("renders the Dashboard page when a valid session is already stored", async () => {
    setStoredToken("existing-token");
    server.use(http.get(`${BASE_URL}/auth/me`, () => HttpResponse.json({ username: "ana" })));

    render(<App />);

    expect(await screen.findByRole("heading", { name: "Dashboard" })).toBeInTheDocument();
  });
});
