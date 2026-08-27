import { describe, expect, it } from "vitest";
import { http, HttpResponse } from "msw";
import { server } from "../test/server";
import { analyzeReorganization, applyReorganization } from "./reorganize";

const BASE_URL = "http://localhost:8000";

describe("reorganize API", () => {
  it("analyzeReorganization posts the root path and returns the analysis", async () => {
    let receivedBody: unknown = null;
    server.use(
      http.post(`${BASE_URL}/reorganize/analyze`, async ({ request }) => {
        receivedBody = await request.json();
        return HttpResponse.json({
          root_path: "D:/LOTE 2",
          total_files: 1,
          tipos: [],
          exceptions: [],
          extra_depth: [],
          extra_depth_total: 0,
          folder_renames: [],
        });
      })
    );

    const result = await analyzeReorganization("D:/LOTE 2");

    expect(receivedBody).toEqual({ root_path: "D:/LOTE 2" });
    expect(result.total_files).toBe(1);
  });

  it("applyReorganization posts the root path and the resolved moves", async () => {
    let receivedBody: unknown = null;
    server.use(
      http.post(`${BASE_URL}/reorganize/apply`, async ({ request }) => {
        receivedBody = await request.json();
        return HttpResponse.json({
          results: [{ current_path: "a", target_path: "b", moved: true, skip_reason: null }],
          folder_rename_results: [],
        });
      })
    );

    const result = await applyReorganization("D:/LOTE 2", [{ current_path: "a", target_path: "b" }]);

    expect(receivedBody).toEqual({
      root_path: "D:/LOTE 2",
      moves: [{ current_path: "a", target_path: "b" }],
      folder_renames: [],
    });
    expect(result.results[0].moved).toBe(true);
  });

  it("applyReorganization posts the resolved folder renames when given", async () => {
    let receivedBody: unknown = null;
    server.use(
      http.post(`${BASE_URL}/reorganize/apply`, async ({ request }) => {
        receivedBody = await request.json();
        return HttpResponse.json({
          results: [],
          folder_rename_results: [{ current_path: "ACUERDOS/CMARAUCA", target_path: "ACUERDOS/CARAUCA", renamed: true, skip_reason: null }],
        });
      })
    );

    const result = await applyReorganization("D:/LOTE 2", [], [
      { current_path: "ACUERDOS/CMARAUCA", target_path: "ACUERDOS/CARAUCA" },
    ]);

    expect(receivedBody).toEqual({
      root_path: "D:/LOTE 2",
      moves: [],
      folder_renames: [{ current_path: "ACUERDOS/CMARAUCA", target_path: "ACUERDOS/CARAUCA" }],
    });
    expect(result.folder_rename_results[0].renamed).toBe(true);
  });
});
