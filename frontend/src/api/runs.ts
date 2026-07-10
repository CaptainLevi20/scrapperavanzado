import { apiFetch, buildQuery } from "./client";
import type { Run, RunCreateInput, RunSource } from "./types";

export interface ListRunsParams {
  status_filter?: string;
  limit?: number;
  offset?: number;
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
