import { fileExtension } from "../formatter/rules";

// Naming rules for the PGN concepts batch: CTO_PGN_{7-digit number}{A?}_{year}(C).{ext}
// See docs/superpowers/specs/2026-11-20-laboratorio-conceptos-pgn-design.md.

export interface ConceptNumber {
  value: number;
  letter: "" | "A";
}

const DOCUMENT_EXTENSIONS = new Set([".pdf", ".doc", ".docx", ".rtf"]);
const IMAGE_EXTENSIONS = new Set([".jpg", ".jpeg", ".png", ".tif", ".tiff"]);
const YEAR = /^(19|20)\d{2}$/;

export function isDocument(filename: string): boolean {
  return DOCUMENT_EXTENSIONS.has(fileExtension(filename));
}

export function isImage(filename: string): boolean {
  return IMAGE_EXTENSIONS.has(fileExtension(filename));
}

export function yearFromFolderName(name: string): number | null {
  return YEAR.test(name) ? Number(name) : null;
}

function stemOf(filename: string): string {
  const ext = /\.[^./\\]+$/.exec(filename);
  return ext ? filename.slice(0, ext.index) : filename;
}

interface NumberGroup {
  value: number;
  digits: string;
  letter: "" | "A";
}

export function parseConceptName(
  filename: string,
  folderYear: number | null
): { number: ConceptNumber | null; nameYear: number | null } {
  const stem = stemOf(filename);
  // "Tomo 3 1991-1-14": a fragment of a whole tomo by page range — the "3" is
  // the tomo, not a concept, so there is no concept number to read.
  if (/^\s*tomo\b/i.test(stem)) return { number: null, nameYear: null };

  // The letter is only taken when no other letter follows it, so "3168pdf"
  // stays 3168 and "4883-A" becomes 4883A.
  let groups: NumberGroup[] = Array.from(stem.matchAll(/(\d+)(?:-?([Aa])(?![A-Za-z]))?/g), (match) => ({
    value: Number(match[1]),
    digits: match[1],
    letter: match[2] ? "A" : "",
  }));

  // A year written in the name is always the LAST number and never the only
  // one: concepts numbered 1900-2099 exist (e.g. "2011.pdf" in 2000).
  let nameYear: number | null = null;
  const last = groups[groups.length - 1];
  if (groups.length >= 2 && last.letter === "" && YEAR.test(last.digits)) {
    nameYear = last.value;
    groups = groups.slice(0, -1);
  }

  const candidate = groups.find((group) => !(group.letter === "" && group.value === folderYear));
  return {
    number: candidate ? { value: candidate.value, letter: candidate.letter } : null,
    nameYear,
  };
}

export function parseConceptInput(text: string): ConceptNumber | null {
  const match = /^\s*(\d+)\s*-?\s*([Aa])?\s*$/.exec(text);
  if (!match) return null;
  return { value: Number(match[1]), letter: match[2] ? "A" : "" };
}

export function buildConceptName(number: ConceptNumber, year: number, ext: string): string {
  return `CTO_PGN_${String(number.value).padStart(7, "0")}${number.letter}_${year}(C)${ext}`;
}
