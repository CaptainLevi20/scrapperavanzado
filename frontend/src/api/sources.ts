import { apiFetch, buildQuery } from "./client";
import type { Source, SourceUpdateInput } from "./types";

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

const ALL_SOURCES_PAGE_SIZE = 100;

export async function fetchAllActiveSources(): Promise<Source[]> {
  const all: Source[] = [];
  let offset = 0;
  while (true) {
    const page = await fetchSources({ active: true, limit: ALL_SOURCES_PAGE_SIZE, offset });
    all.push(...page);
    if (page.length < ALL_SOURCES_PAGE_SIZE) break;
    offset += ALL_SOURCES_PAGE_SIZE;
  }
  return all;
}

export function updateSource(id: number, input: SourceUpdateInput): Promise<Source> {
  return apiFetch<Source>(`/sources/${id}`, { method: "PATCH", body: JSON.stringify(input) });
}
