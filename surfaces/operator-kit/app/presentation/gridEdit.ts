// Colar de planilha e pilha de edição do tabelão — puro e determinístico.
//
// A planilha chega como TEXTO (o `paste` do navegador): TSV do Excel/Sheets,
// com fallback para ponto e vírgula e vírgula. Célula vazia não vira valor: quem
// decide o que fazer com vazio é a tela (preço vazio não é zero).

export function parseGrid(text: string): string[][] {
  const clean = String(text ?? "")
    .replace(/\r\n?/g, "\n")
    .replace(/\n+$/, "");
  if (!clean) return [];
  const separator = clean.includes("\t")
    ? "\t"
    : clean.includes(";")
      ? ";"
      : ",";
  return clean
    .split("\n")
    .map((line) => line.split(separator).map((cell) => cell.trim()));
}

/** Preço em pt-BR ("1.234,50") ou simples ("12.50") em centavos; null se inválido. */
export function parseMoneyCell(text: string): number | null {
  const raw = String(text ?? "")
    .replace(/[^\d,.-]/g, "")
    .trim();
  if (!raw) return null;
  const normalized = raw.includes(",")
    ? raw.replace(/\./g, "").replace(",", ".")
    : raw;
  const value = Number(normalized);
  if (!Number.isFinite(value) || value < 0) return null;
  return Math.round(value * 100);
}

/** A identidade de uma célula do tabelão: linha (SKU) + superfície + campo. */
export function editKey(row: string, surface: string, field: string): string {
  return [row, surface, field].join("|");
}

export function splitEditKey(key: string): [string, string, string] {
  const [row = "", surface = "", field = ""] = key.split("|");
  return [row, surface, field];
}
