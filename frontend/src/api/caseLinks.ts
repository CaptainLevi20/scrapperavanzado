import { apiFetch } from "./client";
import type { CaseLink, CaseLinkListItem } from "./types";

export function fetchCaseLinks(): Promise<CaseLinkListItem[]> {
  return apiFetch<CaseLinkListItem[]>("/case-links");
}

export function fetchCaseLink(id: number): Promise<CaseLink> {
  return apiFetch<CaseLink>(`/case-links/${id}`);
}

export function separateCaseLinkStage(
  caseLinkId: number,
  stageId: number,
): Promise<{ dissolved: boolean; case_link_id: number | null }> {
  return apiFetch(`/case-links/${caseLinkId}/stages/${stageId}`, { method: "DELETE" });
}
