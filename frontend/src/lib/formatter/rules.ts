export interface FormatterConfig {
  typeCode: string;
  cityCode: string;
}

const TYPE_KEYWORDS: Record<string, string> = {
  acuerdo: "A",
};

const CITY_KEYWORDS: Record<string, string> = {
  cali: "CONCALI",
};

const YEAR_PATTERN = /\b(1[89]\d{2}|20\d{2})\b/;

function normalize(value: string): string {
  return value
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase();
}

export function detectConfig(rootFolderName: string): FormatterConfig | null {
  const normalized = normalize(rootFolderName);
  const typeEntry = Object.entries(TYPE_KEYWORDS).find(([keyword]) => normalized.includes(keyword));
  const cityEntry = Object.entries(CITY_KEYWORDS).find(([keyword]) => normalized.includes(keyword));
  if (!typeEntry || !cityEntry) return null;
  return { typeCode: typeEntry[1], cityCode: cityEntry[1] };
}

export function extractYear(folderName: string): number | null {
  const match = YEAR_PATTERN.exec(folderName);
  return match ? Number(match[1]) : null;
}

export function extractNumber(filename: string, year: number | null): number | null {
  const candidates: RegExpMatchArray[] = [];
  for (const match of filename.matchAll(/\d+/g)) {
    const raw = match[0];
    const value = Number(raw);
    if (year !== null && value === year) continue;

    // A lone "0" immediately after "N" (as in "N0." for "Acuerdo N0. 402") is a
    // typo'd/OCR'd "No." (Número) abbreviation, not the acuerdo number itself —
    // skip it and keep looking for the real number later in the filename.
    const precedingChar = filename[match.index - 1];
    const isNoAbbreviation = raw === "0" && precedingChar?.toLowerCase() === "n";
    if (isNoAbbreviation) continue;

    // A number wrapped in parentheses, e.g. "archivo (1).pdf", is a Windows-style
    // copy marker for an accidental duplicate upload, not the acuerdo's own
    // number — exclude it from the candidates entirely.
    const isParenthesized = precedingChar === "(" && filename[(match.index ?? 0) + raw.length] === ")";
    if (isParenthesized) continue;

    candidates.push(match);
  }
  if (candidates.length === 0) return null;

  // A number that appears before the word "acuerdo" is usually something else
  // mentioned in the title (an article number, a nullity clause, ...), not the
  // acuerdo's own number — prefer the first candidate that comes AFTER "acuerdo"
  // when the word is present, falling back to the first candidate otherwise.
  const acuerdoIndex = normalize(filename).indexOf("acuerdo");
  if (acuerdoIndex !== -1) {
    const afterAcuerdo = candidates.find((match) => (match.index ?? -1) > acuerdoIndex);
    if (afterAcuerdo) return Number(afterAcuerdo[0]);
  }

  return Number(candidates[0][0]);
}

export function padNumber(value: number): string {
  return String(value).padStart(4, "0");
}

export function fileExtension(filename: string): string {
  const match = /\.[^./\\]+$/.exec(filename);
  // Lowercased so two files differing only by extension case (".pdf" vs ".PDF")
  // produce the same final name and are correctly caught as a collision instead
  // of one silently slipping through as "ready" with the wrong number.
  return match ? match[0].toLowerCase() : "";
}

export function buildFileName(
  config: FormatterConfig,
  number: number,
  year: number,
  ext: string,
  suffix: string = ""
): string {
  return `${config.typeCode}_${config.cityCode}_${padNumber(number)}_${year}${suffix}${ext}`;
}
