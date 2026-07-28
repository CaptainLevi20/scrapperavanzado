import { beforeEach, describe, expect, it } from "vitest";
import { http, HttpResponse } from "msw";
import { server } from "../test/server";
import {
  ApiError,
  apiFetch,
  buildQuery,
  clearStoredToken,
  getStoredToken,
  registerUnauthorizedHandler,
  setStoredToken,
} from "./client";

const BASE_URL = "http://localhost:8000";

describe("apiFetch", () => {
  beforeEach(() => {
    clearStoredToken();
    registerUnauthorizedHandler(() => {});
  });

  it("sends the stored session token as a Bearer Authorization header", async () => {
    setStoredToken("test-token");
    let receivedHeader: string | null = null;
    server.use(
      http.get(`${BASE_URL}/source-families`, ({ request }) => {
        receivedHeader = request.headers.get("authorization");
        return HttpResponse.json([]);
      })
    );

    await apiFetch("/source-families");

    expect(receivedHeader).toBe("Bearer test-token");
  });

  it("throws ApiError with the backend's detail message on a 4xx response", async () => {
    server.use(
      http.post(`${BASE_URL}/sources`, () =>
        HttpResponse.json({ detail: "Familia técnica desconocida: x" }, { status: 400 })
      )
    );

    await expect(apiFetch("/sources", { method: "POST", body: "{}" })).rejects.toMatchObject({
      status: 400,
      message: "Familia técnica desconocida: x",
    });
  });

  it("clears the stored token and notifies the unauthorized handler on a 401 when a token was sent", async () => {
    setStoredToken("bad-token");
    let notified = false;
    registerUnauthorizedHandler(() => {
      notified = true;
    });
    server.use(http.get(`${BASE_URL}/source-families`, () => new HttpResponse(null, { status: 401 })));

    await expect(apiFetch("/source-families")).rejects.toBeInstanceOf(ApiError);
    expect(getStoredToken()).toBeNull();
    expect(notified).toBe(true);
  });

  it("does not clear session state on a 401 when no token was sent (e.g. a failed login attempt)", async () => {
    let notified = false;
    registerUnauthorizedHandler(() => {
      notified = true;
    });
    server.use(
      http.post(`${BASE_URL}/auth/login`, () =>
        HttpResponse.json({ detail: "Usuario o contraseña incorrectos" }, { status: 401 })
      )
    );

    await expect(apiFetch("/auth/login", { method: "POST", body: "{}" })).rejects.toMatchObject({
      status: 401,
      message: "Usuario o contraseña incorrectos",
    });
    expect(notified).toBe(false);
  });

  it("does not clear a newer session when a stale request (sent with an old, now-replaced token) resolves late with a 401", async () => {
    // Regression test: a request captures the token at the start. If the user
    // logs back in (a fresh token gets stored) before this request's 401
    // response comes back, the stale response must not log the user out of
    // the brand-new, valid session it raced against.
    setStoredToken("old-token");
    let notified = false;
    registerUnauthorizedHandler(() => {
      notified = true;
    });
    server.use(
      http.get(`${BASE_URL}/source-families`, () => {
        setStoredToken("new-token");
        return new HttpResponse(null, { status: 401 });
      })
    );

    await expect(apiFetch("/source-families")).rejects.toBeInstanceOf(ApiError);

    expect(getStoredToken()).toBe("new-token");
    expect(notified).toBe(false);
  });

  it("does not clear the token or notify on a 401 when skipUnauthorizedHandling is set (e.g. change-password with a wrong current password)", async () => {
    setStoredToken("existing-token");
    let notified = false;
    registerUnauthorizedHandler(() => {
      notified = true;
    });
    server.use(
      http.post(`${BASE_URL}/auth/change-password`, () =>
        HttpResponse.json({ detail: "La contraseña actual no es correcta" }, { status: 401 })
      )
    );

    await expect(
      apiFetch("/auth/change-password", { method: "POST", body: "{}" }, { skipUnauthorizedHandling: true })
    ).rejects.toMatchObject({
      status: 401,
      message: "La contraseña actual no es correcta",
    });
    expect(getStoredToken()).toBe("existing-token");
    expect(notified).toBe(false);
  });
});

describe("buildQuery", () => {
  it("builds a query string skipping undefined values", () => {
    expect(buildQuery({ a: 1, b: undefined, c: "x" })).toBe("?a=1&c=x");
  });

  it("returns an empty string when there are no defined params", () => {
    expect(buildQuery({ a: undefined })).toBe("");
  });
});
