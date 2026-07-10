import { apiFetch } from "./client";
import type { SourceFamily } from "./types";

export function fetchSourceFamilies(): Promise<SourceFamily[]> {
  return apiFetch<SourceFamily[]>("/source-families");
}
