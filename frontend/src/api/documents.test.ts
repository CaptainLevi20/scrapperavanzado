import { beforeEach, describe, expect, it, vi } from "vitest";
import { http, HttpResponse } from "msw";
import { server } from "../test/server";
import { clearStoredToken } from "./client";
import {
  buildDownloadFilename,
  buildVersionDownloadFilename,
  downloadDocumentFile,
  downloadFromUrl,
  fetchDocument,
  fetchDocumentBlob,
  fetchDocumentEspecialidades,
  fetchDocumentMagistrados,
  fetchDocumentPreviewUrl,
  fetchDocumentSecciones,
  fetchDocumentTipos,
  fetchDocuments,
  fetchDocumentVersions,
  fetchDocumentVersionUrl,
} from "./documents";
import type { Document } from "./types";

const BASE_URL = "http://localhost:8000";

describe("documents API", () => {
  beforeEach(() => clearStoredToken());

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

  it("fetchDocumentTipos fetches the distinct list of tipos", async () => {
    server.use(http.get(`${BASE_URL}/documents/tipos`, () => HttpResponse.json(["Auto", "Sentencia"])));

    const tipos = await fetchDocumentTipos();

    expect(tipos).toEqual(["Auto", "Sentencia"]);
  });

  it("fetchDocumentSecciones fetches the distinct list of secciones, scoped by tipo", async () => {
    let receivedUrl = "";
    server.use(
      http.get(`${BASE_URL}/documents/secciones`, ({ request }) => {
        receivedUrl = request.url;
        return HttpResponse.json(["SECCION PRIMERA", "SECCION SEGUNDA"]);
      })
    );

    const secciones = await fetchDocumentSecciones(1, "Sentencia");

    expect(secciones).toEqual(["SECCION PRIMERA", "SECCION SEGUNDA"]);
    expect(receivedUrl).toContain("source_id=1");
    expect(receivedUrl).toContain("tipo=Sentencia");
  });

  it("fetchDocumentEspecialidades fetches the distinct list of especialidades, scoped by seccion", async () => {
    let receivedUrl = "";
    server.use(
      http.get(`${BASE_URL}/documents/especialidades`, ({ request }) => {
        receivedUrl = request.url;
        return HttpResponse.json(["Nulidad"]);
      })
    );

    const especialidades = await fetchDocumentEspecialidades(1, "Sentencia", "SECCION PRIMERA");

    expect(especialidades).toEqual(["Nulidad"]);
    expect(receivedUrl).toContain("seccion=SECCION+PRIMERA");
  });

  it("fetchDocumentMagistrados fetches the distinct list of magistrados, scoped by especialidad", async () => {
    let receivedUrl = "";
    server.use(
      http.get(`${BASE_URL}/documents/magistrados`, ({ request }) => {
        receivedUrl = request.url;
        return HttpResponse.json(["Ana Pérez"]);
      })
    );

    const magistrados = await fetchDocumentMagistrados(1, "Sentencia", "SECCION PRIMERA", "Nulidad");

    expect(magistrados).toEqual(["Ana Pérez"]);
    expect(receivedUrl).toContain("especialidad=Nulidad");
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
    const createElementSpy = vi.spyOn(document, "createElement").mockImplementation((tag: string) => {
      const element = originalCreateElement(tag);
      if (tag === "a") element.click = clickSpy;
      return element;
    });

    await downloadDocumentFile(1, "sentencia.pdf");

    expect(clickSpy).toHaveBeenCalledOnce();
    createElementSpy.mockRestore();
  });

  it("throws when the download request fails", async () => {
    server.use(http.get(`${BASE_URL}/documents/2/download`, () => new HttpResponse(null, { status: 404 })));

    await expect(downloadDocumentFile(2, "x.pdf")).rejects.toThrow();
  });
});

describe("downloadFromUrl", () => {
  it("fetches the given URL and triggers a browser download under the given filename", async () => {
    server.use(
      http.get("https://signed.example.com/preview.pdf", () => new HttpResponse(new Blob(["contenido pdf"], { type: "application/pdf" })))
    );
    const clickSpy = vi.fn();
    const originalCreateElement = document.createElement.bind(document);
    const createElementSpy = vi.spyOn(document, "createElement").mockImplementation((tag: string) => {
      const element = originalCreateElement(tag);
      if (tag === "a") element.click = clickSpy;
      return element;
    });

    await downloadFromUrl("https://signed.example.com/preview.pdf", "documento.pdf");

    expect(clickSpy).toHaveBeenCalledOnce();
    createElementSpy.mockRestore();
  });

  it("throws when the fetch fails", async () => {
    server.use(http.get("https://signed.example.com/missing.pdf", () => new HttpResponse(null, { status: 404 })));

    await expect(downloadFromUrl("https://signed.example.com/missing.pdf", "x.pdf")).rejects.toThrow();
  });
});

describe("fetchDocumentBlob", () => {
  it("fetches the raw file content as a Blob", async () => {
    server.use(
      http.get(`${BASE_URL}/documents/5/download`, () => new HttpResponse("contenido", { headers: { "Content-Type": "application/pdf" } }))
    );

    const blob = await fetchDocumentBlob(5);

    expect(blob).toBeInstanceOf(Blob);
    expect(await blob.text()).toBe("contenido");
  });

  it("throws when the request fails", async () => {
    server.use(http.get(`${BASE_URL}/documents/6/download`, () => new HttpResponse(null, { status: 404 })));

    await expect(fetchDocumentBlob(6)).rejects.toThrow();
  });
});

describe("fetchDocumentPreviewUrl", () => {
  it("fetches the presigned preview URL as JSON (not a redirect consumed as a Blob)", async () => {
    // The preview URL is meant to be used directly as an <iframe src>, so the browser's
    // own pdf viewer can read the filename hint baked into the URL's
    // ResponseContentDisposition — something a fetch()+Blob would throw away.
    server.use(
      http.get(`${BASE_URL}/documents/7/preview`, () => HttpResponse.json({ url: "https://signed.example.com/doc7.pdf" }))
    );

    const url = await fetchDocumentPreviewUrl(7);

    expect(url).toBe("https://signed.example.com/doc7.pdf");
  });

  it("throws when the preview request fails", async () => {
    server.use(http.get(`${BASE_URL}/documents/8/preview`, () => new HttpResponse(null, { status: 502 })));

    await expect(fetchDocumentPreviewUrl(8)).rejects.toThrow();
  });
});

function makeDocument(overrides: Partial<Document> = {}): Document {
  return {
    id: 1,
    doc_id: "abc",
    source_id: 1,
    title: "Sentencia X",
    nombre: "Sentencia X",
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
    const document = makeDocument({ title: "Título crudo", nombre: "Sentencia X", storage_key: "abc123.pdf" });

    expect(buildDownloadFilename(document)).toBe("Sentencia X.pdf");
  });

  it("falls back to the content_type map when storage_key has no recognizable extension", () => {
    const document = makeDocument({
      nombre: "Reporte",
      storage_key: "some-opaque-key-without-extension",
      content_type: "text/plain",
    });

    expect(buildDownloadFilename(document)).toBe("Reporte.txt");
  });

  it("omits the extension entirely when neither storage_key nor content_type yield one", () => {
    const document = makeDocument({
      nombre: "Sin extension",
      storage_key: "opaque-key",
      content_type: "application/octet-stream",
    });

    expect(buildDownloadFilename(document)).toBe("Sin extension");
  });

  it("sanitizes a nombre containing a slash, regardless of the (unrelated) title field", () => {
    const document = makeDocument({ title: "Auto 999/2099", nombre: "Auto 123/2026", storage_key: "abc123.pdf" });

    expect(buildDownloadFilename(document)).toBe("Auto 123-2026.pdf");
  });
});

it("usa el nombre canónico para el archivo de descarga", () => {
  const doc = { nombre: "11001_20260731_v2", storage_key: "x/y.pdf", content_type: "application/pdf" } as any;
  expect(buildDownloadFilename(doc)).toBe("11001_20260731_v2.pdf");
});

it("usa el nombre canónico de la versión", () => {
  const version = { nombre: "11001_20260731_v1", content_type: "application/pdf", id: 5 } as any;
  expect(buildVersionDownloadFilename(version)).toBe("11001_20260731_v1.pdf");
});

describe("fetchDocumentVersions", () => {
  it("gets the version list for a document", async () => {
    const versions = [
      { id: 1, document_id: 5, file_size_bytes: 100, content_type: "application/rtf", downloaded_at: "2026-06-01T00:00:00Z", superseded_at: "2026-07-01T00:00:00Z" },
    ];
    server.use(http.get(`${BASE_URL}/documents/5/versions`, () => HttpResponse.json(versions)));

    const result = await fetchDocumentVersions(5);

    expect(result).toEqual(versions);
  });
});

describe("fetchDocumentVersionUrl", () => {
  it("returns the presigned url for a version", async () => {
    server.use(
      http.get(`${BASE_URL}/documents/5/versions/1/download`, () =>
        HttpResponse.json({ url: "https://signed.example.com/versions/1.rtf" })
      )
    );

    const result = await fetchDocumentVersionUrl(5, 1);

    expect(result).toBe("https://signed.example.com/versions/1.rtf");
  });
});
