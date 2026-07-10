import { beforeEach, describe, expect, it } from "vitest";
import { http, HttpResponse } from "msw";
import { server } from "../test/server";
import {
  ApiError,
  apiFetch,
  buildQuery,
  clearStoredApiKey,
  getStoredApiKey,
  registerUnauthorizedHandler,
  setStoredApiKey,
} from "./client";

const BASE_URL = "http://localhost:8000";

describe("apiFetch", () => {
  beforeEach(() => {
    clearStoredApiKey();
    registerUnauthorizedHandler(() => {});
  });

  it("sends the stored API key as the X-API-Key header", async () => {
    setStoredApiKey("test-key");
    let receivedHeader: string | null = null;
    server.use(
      http.get(`${BASE_URL}/source-families`, ({ request }) => {
        receivedHeader = request.headers.get("x-api-key");
        return HttpResponse.json([]);
      })
    );

    await apiFetch("/source-families");

    expect(receivedHeader).toBe("test-key");
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

  it("clears the stored key and notifies the unauthorized handler on a 401", async () => {
    setStoredApiKey("bad-key");
    let notified = false;
    registerUnauthorizedHandler(() => {
      notified = true;
    });
    server.use(http.get(`${BASE_URL}/source-families`, () => new HttpResponse(null, { status: 401 })));

    await expect(apiFetch("/source-families")).rejects.toBeInstanceOf(ApiError);
    expect(getStoredApiKey()).toBeNull();
    expect(notified).toBe(true);
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
