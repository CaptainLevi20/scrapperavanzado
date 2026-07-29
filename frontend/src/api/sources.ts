import { apiFetch, buildQuery } from "./client";
import type { Source, SourceUpdateInput } from "./types";

export interface ListSourcesParams {
  id?: number;
  family_key?: string;
  active?: boolean;
  has_documents?: boolean;
  limit?: number;
  offset?: number;
  [key: string]: string | number | boolean | undefined;
}

export function fetchSources(params: ListSourcesParams = {}): Promise<Source[]> {
  return apiFetch<Source[]>(`/sources${buildQuery(params)}`);
}

const ALL_SOURCES_PAGE_SIZE = 100;

// Used by the Fuentes page's "Fuente" filter: every source (active or not),
// so it can narrow the table down to one specific source by name — unlike a
// family, which groups several distinctly-named sources together.
export async function fetchAllSources(): Promise<Source[]> {
  const all: Source[] = [];
  let offset = 0;
  while (true) {
    const page = await fetchSources({ limit: ALL_SOURCES_PAGE_SIZE, offset });
    all.push(...page);
    if (page.length < ALL_SOURCES_PAGE_SIZE) break;
    offset += ALL_SOURCES_PAGE_SIZE;
  }
  return all;
}

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

// Used by the Documents page's Fuente filter: only sources that actually have at
// least one document, so the dropdown doesn't offer options that always return an
// empty table. Other callers of fetchAllActiveSources (the "Nuevo run" source
// picker, the Dashboard's "Fuentes activas" count) intentionally keep using every
// active source regardless of document count.
export async function fetchAllActiveSourcesWithDocuments(): Promise<Source[]> {
  const all: Source[] = [];
  let offset = 0;
  while (true) {
    const page = await fetchSources({ active: true, has_documents: true, limit: ALL_SOURCES_PAGE_SIZE, offset });
    all.push(...page);
    if (page.length < ALL_SOURCES_PAGE_SIZE) break;
    offset += ALL_SOURCES_PAGE_SIZE;
  }
  return all;
}

export function updateSource(id: number, input: SourceUpdateInput): Promise<Source> {
  return apiFetch<Source>(`/sources/${id}`, { method: "PATCH", body: JSON.stringify(input) });
}
