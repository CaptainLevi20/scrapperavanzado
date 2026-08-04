import { apiFetch } from "./client";
import type { CaseLink, CaseLinkSuggestion, ManualCaseLinkInput } from "./types";

export function fetchCaseLinkSuggestions(): Promise<CaseLinkSuggestion[]> {
  return apiFetch<CaseLinkSuggestion[]>("/case-link-suggestions");
}

export function confirmCaseLinkSuggestion(suggestionId: number): Promise<CaseLink> {
  return apiFetch<CaseLink>(`/case-link-suggestions/${suggestionId}/confirm`, { method: "POST" });
}

export function dismissCaseLinkSuggestion(suggestionId: number): Promise<{ status: string }> {
  return apiFetch<{ status: string }>(`/case-link-suggestions/${suggestionId}/dismiss`, { method: "POST" });
}

export function createManualCaseLink(input: ManualCaseLinkInput): Promise<CaseLink> {
  return apiFetch<CaseLink>("/case-links", { method: "POST", body: JSON.stringify(input) });
}

export function fetchCaseLink(id: number): Promise<CaseLink> {
  return apiFetch<CaseLink>(`/case-links/${id}`);
}
