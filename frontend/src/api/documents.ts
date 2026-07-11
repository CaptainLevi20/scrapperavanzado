import { apiFetch, buildQuery, getStoredApiKey } from "./client";
import type { Document, PaginatedDocuments } from "./types";

const BASE_URL: string = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export interface ListDocumentsParams {
  source_id?: number;
  family_key?: string;
  tipo?: string;
  title?: string;
  limit?: number;
  offset?: number;
  [key: string]: string | number | boolean | undefined;
}

export function fetchDocuments(params: ListDocumentsParams = {}): Promise<PaginatedDocuments> {
  return apiFetch<PaginatedDocuments>(`/documents${buildQuery(params)}`);
}

export function fetchDocument(id: number): Promise<Document> {
  return apiFetch<Document>(`/documents/${id}`);
}

export async function downloadDocumentFile(id: number, filename: string): Promise<void> {
  const apiKey = getStoredApiKey();
  const headers = new Headers();
  if (apiKey) headers.set("X-API-Key", apiKey);

  const response = await fetch(`${BASE_URL}/documents/${id}/download`, { headers });
  if (!response.ok) {
    throw new Error("No se pudo descargar el documento");
  }

  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}
