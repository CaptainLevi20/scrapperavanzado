import { describe, expect, it } from "vitest";
import { isStaleRun, isTerminalRunStatus, MAX_POLL_AGE_MS, shouldPollRun } from "./runStatus";

describe("isTerminalRunStatus", () => {
  it("treats completed, failed, and cancelled as terminal", () => {
    expect(isTerminalRunStatus("completed")).toBe(true);
    expect(isTerminalRunStatus("failed")).toBe(true);
    expect(isTerminalRunStatus("cancelled")).toBe(true);
  });

  it("treats pending and running as not terminal", () => {
    expect(isTerminalRunStatus("pending")).toBe(false);
    expect(isTerminalRunStatus("running")).toBe(false);
  });
});

describe("isStaleRun", () => {
  const now = new Date("2026-07-28T12:00:00Z").getTime();

  it("is not stale just under the cutoff", () => {
    const createdAt = new Date(now - MAX_POLL_AGE_MS + 1000).toISOString();
    expect(isStaleRun(createdAt, "running", now)).toBe(false);
  });

  it("is stale once it's been running past the cutoff", () => {
    // Regression test: a worker process that dies outright (killed, crashed,
    // container restarted) never gets the chance to write "failed" — the run
    // just stays "running" in the database forever. Without this cutoff the
    // frontend would poll it every few seconds indefinitely.
    const createdAt = new Date(now - MAX_POLL_AGE_MS - 1000).toISOString();
    expect(isStaleRun(createdAt, "running", now)).toBe(true);
  });

  it("is never stale once the run reached a terminal status, no matter its age", () => {
    const createdAt = new Date(now - MAX_POLL_AGE_MS * 10).toISOString();
    expect(isStaleRun(createdAt, "completed", now)).toBe(false);
  });
});

describe("shouldPollRun", () => {
  const now = new Date("2026-07-28T12:00:00Z").getTime();

  it("keeps polling a fresh, non-terminal run", () => {
    const createdAt = new Date(now - 1000).toISOString();
    expect(shouldPollRun(createdAt, "running", now)).toBe(true);
  });

  it("stops polling a terminal run even if it's fresh", () => {
    const createdAt = new Date(now - 1000).toISOString();
    expect(shouldPollRun(createdAt, "completed", now)).toBe(false);
  });

  it("stops polling a non-terminal run once it's stale", () => {
    const createdAt = new Date(now - MAX_POLL_AGE_MS - 1000).toISOString();
    expect(shouldPollRun(createdAt, "running", now)).toBe(false);
  });
});
