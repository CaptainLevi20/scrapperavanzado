import { describe, expect, it } from "vitest";
import { pickCurrentPage } from "./pdfPage";

describe("pickCurrentPage", () => {
  it("returns page 1 when nothing is visible yet", () => {
    expect(pickCurrentPage(new Map())).toBe(1);
    expect(pickCurrentPage(new Map([[1, 0], [2, 0], [3, 0]]))).toBe(1);
  });

  it("picks the page that occupies the most of the viewport", () => {
    expect(pickCurrentPage(new Map([[1, 0.2], [2, 0.8], [3, 0]]))).toBe(2);
    expect(pickCurrentPage(new Map([[4, 0.1], [5, 0.9]]))).toBe(5);
  });

  it("breaks ties toward the lower page number regardless of insertion order", () => {
    // Two pages equally visible (e.g. straddling the viewport): the one you
    // reach first scrolling down wins, no matter which intersected first.
    expect(pickCurrentPage(new Map([[3, 0.5], [2, 0.5]]))).toBe(2);
    expect(pickCurrentPage(new Map([[2, 0.5], [3, 0.5]]))).toBe(2);
  });

  it("ignores pages scrolled out of view (ratio 0)", () => {
    expect(pickCurrentPage(new Map([[1, 0], [2, 0], [3, 0.4]]))).toBe(3);
  });
});
