import { describe, expect, it, vi, beforeEach } from "vitest";
import * as client from "./client";
import { fetchCaseLinks, fetchCaseLink, separateCaseLinkStage } from "./caseLinks";

vi.mock("./client", async () => {
  const actual = await vi.importActual<typeof client>("./client");
  return { ...actual, apiFetch: vi.fn() };
});

describe("caseLinks api", () => {
  beforeEach(() => {
    vi.mocked(client.apiFetch).mockReset();
  });

  it("fetches the list of expedientes", async () => {
    vi.mocked(client.apiFetch).mockResolvedValue([]);
    await fetchCaseLinks();
    expect(client.apiFetch).toHaveBeenCalledWith("/case-links");
  });

  it("fetches a single expediente by id", async () => {
    vi.mocked(client.apiFetch).mockResolvedValue({ id: 1, stages: [] });
    await fetchCaseLink(1);
    expect(client.apiFetch).toHaveBeenCalledWith("/case-links/1");
  });

  it("removes a stage from an expediente", async () => {
    vi.mocked(client.apiFetch).mockResolvedValue({ dissolved: false, case_link_id: 1 });
    await separateCaseLinkStage(1, 7);
    expect(client.apiFetch).toHaveBeenCalledWith("/case-links/1/stages/7", { method: "DELETE" });
  });
});
