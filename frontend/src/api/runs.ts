import { apiFetch, buildQuery } from "./client";
import { fetchBlobFrom } from "./documents";
import type { Run, RunCreateInput, RunSource } from "./types";

export interface ListRunsParams {
  status_filter?: string;
  limit?: number;
  offset?: number;
  [key: string]: string | number | boolean | undefined;
}

export function fetchRuns(params: ListRunsParams = {}): Promise<Run[]> {
  return apiFetch<Run[]>(`/runs${buildQuery(params)}`);
}

export function fetchRun(id: number): Promise<Run> {
  return apiFetch<Run>(`/runs/${id}`);
}

export function fetchRunSources(runId: number): Promise<RunSource[]> {
  return apiFetch<RunSource[]>(`/runs/${runId}/sources`);
}

export function createRun(input: RunCreateInput): Promise<Run> {
  return apiFetch<Run>("/runs", { method: "POST", body: JSON.stringify(input) });
}

export function cancelRun(id: number): Promise<Run> {
  return apiFetch<Run>(`/runs/${id}/cancel`, { method: "POST" });
}

export function retryFailedRunSources(id: number): Promise<Run> {
  return apiFetch<Run>(`/runs/${id}/retry-failed`, { method: "POST" });
}

export function fetchRunReportBlob(id: number): Promise<Blob> {
  return fetchBlobFrom(`/runs/${id}/report.xlsx`, "No se pudo generar el informe");
}
