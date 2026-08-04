import { describe, expect, it, vi, beforeEach } from "vitest";
import * as client from "./client";
import {
  confirmCaseLinkSuggestion,
  createManualCaseLink,
  dismissCaseLinkSuggestion,
  fetchCaseLink,
  fetchCaseLinkSuggestions,
} from "./caseLinks";

vi.mock("./client", async () => {
  const actual = await vi.importActual<typeof client>("./client");
  return { ...actual, apiFetch: vi.fn() };
});

describe("caseLinks api", () => {
  beforeEach(() => {
    vi.mocked(client.apiFetch).mockReset();
  });

  it("fetches pending suggestions", async () => {
    vi.mocked(client.apiFetch).mockResolvedValue([]);
    await fetchCaseLinkSuggestions();
    expect(client.apiFetch).toHaveBeenCalledWith("/case-link-suggestions");
  });

  it("confirms a suggestion", async () => {
    vi.mocked(client.apiFetch).mockResolvedValue({ id: 1, stages: [] });
    await confirmCaseLinkSuggestion(7);
    expect(client.apiFetch).toHaveBeenCalledWith("/case-link-suggestions/7/confirm", { method: "POST" });
  });

  it("dismisses a suggestion", async () => {
    vi.mocked(client.apiFetch).mockResolvedValue({ status: "dismissed" });
    await dismissCaseLinkSuggestion(7);
    expect(client.apiFetch).toHaveBeenCalledWith("/case-link-suggestions/7/dismiss", { method: "POST" });
  });

  it("creates a manual link", async () => {
    vi.mocked(client.apiFetch).mockResolvedValue({ id: 1, stages: [] });
    await createManualCaseLink({ source_id_a: 1, radicado_a: "a", source_id_b: 2, radicado_b: "b" });
    expect(client.apiFetch).toHaveBeenCalledWith("/case-links", {
      method: "POST",
      body: JSON.stringify({ source_id_a: 1, radicado_a: "a", source_id_b: 2, radicado_b: "b" }),
    });
  });

  it("fetches a case link by id", async () => {
    vi.mocked(client.apiFetch).mockResolvedValue({ id: 1, stages: [] });
    await fetchCaseLink(1);
    expect(client.apiFetch).toHaveBeenCalledWith("/case-links/1");
  });
});
