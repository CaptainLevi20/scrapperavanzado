import { describe, expect, it } from "vitest";
import { formatBytes, formatDate, formatDateTime } from "./formatters";

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
});
