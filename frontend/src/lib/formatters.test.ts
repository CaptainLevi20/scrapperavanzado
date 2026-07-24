import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { formatBytes, formatDate, formatDateTime, todayDateString } from "./formatters";

describe("formatBytes", () => {
  it("formats bytes under 1KB", () => expect(formatBytes(500)).toBe("500 B"));
  it("formats KB", () => expect(formatBytes(2048)).toBe("2.0 KB"));
  it("formats MB", () => expect(formatBytes(5 * 1024 * 1024)).toBe("5.0 MB"));
  it("returns an em dash for null", () => expect(formatBytes(null)).toBe("—"));
});

describe("formatDate / formatDateTime", () => {
  it("returns an em dash for null", () => {
    expect(formatDate(null)).toBe("—");
    expect(formatDateTime(null)).toBe("—");
  });

  it("formats a non-null date string", () => {
    expect(formatDate("2026-07-10")).not.toBe("—");
    expect(formatDateTime("2026-07-10T12:00:00Z")).not.toBe("—");
  });

  it("does not shift a plain YYYY-MM-DD date back a day in a UTC-5 timezone", () => {
    // Regression test: `new Date("2026-07-16")` is parsed as UTC midnight, which is
    // 2026-07-15T19:00:00 in America/Bogota (UTC-5) — the exact discrepancy reported
    // against real JEP documents (DB correctly stored 2026-07-16, but the table
    // displayed 2026-07-15).
    expect(formatDate("2026-07-16")).toContain("16");
    expect(formatDate("2026-07-16")).not.toContain("15");
  });
});

describe("todayDateString", () => {
  const ORIGINAL_TZ = process.env.TZ;

  beforeEach(() => {
    // Pin to America/Bogota (UTC-5, this project's real users) so the assertion
    // is deterministic regardless of the host machine's ambient timezone — CI
    // runners (ubuntu-latest, UTC) would otherwise never catch a regression to
    // the banned `toISOString().slice(0, 10)` pattern, since at UTC+0 both the
    // correct and buggy implementations happen to agree.
    process.env.TZ = "America/Bogota";
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
    process.env.TZ = ORIGINAL_TZ;
  });

  it("returns today's local date as YYYY-MM-DD, shifted back a day from a UTC timestamp early in the UTC day", () => {
    // 2026-07-23T02:00:00 UTC is 2026-07-22T21:00:00 in America/Bogota (UTC-5) —
    // the exact discrepancy this helper exists to avoid (see the module's own
    // comment). `new Date().toISOString().slice(0, 10)` would wrongly return
    // "2026-07-23" here; the correct local-component answer is "2026-07-22".
    vi.setSystemTime(new Date("2026-07-23T02:00:00Z"));

    expect(todayDateString()).toBe("2026-07-22");
  });
});
