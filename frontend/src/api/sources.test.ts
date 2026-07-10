import { beforeEach, describe, expect, it } from "vitest";
import { http, HttpResponse } from "msw";
import { server } from "../test/server";
import { clearStoredApiKey } from "./client";
import { createSource, fetchSources, updateSource } from "./sources";

const BASE_URL = "http://localhost:8000";

describe("sources API", () => {
  beforeEach(() => clearStoredApiKey());

  it("fetchSources sends filters as query params", async () => {
    let receivedUrl = "";
    server.use(
      http.get(`${BASE_URL}/sources`, ({ request }) => {
        receivedUrl = request.url;
        return HttpResponse.json([]);
      })
    );

    await fetchSources({ family_key: "constitucional", active: true, limit: 20, offset: 0 });

    expect(receivedUrl).toContain("family_key=constitucional");
    expect(receivedUrl).toContain("active=true");
  });

  it("createSource posts the payload and returns the created source", async () => {
    server.use(
      http.post(`${BASE_URL}/sources`, async ({ request }) => {
        const body = await request.json();
        return HttpResponse.json({ id: 1, ...(body as object) }, { status: 201 });
      })
    );

    const result = await createSource({
      family_key: "constitucional",
      name: "Corte Constitucional",
      family_params: {},
      active: true,
    });

    expect(result.id).toBe(1);
    expect(result.name).toBe("Corte Constitucional");
  });

  it("updateSource sends a PATCH to the source's id", async () => {
    let method = "";
    server.use(
      http.patch(`${BASE_URL}/sources/5`, ({ request }) => {
        method = request.method;
        return HttpResponse.json({ id: 5, family_key: "constitucional", name: "x", family_params: {}, active: false });
      })
    );

    const result = await updateSource(5, { active: false });

    expect(method).toBe("PATCH");
    expect(result.active).toBe(false);
  });
});
