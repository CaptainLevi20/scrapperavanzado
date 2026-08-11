import { apiFetch, buildQuery, getStoredToken } from "./client";
import type { Document, DocumentReviewStatus, DocumentStats, DocumentVersion, PaginatedDocuments } from "./types";

const BASE_URL: string = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export interface ListDocumentsParams {
  source_id?: number;
  family_key?: string;
  tipo?: string;
  seccion?: string;
  especialidad?: string;
  magistrado?: string;
  title?: string;
  title_exact?: string;
  review_status?: DocumentReviewStatus;
  f_public_from?: string;
  f_public_to?: string;
  downloaded_from?: string;
  downloaded_to?: string;
  limit?: number;
  offset?: number;
  [key: string]: string | number | boolean | undefined;
}

export function fetchDocuments(params: ListDocumentsParams = {}): Promise<PaginatedDocuments> {
  return apiFetch<PaginatedDocuments>(`/documents${buildQuery(params)}`);
}

export function fetchDocumentTipos(sourceId?: number): Promise<string[]> {
  return apiFetch<string[]>(`/documents/tipos${buildQuery({ source_id: sourceId })}`);
}

export function fetchDocumentSecciones(sourceId?: number, tipo?: string): Promise<string[]> {
  return apiFetch<string[]>(`/documents/secciones${buildQuery({ source_id: sourceId, tipo })}`);
}

export function fetchDocumentEspecialidades(sourceId?: number, tipo?: string, seccion?: string): Promise<string[]> {
  return apiFetch<string[]>(`/documents/especialidades${buildQuery({ source_id: sourceId, tipo, seccion })}`);
}

export function fetchDocumentMagistrados(
  sourceId?: number,
  tipo?: string,
  seccion?: string,
  especialidad?: string
): Promise<string[]> {
  return apiFetch<string[]>(
    `/documents/magistrados${buildQuery({ source_id: sourceId, tipo, seccion, especialidad })}`
  );
}

// Aggregated server-side (GROUP BY over the whole table) rather than sampled
// client-side, so counts stay accurate no matter how large the archive gets.
export function fetchDocumentStats(year?: number, month?: number): Promise<DocumentStats> {
  return apiFetch<DocumentStats>(`/documents/stats${buildQuery({ year, month })}`);
}

export function fetchDocument(id: number): Promise<Document> {
  return apiFetch<Document>(`/documents/${id}`);
}

export function fetchDocumentVersions(documentId: number): Promise<DocumentVersion[]> {
  return apiFetch<DocumentVersion[]>(`/documents/${documentId}/versions`);
}

export function fetchDocumentVersionUrl(documentId: number, versionId: number): Promise<string> {
  return apiFetch<{ url: string }>(`/documents/${documentId}/versions/${versionId}/download`).then((data) => data.url);
}

export function updateDocumentReviewStatus(id: number, review_status: DocumentReviewStatus): Promise<Document> {
  return apiFetch<Document>(`/documents/${id}`, { method: "PATCH", body: JSON.stringify({ review_status }) });
}

// Manual escape hatch for when a family's automated title rules (Corte
// Constitucional, JEP, etc.) don't cover a one-off case — lets a reviewer
// fix a single document's title by hand from the preview dialog.
export function updateDocumentTitle(id: number, title: string): Promise<Document> {
  return apiFetch<Document>(`/documents/${id}/title`, { method: "PATCH", body: JSON.stringify({ title }) });
}

export function bulkUpdateDocumentReviewStatus(
  documentIds: number[],
  review_status: DocumentReviewStatus
): Promise<{ updated: number }> {
  return apiFetch<{ updated: number }>("/documents/bulk-review", {
    method: "PATCH",
    body: JSON.stringify({ document_ids: documentIds, review_status }),
  });
}

const CONTENT_TYPE_EXTENSIONS: Record<string, string> = {
  "application/pdf": "pdf",
  "text/plain": "txt",
  "application/msword": "doc",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
  "application/rtf": "rtf",
};

function extensionFromStorageKey(storageKey: string): string | undefined {
  const match = /\.([a-zA-Z0-9]+)$/.exec(storageKey);
  return match ? match[1].toLowerCase() : undefined;
}

function sanitizeFilename(value: string): string {
  // eslint-disable-next-line no-control-regex
  return value.replace(/[/\\\x00-\x1f]/g, "-");
}

export function buildDownloadFilename(document: Document): string {
  const ext = extensionFromStorageKey(document.storage_key) ?? (document.content_type ? CONTENT_TYPE_EXTENSIONS[document.content_type] : undefined);
  const sanitized = sanitizeFilename(document.nombre);
  return ext ? `${sanitized}.${ext}` : sanitized;
}

// The previewed file is always a PDF (native passthrough or an on-demand/pre-generated
// conversion) regardless of what format storage_key points at for the main download
// (e.g. RTF for Corte Constitucional/SAMAI), so its filename can't reuse
// buildDownloadFilename's storage_key-derived extension.
export function buildPreviewDownloadFilename(document: Document): string {
  return `${sanitizeFilename(document.nombre)}.pdf`;
}

// A DocumentVersion has no storage_key (only content_type), so its extension
// can only come from the CONTENT_TYPE_EXTENSIONS lookup, unlike
// buildDownloadFilename which can also fall back to the live document's
// storage_key. The version already carries its own canonical name (with the
// "_v{n}" suffix baked in), so no separate document title is needed here.
export function buildVersionDownloadFilename(version: DocumentVersion): string {
  const ext = version.content_type ? CONTENT_TYPE_EXTENSIONS[version.content_type] : undefined;
  const sanitized = sanitizeFilename(version.nombre);
  return ext ? `${sanitized}.${ext}` : sanitized;
}

export function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}

async function fetchBlobFrom(path: string, errorMessage: string): Promise<Blob> {
  const token = getStoredToken();
  const headers = new Headers();
  if (token) headers.set("Authorization", `Bearer ${token}`);

  const response = await fetch(`${BASE_URL}${path}`, { headers });
  if (!response.ok) {
    throw new Error(errorMessage);
  }
  return response.blob();
}

export function fetchDocumentBlob(id: number): Promise<Blob> {
  return fetchBlobFrom(`/documents/${id}/download`, "No se pudo cargar el documento");
}

// The preview endpoint returns the presigned URL as JSON (rather than a 302 redirect
// consumed via fetch()+Blob) specifically so the browser's OWN pdf viewer can be
// pointed at the signed URL directly — that lets its native download button use the
// filename baked into the URL's ResponseContentDisposition, which a Blob would have
// thrown away.
export function fetchDocumentPreviewUrl(id: number): Promise<string> {
  return apiFetch<{ url: string }>(`/documents/${id}/preview`).then((data) => data.url);
}

// The presigned URL is cross-origin (points at MinIO, not our API) and carries no
// Authorization header requirement — CORS is already permissive there (verified:
// core/storage.py's presigned URLs allow cross-origin reads), so a plain fetch works.
// Downloading via Blob (rather than just navigating to the URL) guarantees the
// browser saves the file under our chosen name regardless of cross-origin
// `download`-attribute quirks.
export async function downloadFromUrl(url: string, filename: string): Promise<void> {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error("No se pudo descargar el archivo");
  }
  const blob = await response.blob();
  downloadBlob(blob, filename);
}

export async function downloadDocumentFile(id: number, filename: string): Promise<void> {
  const blob = await fetchDocumentBlob(id);
  downloadBlob(blob, filename);
}
