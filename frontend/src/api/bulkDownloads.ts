import { apiFetch, buildQuery } from "./client";

export interface BulkDownload {
  id: number;
  status: "pending" | "running" | "completed" | "failed";
  document_count: number;
  failed_count: number;
  error_message: string | null;
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
}

export interface ListBulkDownloadsParams {
  limit?: number;
  offset?: number;
  [key: string]: string | number | boolean | undefined;
}

export function createBulkDownload(): Promise<BulkDownload> {
  return apiFetch<BulkDownload>("/bulk-downloads", { method: "POST" });
}

export function fetchBulkDownloads(params: ListBulkDownloadsParams = {}): Promise<BulkDownload[]> {
  return apiFetch<BulkDownload[]>(`/bulk-downloads${buildQuery(params)}`);
}

export function fetchBulkDownloadUrl(id: number): Promise<string> {
  return apiFetch<{ url: string }>(`/bulk-downloads/${id}/download`).then((data) => data.url);
}
