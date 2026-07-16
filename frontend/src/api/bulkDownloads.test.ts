import { describe, expect, it } from "vitest";
import { http, HttpResponse } from "msw";
import { server } from "../test/server";
import { createBulkDownload, fetchBulkDownloadUrl, fetchBulkDownloads } from "./bulkDownloads";

const BASE_URL = "http://localhost:8000";

const BULK_DOWNLOAD = {
  id: 1,
  status: "pending",
  document_count: 0,
  failed_count: 0,
  error_message: null,
  started_at: null,
  finished_at: null,
  created_at: "2026-07-16T00:00:00Z",
};

describe("createBulkDownload", () => {
  it("posts to /bulk-downloads and returns the created row", async () => {
    server.use(http.post(`${BASE_URL}/bulk-downloads`, () => HttpResponse.json(BULK_DOWNLOAD, { status: 202 })));

    const result = await createBulkDownload();

    expect(result).toEqual(BULK_DOWNLOAD);
  });
});

describe("fetchBulkDownloads", () => {
  it("gets the list from /bulk-downloads", async () => {
    server.use(http.get(`${BASE_URL}/bulk-downloads`, () => HttpResponse.json([BULK_DOWNLOAD])));

    const result = await fetchBulkDownloads();

    expect(result).toEqual([BULK_DOWNLOAD]);
  });
});

describe("fetchBulkDownloadUrl", () => {
  it("returns the presigned url from /bulk-downloads/:id/download", async () => {
    server.use(
      http.get(`${BASE_URL}/bulk-downloads/1/download`, () =>
        HttpResponse.json({ url: "https://signed.example.com/bulk-downloads/1.zip" })
      )
    );

    const result = await fetchBulkDownloadUrl(1);

    expect(result).toBe("https://signed.example.com/bulk-downloads/1.zip");
  });
});
