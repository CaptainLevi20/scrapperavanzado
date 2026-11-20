import { describe, expect, it } from "vitest";
import { fileExtension } from "../formatter/rules";
import {
  buildConceptName,
  isDocument,
  isImage,
  parseConceptInput,
  parseConceptName,
  yearFromFolderName,
} from "./rules";

// Every shape of filename found in the real PGN batch (lista_lote.txt), with
// the year of the top-level folder it lives under.
const CASES: [string, number, string][] = [
  ["Cto. 1653.pdf", 1991, "CTO_PGN_0001653_1991(C).pdf"],
  ["Cto. NN 1.pdf", 1991, "CTO_PGN_0000001_1991(C).pdf"],
  ["Cto. NN1.pdf", 2000, "CTO_PGN_0000001_2000(C).pdf"],
  ["Cto. 114 .pdf", 1992, "CTO_PGN_0000114_1992(C).pdf"],
  ["Cto. 3168pdf.pdf", 2003, "CTO_PGN_0003168_2003(C).pdf"],
  ["Concepto 2258 de 2000.pdf", 2000, "CTO_PGN_0002258_2000(C).pdf"],
  ["Concepto de 5094 de 2011.pdf", 2011, "CTO_PGN_0005094_2011(C).pdf"],
  ["Concpeto 5018 de 2010.pdf", 2010, "CTO_PGN_0005018_2010(C).pdf"],
  ["Conceptto 4106 de 2006.pdf", 2006, "CTO_PGN_0004106_2006(C).pdf"],
  ["Concepro 4747 de 2009.pdf", 2009, "CTO_PGN_0004747_2009(C).pdf"],
  ["Cncepto 5649.pdf", 2013, "CTO_PGN_0005649_2013(C).pdf"],
  ["Concepto 5651 de 2013..pdf", 2013, "CTO_PGN_0005651_2013(C).pdf"],
  ["Concepto 4450 de 2008 .pdf", 2008, "CTO_PGN_0004450_2008(C).pdf"],
  ["Concepto 4838.pdf", 2009, "CTO_PGN_0004838_2009(C).pdf"],
  ["4004.pdf", 2006, "CTO_PGN_0004004_2006(C).pdf"],
  // Concepts numbered 1900-2099 exist (year 2000 runs 2011-2365): a lone
  // number in that range is the concept number, never a year.
  ["2011.pdf", 2000, "CTO_PGN_0002011_2000(C).pdf"],
  ["Cto. 2011.pdf", 2000, "CTO_PGN_0002011_2000(C).pdf"],
  ["Concepto 4036A de 2006.pdf", 2006, "CTO_PGN_0004036A_2006(C).pdf"],
  ["Concepto 4883-A.pdf", 2010, "CTO_PGN_0004883A_2010(C).pdf"],
  ["CTO_PGN_0003788_2005.pdf", 2005, "CTO_PGN_0003788_2005(C).pdf"],
  ["Cto. 1654.PDF", 1991, "CTO_PGN_0001654_1991(C).pdf"],
];

describe("parseConceptName + buildConceptName", () => {
  it.each(CASES)("%s (carpeta %i) → %s", (filename, folderYear, expected) => {
    const { number, nameYear } = parseConceptName(filename, folderYear);
    expect(number).not.toBeNull();
    expect(buildConceptName(number!, nameYear ?? folderYear, fileExtension(filename))).toBe(expected);
  });

  it("does not read a concept number from a 'Tomo' fragment", () => {
    expect(parseConceptName("Tomo 3 1991-1-14.pdf", 1991)).toEqual({ number: null, nameYear: null });
  });

  it("reports the year written in the name when it differs from the folder", () => {
    expect(parseConceptName("Concepto 4734 de 2008.pdf", 2009)).toEqual({
      number: { value: 4734, letter: "" },
      nameYear: 2008,
    });
  });

  it("refuses a lone number equal to the folder year", () => {
    expect(parseConceptName("Cto. 2005.pdf", 2005).number).toBeNull();
  });
});

describe("parseConceptInput", () => {
  it.each(["4036A", "4036a", " 0004036A ", "4036-A"])("reads %j as 4036A", (text) => {
    expect(parseConceptInput(text)).toEqual({ value: 4036, letter: "A" });
  });

  it("reads a plain number without a letter", () => {
    expect(parseConceptInput("4036")).toEqual({ value: 4036, letter: "" });
  });

  it.each(["", "abc", "12B", "-3"])("rejects %j", (text) => {
    expect(parseConceptInput(text)).toBeNull();
  });
});

describe("isDocument / isImage", () => {
  it.each(["a.PDF", "a.docx", "a.rtf", "a.doc"])("%s is a document", (name) => {
    expect(isDocument(name)).toBe(true);
  });

  it.each(["a.jpg", "a.xlsx", "Léame.txt", "registro_renombres_20261120-1010.csv"])("%s is not a document", (name) => {
    expect(isDocument(name)).toBe(false);
  });

  it("recognizes photos", () => {
    expect(isImage("20260708_110124.JPG")).toBe(true);
    expect(isImage("a.pdf")).toBe(false);
  });
});

describe("yearFromFolderName", () => {
  it("reads an exact year folder", () => {
    expect(yearFromFolderName("1991")).toBe(1991);
  });

  it.each(["Tomo 1", "1991 bis", "1800"])("rejects %j", (name) => {
    expect(yearFromFolderName(name)).toBeNull();
  });
});
