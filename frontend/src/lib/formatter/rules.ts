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
  const matches = filename.match(/\d+/g);
  if (!matches) return null;
  for (const raw of matches) {
    const value = Number(raw);
    if (year === null || value !== year) return value;
  }
  return null;
}

export function padNumber(value: number): string {
  return String(value).padStart(4, "0");
}

export function fileExtension(filename: string): string {
  const match = /\.[^./\\]+$/.exec(filename);
  return match ? match[0] : "";
}

export function buildFileName(config: FormatterConfig, number: number, year: number, ext: string): string {
  return `${config.typeCode}_${config.cityCode}_${padNumber(number)}_${year}${ext}`;
}
