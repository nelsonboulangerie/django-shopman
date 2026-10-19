export type CsvCell = string | number;

export interface CsvTable {
  header: readonly string[];
  rows: readonly (readonly CsvCell[])[];
}

export interface CsvRowError {
  row: number;
  detail: string;
}

export interface ParsedCsv {
  header: string[];
  rows: string[][];
  errors: CsvRowError[];
}

const CSV_NUMBER = new Intl.NumberFormat("pt-BR", {
  useGrouping: false,
  maximumFractionDigits: 20,
});
const CSV_MONEY = new Intl.NumberFormat("pt-BR", {
  useGrouping: false,
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

export function csvNumber(value: number): string {
  return CSV_NUMBER.format(value);
}

export function csvMoney(value: number): string {
  return CSV_MONEY.format(value);
}

function csvCell(value: CsvCell): string {
  const text = typeof value === "number" ? csvNumber(value) : value;
  return /[";\n\r]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
}

/** CSV para planilhas em português: ponto e vírgula, vírgula decimal e BOM UTF-8. */
export function csvText(table: CsvTable): string {
  const lines = [table.header, ...table.rows].map((row) =>
    row.map(csvCell).join(";"),
  );
  return `\uFEFF${lines.join("\n")}`;
}

/** Lê reais com vírgula ou ponto decimal e devolve centavos inteiros. */
export function csvMoneyToCents(value: string): number | null {
  const clean = value.trim().replace(/\s/g, "");
  if (!clean) return null;
  let normalized = clean;
  if (clean.includes(",")) {
    normalized = clean.replace(/\./g, "").replace(",", ".");
  }
  if (!/^[+-]?\d+(?:\.\d+)?$/.test(normalized)) return null;
  const number = Number(normalized);
  return Number.isFinite(number) ? Math.round(number * 100) : null;
}

function parseLine(line: string): { cells: string[]; invalid: boolean } {
  const cells: string[] = [];
  let cell = "";
  let quoted = false;
  for (let index = 0; index < line.length; index += 1) {
    const char = line[index]!;
    if (char === '"') {
      if (quoted && line[index + 1] === '"') {
        cell += '"';
        index += 1;
      } else {
        quoted = !quoted;
      }
    } else if (char === ";" && !quoted) {
      cells.push(cell);
      cell = "";
    } else {
      cell += char;
    }
  }
  cells.push(cell);
  return { cells, invalid: quoted };
}

/** Leitura estrutural tolerante; erros pertencem à linha que os causou. */
export function parseCsv(text: string): ParsedCsv {
  const lines = text.replace(/^\uFEFF/, "").replace(/\r\n?/g, "\n").split("\n");
  const first = parseLine(lines.shift() ?? "");
  const errors: CsvRowError[] = first.invalid
    ? [{ row: 1, detail: "Aspas não foram fechadas." }]
    : [];
  const rows: string[][] = [];
  lines.forEach((line, index) => {
    if (!line && index === lines.length - 1) return;
    const parsed = parseLine(line);
    const row = index + 2;
    if (parsed.invalid) errors.push({ row, detail: "Aspas não foram fechadas." });
    if (parsed.cells.length !== first.cells.length) {
      errors.push({
        row,
        detail: `A linha tem ${parsed.cells.length} campos; o cabeçalho tem ${first.cells.length}.`,
      });
    }
    rows.push(parsed.cells);
  });
  return { header: first.cells, rows, errors };
}

export function downloadCsv(table: CsvTable, fileName: string): void {
  const blob = new Blob([csvText(table)], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = fileName;
  anchor.click();
  URL.revokeObjectURL(url);
}
