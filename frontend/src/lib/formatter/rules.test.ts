import { describe, expect, it } from "vitest";
import { buildFileName, detectConfig, extractNumber, extractYear, fileExtension, padNumber } from "./rules";

describe("detectConfig", () => {
  it("detects type and city from keywords regardless of case and accents", () => {
    expect(detectConfig("Acuerdos Cali")).toEqual({ typeCode: "A", cityCode: "CONCALI" });
    expect(detectConfig("ACUERDOS DE CALÍ")).toEqual({ typeCode: "A", cityCode: "CONCALI" });
  });

  it("returns null when the type keyword is missing", () => {
    expect(detectConfig("Resoluciones Cali")).toBeNull();
  });

  it("returns null when the city keyword is missing", () => {
    expect(detectConfig("Acuerdos Bogota")).toBeNull();
  });
});

describe("extractYear", () => {
  it("extracts a plausible year from the folder name", () => {
    expect(extractYear("ACUERDOS 1962")).toBe(1962);
    expect(extractYear("ACUERDOS 2025")).toBe(2025);
  });

  it("returns null when no plausible year is present", () => {
    expect(extractYear("ACUERDOS VARIOS")).toBeNull();
  });
});

describe("extractNumber", () => {
  it("returns the first number that is not the year", () => {
    expect(extractNumber("Acuerdo 0005 de 1962.pdf", 1962)).toBe(5);
    expect(extractNumber("1962 - acuerdo 12.pdf", 1962)).toBe(12);
  });

  it("returns null when the only number found is the year", () => {
    expect(extractNumber("1962.pdf", 1962)).toBeNull();
  });

  it("returns null when there is no number at all", () => {
    expect(extractNumber("acuerdo sin numero.pdf", 1962)).toBeNull();
  });

  it("returns the first number when year is null", () => {
    expect(extractNumber("acuerdo 7.pdf", null)).toBe(7);
  });
});

describe("padNumber", () => {
  it("pads to at least 4 digits", () => {
    expect(padNumber(5)).toBe("0005");
    expect(padNumber(42)).toBe("0042");
  });

  it("leaves numbers with more than 4 digits untouched", () => {
    expect(padNumber(12345)).toBe("12345");
  });
});

describe("fileExtension", () => {
  it("returns the extension including the dot", () => {
    expect(fileExtension("archivo.pdf")).toBe(".pdf");
  });

  it("returns an empty string when there is no extension", () => {
    expect(fileExtension("archivo")).toBe("");
  });
});

describe("buildFileName", () => {
  it("builds the final name from config, number, year and extension", () => {
    expect(buildFileName({ typeCode: "A", cityCode: "CONCALI" }, 5, 1962, ".pdf")).toBe("A_CONCALI_0005_1962.pdf");
  });
});
