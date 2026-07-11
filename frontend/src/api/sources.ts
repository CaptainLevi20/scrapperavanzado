import { apiFetch, buildQuery } from "./client";
import type { Source, SourceCreateInput, SourceUpdateInput } from "./types";

export interface ListSourcesParams {
  family_key?: string;
  active?: boolean;
  limit?: number;
  offset?: number;
  [key: string]: string | number | boolean | undefined;
}

export function fetchSources(params: ListSourcesParams = {}): Promise<Source[]> {
  return apiFetch<Source[]>(`/sources${buildQuery(params)}`);
}

export function createSource(input: SourceCreateInput): Promise<Source> {
  return apiFetch<Source>("/sources", { method: "POST", body: JSON.stringify(input) });
}

export function updateSource(id: number, input: SourceUpdateInput): Promise<Source> {
  return apiFetch<Source>(`/sources/${id}`, { method: "PATCH", body: JSON.stringify(input) });
}
