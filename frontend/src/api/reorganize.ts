import { apiFetch } from "./client";
import type { ApplyResult, BatchAnalysis, ResolvedMove } from "./types";

export function analyzeReorganization(rootPath: string): Promise<BatchAnalysis> {
  return apiFetch<BatchAnalysis>("/reorganize/analyze", {
    method: "POST",
    body: JSON.stringify({ root_path: rootPath }),
  });
}

export function applyReorganization(rootPath: string, moves: ResolvedMove[]): Promise<ApplyResult> {
  return apiFetch<ApplyResult>("/reorganize/apply", {
    method: "POST",
    body: JSON.stringify({ root_path: rootPath, moves }),
  });
}
