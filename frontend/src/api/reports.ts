import { apiFetch, buildQuery } from "./client";

export interface MonthlyReport {
  id: number;
  period: string;
  status: "pending" | "running" | "completed" | "failed";
  triggered_by: "manual" | "scheduled";
  error_message: string | null;
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
}

export interface ListReportsParams {
  limit?: number;
  offset?: number;
  [key: string]: string | number | boolean | undefined;
}

export function fetchReports(params: ListReportsParams = {}): Promise<MonthlyReport[]> {
  return apiFetch<MonthlyReport[]>(`/reports${buildQuery(params)}`);
}

export function createReport(period: string): Promise<MonthlyReport> {
  return apiFetch<MonthlyReport>("/reports", { method: "POST", body: JSON.stringify({ period: `${period}-01` }) });
}

export function fetchReportUrl(id: number): Promise<string> {
  return apiFetch<{ url: string }>(`/reports/${id}/download`).then((data) => data.url);
}
