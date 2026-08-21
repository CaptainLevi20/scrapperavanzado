import { beforeEach, describe, expect, it } from "vitest";
import { http, HttpResponse } from "msw";
import { server } from "../test/server";
import { clearStoredToken } from "./client";
import { cancelRun, createRun, fetchRun, fetchRunSources, fetchRuns, retryFailedRunSources } from "./runs";

const BASE_URL = "http://localhost:8000";

describe("runs API", () => {
  beforeEach(() => clearStoredToken());

  it("fetchRuns sends the status filter as a query param", async () => {
    let receivedUrl = "";
    server.use(
      http.get(`${BASE_URL}/runs`, ({ request }) => {
        receivedUrl = request.url;
        return HttpResponse.json([]);
      })
    );

    await fetchRuns({ status_filter: "running", limit: 10, offset: 0 });

    expect(receivedUrl).toContain("status_filter=running");
  });

  it("fetchRun fetches a single run by id", async () => {
    server.use(
      http.get(`${BASE_URL}/runs/7`, () =>
        HttpResponse.json({
          id: 7,
          triggered_by: "manual",
          status: "running",
          fini: null,
          ffin: null,
          cancel_requested: false,
          started_at: null,
          finished_at: null,
          created_at: "2026-07-10T00:00:00Z",
        })
      )
    );

    const run = await fetchRun(7);

    expect(run.id).toBe(7);
    expect(run.status).toBe("running");
  });

  it("fetchRunSources fetches the run's sources", async () => {
    server.use(
      http.get(`${BASE_URL}/runs/7/sources`, () =>
        HttpResponse.json([{ id: 1, run_id: 7, source_id: 2, status: "completed", docs_new: 3, docs_errors: 0, error_message: null }])
      )
    );

    const runSources = await fetchRunSources(7);

    expect(runSources).toHaveLength(1);
    expect(runSources[0].source_id).toBe(2);
  });

  it("createRun posts optional source_ids and date range", async () => {
    let body: unknown;
    server.use(
      http.post(`${BASE_URL}/runs`, async ({ request }) => {
        body = await request.json();
        return HttpResponse.json(
          { id: 1, triggered_by: "manual", status: "pending", fini: null, ffin: null, cancel_requested: false, started_at: null, finished_at: null, created_at: "2026-07-10T00:00:00Z" },
          { status: 202 }
        );
      })
    );

    await createRun({ source_ids: [1, 2], fini: "2026-01-01" });

    expect(body).toMatchObject({ source_ids: [1, 2], fini: "2026-01-01" });
  });

  it("cancelRun posts to the cancel endpoint", async () => {
    let method = "";
    server.use(
      http.post(`${BASE_URL}/runs/9/cancel`, ({ request }) => {
        method = request.method;
        return HttpResponse.json({ id: 9, triggered_by: "manual", status: "running", fini: null, ffin: null, cancel_requested: true, started_at: null, finished_at: null, created_at: "2026-07-10T00:00:00Z" });
      })
    );

    const run = await cancelRun(9);

    expect(method).toBe("POST");
    expect(run.cancel_requested).toBe(true);
  });

  it("retryFailedRunSources posts to the retry-failed endpoint", async () => {
    let method = "";
    server.use(
      http.post(`${BASE_URL}/runs/9/retry-failed`, ({ request }) => {
        method = request.method;
        return HttpResponse.json({ id: 9, triggered_by: "manual", status: "running", fini: null, ffin: null, cancel_requested: false, started_at: null, finished_at: null, created_at: "2026-07-10T00:00:00Z" });
      })
    );

    const run = await retryFailedRunSources(9);

    expect(method).toBe("POST");
    expect(run.status).toBe("running");
  });
});
