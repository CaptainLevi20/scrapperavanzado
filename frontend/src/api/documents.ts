import { apiFetch, buildQuery, getStoredToken } from "./client";
import type { Document, DocumentReviewStatus, PaginatedDocuments } from "./types";

const BASE_URL: string = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export interface ListDocumentsParams {
  source_id?: number;
  family_key?: string;
  tipo?: string;
  title?: string;
  review_status?: DocumentReviewStatus;
  limit?: number;
  offset?: number;
  [key: string]: string | number | boolean | undefined;
}

export function fetchDocuments(params: ListDocumentsParams = {}): Promise<PaginatedDocuments> {
  return apiFetch<PaginatedDocuments>(`/documents${buildQuery(params)}`);
}

const STATS_PAGE_SIZE = 200;
const STATS_FETCH_CAP = 1000;

export interface DocumentStats {
  items: Document[];
  total: number;
  /** True when the archive holds more documents than STATS_FETCH_CAP — charts
   *  are then based on the most recent STATS_FETCH_CAP documents (the API's
   *  own sort order), not the full history. */
  capped: boolean;
}

// There's no aggregation endpoint on the backend (no "count grouped by tipo"),
// so dashboard charts page through the same /documents data DocumentsPage
// shows row-by-row and group it client-side. Documents already come sorted
// by downloaded_at desc, so this doubles as "most recent N" for the
// Dashboard's novedades table.
export async function fetchDocumentsForStats(): Promise<DocumentStats> {
  const first = await fetchDocuments({ limit: STATS_PAGE_SIZE, offset: 0 });
  const targetCount = Math.min(first.total, STATS_FETCH_CAP);
  const items = [...first.items];

  let offset = STATS_PAGE_SIZE;
  while (items.length < targetCount) {
    const page = await fetchDocuments({ limit: STATS_PAGE_SIZE, offset });
    if (page.items.length === 0) break;
    items.push(...page.items);
    offset += STATS_PAGE_SIZE;
  }

  return { items, total: first.total, capped: first.total > STATS_FETCH_CAP };
}

export function fetchDocument(id: number): Promise<Document> {
  return apiFetch<Document>(`/documents/${id}`);
}

export function updateDocumentReviewStatus(id: number, review_status: DocumentReviewStatus): Promise<Document> {
  return apiFetch<Document>(`/documents/${id}`, { method: "PATCH", body: JSON.stringify({ review_status }) });
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
};

function extensionFromStorageKey(storageKey: string): string | undefined {
  const match = /\.([a-zA-Z0-9]+)$/.exec(storageKey);
  return match ? match[1].toLowerCase() : undefined;
}

function sanitizeFilename(title: string): string {
  // eslint-disable-next-line no-control-regex
  return title.replace(/[/\\\x00-\x1f]/g, "-");
}

export function buildDownloadFilename(document: Document): string {
  const ext = extensionFromStorageKey(document.storage_key) ?? (document.content_type ? CONTENT_TYPE_EXTENSIONS[document.content_type] : undefined);
  const sanitizedTitle = sanitizeFilename(document.title);
  return ext ? `${sanitizedTitle}.${ext}` : sanitizedTitle;
}

export async function fetchDocumentBlob(id: number): Promise<Blob> {
  const token = getStoredToken();
  const headers = new Headers();
  if (token) headers.set("Authorization", `Bearer ${token}`);

  const response = await fetch(`${BASE_URL}/documents/${id}/download`, { headers });
  if (!response.ok) {
    throw new Error("No se pudo cargar el documento");
  }
  return response.blob();
}

export async function downloadDocumentFile(id: number, filename: string): Promise<void> {
  const blob = await fetchDocumentBlob(id);
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}
