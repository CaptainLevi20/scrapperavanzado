import { describe, expect, it, vi } from "vitest";
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
  it("returns today's local date as YYYY-MM-DD, not shifted by UTC conversion", () => {
    vi.useFakeTimers();
    // 2026-07-23T02:00:00 UTC is still 2026-07-22 in America/Bogota (UTC-5) —
    // this pins system time to exercise exactly the shift formatDate's
    // parseDateOnlyAsLocal comment already warns about, but for "today"
    // instead of a parsed date string.
    vi.setSystemTime(new Date("2026-07-23T02:00:00Z"));

    const result = todayDateString();

    expect(result).toMatch(/^\d{4}-\d{2}-\d{2}$/);
    expect(result).toBe(
      `${new Date().getFullYear()}-${String(new Date().getMonth() + 1).padStart(2, "0")}-${String(new Date().getDate()).padStart(2, "0")}`
    );

    vi.useRealTimers();
  });
});
