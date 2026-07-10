import { beforeEach, describe, expect, it } from "vitest";
import { http, HttpResponse } from "msw";
import { server } from "../test/server";
import { clearStoredApiKey } from "./client";
import { fetchDocument, fetchDocuments } from "./documents";

const BASE_URL = "http://localhost:8000";

describe("documents API", () => {
  beforeEach(() => clearStoredApiKey());

  it("fetchDocuments sends filters and returns the paginated envelope", async () => {
    let receivedUrl = "";
    server.use(
      http.get(`${BASE_URL}/documents`, ({ request }) => {
        receivedUrl = request.url;
        return HttpResponse.json({ items: [], total: 0, limit: 50, offset: 0 });
      })
    );

    const result = await fetchDocuments({ title: "sentencia", limit: 50, offset: 0 });

    expect(receivedUrl).toContain("title=sentencia");
    expect(result.total).toBe(0);
  });

  it("fetchDocument fetches a single document by id", async () => {
    server.use(
      http.get(`${BASE_URL}/documents/3`, () =>
        HttpResponse.json({
          id: 3,
          doc_id: "abc",
          source_id: 1,
          title: "Sentencia X",
          tipo: null,
          seccion: null,
          f_public: null,
          f_providencia: null,
          storage_bucket: "iurisync-documents",
          storage_key: "abc.pdf",
          content_type: "application/pdf",
          file_size_bytes: 1024,
          downloaded_at: "2026-07-10T00:00:00Z",
        })
      )
    );

    const document = await fetchDocument(3);

    expect(document.title).toBe("Sentencia X");
  });
});
