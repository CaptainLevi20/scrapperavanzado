import { beforeEach, describe, expect, it } from "vitest";
import { http, HttpResponse } from "msw";
import { server } from "../test/server";
import { clearStoredToken } from "./client";
import { fetchAllActiveSources, fetchSources, updateSource } from "./sources";

const BASE_URL = "http://localhost:8000";

describe("sources API", () => {
  beforeEach(() => clearStoredToken());

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

function makeSource(id: number) {
  return { id, family_key: "constitucional", name: `Fuente ${id}`, family_params: {}, active: true };
}

describe("fetchAllActiveSources", () => {
  it("returns a single page unchanged when it is not full", async () => {
    server.use(http.get(`${BASE_URL}/sources`, () => HttpResponse.json([makeSource(1), makeSource(2)])));

    const sources = await fetchAllActiveSources();

    expect(sources).toHaveLength(2);
  });

  it("keeps paginating past 100 items instead of truncating the result", async () => {
    server.use(
      http.get(`${BASE_URL}/sources`, ({ request }) => {
        const offset = Number(new URL(request.url).searchParams.get("offset") ?? "0");
        if (offset === 0) {
          return HttpResponse.json(Array.from({ length: 100 }, (_, index) => makeSource(index + 1)));
        }
        return HttpResponse.json([makeSource(101)]);
      })
    );

    const sources = await fetchAllActiveSources();

    expect(sources).toHaveLength(101);
    expect(sources[100].id).toBe(101);
  });
});
