import { beforeEach, describe, expect, it, vi } from "vitest";
import { http, HttpResponse } from "msw";
import { server } from "../test/server";
import { clearStoredApiKey } from "./client";
import { buildDownloadFilename, downloadDocumentFile, fetchDocument, fetchDocuments } from "./documents";
import type { Document } from "./types";

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
          especialidad: null,
          magistrado: null,
          detalle: null,
          f_public: null,
          f_providencia: null,
          source_url: null,
          storage_bucket: "iurisync-documents",
          storage_key: "abc.pdf",
          content_type: "application/pdf",
          file_size_bytes: 1024,
          review_status: "pending",
          reviewed_at: null,
          downloaded_at: "2026-07-10T00:00:00Z",
        })
      )
    );

    const document = await fetchDocument(3);

    expect(document.title).toBe("Sentencia X");
  });
});

describe("downloadDocumentFile", () => {
  it("fetches the file and triggers a browser download", async () => {
    server.use(
      http.get(`${BASE_URL}/documents/1/download`, () => new HttpResponse(new Blob(["contenido"], { type: "application/pdf" })))
    );
    const clickSpy = vi.fn();
    const originalCreateElement = document.createElement.bind(document);
    vi.spyOn(document, "createElement").mockImplementation((tag: string) => {
      const element = originalCreateElement(tag);
      if (tag === "a") element.click = clickSpy;
      return element;
    });

    await downloadDocumentFile(1, "sentencia.pdf");

    expect(clickSpy).toHaveBeenCalledOnce();
  });

  it("throws when the download request fails", async () => {
    server.use(http.get(`${BASE_URL}/documents/2/download`, () => new HttpResponse(null, { status: 404 })));

    await expect(downloadDocumentFile(2, "x.pdf")).rejects.toThrow();
  });
});

function makeDocument(overrides: Partial<Document> = {}): Document {
  return {
    id: 1,
    doc_id: "abc",
    source_id: 1,
    title: "Sentencia X",
    tipo: null,
    seccion: null,
    especialidad: null,
    magistrado: null,
    detalle: null,
    f_public: null,
    f_providencia: null,
    source_url: null,
    storage_bucket: "iurisync-documents",
    storage_key: "abc123.pdf",
    content_type: "application/pdf",
    file_size_bytes: 1024,
    review_status: "pending",
    reviewed_at: null,
    downloaded_at: "2026-07-10T00:00:00Z",
    ...overrides,
  };
}

describe("buildDownloadFilename", () => {
  it("derives the extension from a recognizable storage_key extension", () => {
    const document = makeDocument({ title: "Sentencia X", storage_key: "abc123.pdf" });

    expect(buildDownloadFilename(document)).toBe("Sentencia X.pdf");
  });

  it("falls back to the content_type map when storage_key has no recognizable extension", () => {
    const document = makeDocument({
      title: "Reporte",
      storage_key: "some-opaque-key-without-extension",
      content_type: "text/plain",
    });

    expect(buildDownloadFilename(document)).toBe("Reporte.txt");
  });

  it("omits the extension entirely when neither storage_key nor content_type yield one", () => {
    const document = makeDocument({
      title: "Sin extension",
      storage_key: "opaque-key",
      content_type: "application/octet-stream",
    });

    expect(buildDownloadFilename(document)).toBe("Sin extension");
  });

  it("sanitizes a title containing a slash", () => {
    const document = makeDocument({ title: "Auto 123/2026", storage_key: "abc123.pdf" });

    expect(buildDownloadFilename(document)).toBe("Auto 123-2026.pdf");
  });
});
