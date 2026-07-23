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

  it("skips a lone '0' that follows 'N' as a typo'd/OCR'd 'No.' abbreviation, not the real number", () => {
    expect(extractNumber("ACUERDO N0. 0402 DE 2016 PDF.pdf", 2016)).toBe(402);
    expect(extractNumber("ACUERDO N0. 397 PDF1.PDF", 2016)).toBe(397);
    expect(extractNumber("AC N0. 453 DE 2018.PDF", 2018)).toBe(453);
  });

  it("does not skip a multi-digit number even if it directly follows 'n'", () => {
    expect(extractNumber("edicion0099.pdf", null)).toBe(99);
  });

  it("prefers the number right after the word 'acuerdo' over an earlier unrelated number", () => {
    expect(extractNumber("NULIDAD ARTICULO 16 DEL ACUERDO 032 DE 1998 PDF1.PDF", 1998)).toBe(32);
  });

  it("falls back to the first candidate number when the filename has no 'acuerdo' word at all", () => {
    expect(extractNumber("Adicion 12 - copia 5.pdf", null)).toBe(12);
  });

  it("ignores a parenthesized copy marker like '(1)', even when it appears after the word 'acuerdo'", () => {
    expect(extractNumber("055NOVIEMBRE1973ACUERDO (1).pdf", 1973)).toBe(55);
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

  it("lowercases the extension so files differing only by extension case collide as duplicates", () => {
    expect(fileExtension("archivo.PDF")).toBe(".pdf");
    expect(fileExtension("archivo.Pdf")).toBe(".pdf");
  });
});

describe("buildFileName", () => {
  it("builds the final name from config, number, year and extension", () => {
    expect(buildFileName({ typeCode: "A", cityCode: "CONCALI" }, 5, 1962, ".pdf")).toBe("A_CONCALI_0005_1962.pdf");
  });

  it("appends an optional suffix before the extension", () => {
    expect(buildFileName({ typeCode: "A", cityCode: "CONCALI" }, 55, 1973, ".pdf", "_1")).toBe(
      "A_CONCALI_0055_1973_1.pdf"
    );
    expect(buildFileName({ typeCode: "A", cityCode: "CONCALI" }, 402, 2016, ".rar", "_anexo1")).toBe(
      "A_CONCALI_0402_2016_anexo1.rar"
    );
  });
});
