// Tabelão de produtos: colunas, validação na hora, colar de planilha e o lote.
//
// Puro e determinístico. O servidor é a régua (o mesmo escritor do painel); a
// validação daqui só existe para o operador ver o erro na célula ANTES de salvar,
// com as mesmas regras do fiscalman (NCM de 8 dígitos, CEST de 7, perfil que
// exige CEST). CFOP e CSOSN não são colunas: saem do perfil fiscal do contador.

import { parseGrid, parseMoneyCell } from "../../../operator-kit/app/presentation/gridEdit";
import type {
  ProductSheetChoice,
  ProductSheetProfile,
  ProductSheetRow,
  ProductSheetRowPatch,
} from "~/types/catalog";

export const SHEET_COLUMNS = [
  "name",
  "short_description",
  "price",
  "by_weight",
  "profile",
  "ncm",
  "cest",
  "origin",
] as const;
export type SheetColumn = (typeof SHEET_COLUMNS)[number];
export type SheetValue = string | boolean;

export const SHEET_COLUMN_LABELS: Record<SheetColumn, string> = {
  name: "Nome",
  short_description: "Descrição curta",
  price: "Preço (R$)",
  by_weight: "Vendido por peso",
  profile: "Perfil fiscal",
  ncm: "NCM",
  cest: "CEST",
  origin: "Origem",
};

export const sheetKey = (sku: string, column: SheetColumn) => `${sku}|${column}`;

export function splitSheetKey(key: string): [string, SheetColumn] {
  const cut = key.lastIndexOf("|");
  return [key.slice(0, cut), key.slice(cut + 1) as SheetColumn];
}

const centsToText = (q: number) => (q / 100).toFixed(2).replace(".", ",");
const digits = (text: string) => text.replace(/\D/g, "");

/** O valor do servidor na forma que a célula mostra. */
export function serverValue(row: ProductSheetRow, column: SheetColumn): SheetValue {
  switch (column) {
    case "name":
      return row.name;
    case "short_description":
      return row.short_description;
    case "price":
      return centsToText(row.base_price_q);
    case "by_weight":
      return row.unit === "kg";
    default:
      return row.fiscal[column] ?? "";
  }
}

export function cellValue(
  row: ProductSheetRow,
  column: SheetColumn,
  draft: Record<string, SheetValue>,
): SheetValue {
  const value = draft[sheetKey(row.sku, column)];
  return value === undefined ? serverValue(row, column) : value;
}

const BOOL_TOKENS: Record<string, boolean> = {
  sim: true, s: true, x: true, kg: true, "1": true, verdadeiro: true, true: true,
  não: false, nao: false, n: false, "0": false, un: false, falso: false, false: false, "": false,
};

/**
 * Lê o texto colado para a coluna. ``undefined`` = o texto não serve a esta
 * coluna e a célula fica como estava (não vira vazio nem zero sozinha).
 */
export function pastedValue(
  column: SheetColumn,
  text: string,
  choices: { profiles: ProductSheetProfile[]; origins: ProductSheetChoice[] },
): SheetValue | undefined {
  const raw = text.trim();
  if (column === "by_weight") return BOOL_TOKENS[raw.toLowerCase()];
  if (column === "profile") {
    const found = choices.profiles.find(
      (choice) => choice.key === raw || choice.name.toLowerCase() === raw.toLowerCase(),
    );
    return found?.key;
  }
  if (column === "origin") {
    const code = raw.match(/^\d/)?.[0];
    return choices.origins.some((choice) => choice.key === code) ? code : undefined;
  }
  if (column === "ncm" || column === "cest") return digits(raw);
  return raw;
}

/**
 * Cola um bloco da planilha a partir da célula focada: linhas descem pelos
 * produtos visíveis, colunas andam para a direita na ordem do tabelão.
 */
export function pasteBlock(
  text: string,
  start: { skus: string[]; sku: string; column: SheetColumn },
  choices: { profiles: ProductSheetProfile[]; origins: ProductSheetChoice[] },
): { key: string; value: SheetValue }[] {
  const grid = parseGrid(text);
  const firstRow = start.skus.indexOf(start.sku);
  const firstColumn = SHEET_COLUMNS.indexOf(start.column);
  if (!grid.length || firstRow < 0 || firstColumn < 0) return [];
  const edits: { key: string; value: SheetValue }[] = [];
  grid.forEach((line, rowOffset) => {
    const sku = start.skus[firstRow + rowOffset];
    if (!sku) return;
    line.forEach((cell, columnOffset) => {
      const column = SHEET_COLUMNS[firstColumn + columnOffset];
      if (!column || cell === "") return;
      const value = pastedValue(column, cell, choices);
      if (value !== undefined) edits.push({ key: sheetKey(sku, column), value });
    });
  });
  return edits;
}

/** Erros da linha por coluna, com o rascunho aplicado: o que o servidor recusaria. */
export function rowProblems(
  row: ProductSheetRow,
  draft: Record<string, SheetValue>,
  profiles: ProductSheetProfile[],
): Partial<Record<SheetColumn, string>> {
  const value = (column: SheetColumn) => String(cellValue(row, column, draft));
  const problems: Partial<Record<SheetColumn, string>> = {};
  const name = value("name").trim();
  if (!name) problems.name = "Informe o nome.";
  else if (name.length > 200) problems.name = "No máximo 200 letras.";
  if (parseMoneyCell(value("price")) === null) problems.price = "Preço inválido.";
  const ncm = value("ncm");
  const cest = value("cest");
  if (ncm || cest) {
    const profile = profiles.find((choice) => choice.key === value("profile"));
    if (!profile) problems.profile = "Escolha o perfil fiscal.";
    if (!/^\d{8}$/.test(ncm)) problems.ncm = "O NCM tem 8 dígitos.";
    if (cest && !/^\d{7}$/.test(cest)) problems.cest = "O CEST tem 7 dígitos.";
    else if (profile?.requires_cest && !cest)
      problems.cest = "Este perfil pede o CEST.";
  }
  return problems;
}

/**
 * Transforma o rascunho em linhas do lote: só o que mudou de verdade, cada
 * folha com a revisão que o operador viu. Linha com erro fica de fora.
 */
export function buildRowPatches(
  rows: ProductSheetRow[],
  draft: Record<string, SheetValue>,
  profiles: ProductSheetProfile[],
): { patches: ProductSheetRowPatch[]; blocked: string[] } {
  const patches: ProductSheetRowPatch[] = [];
  const blocked: string[] = [];
  for (const row of rows) {
    const changed = SHEET_COLUMNS.filter(
      (column) =>
        sheetKey(row.sku, column) in draft &&
        cellValue(row, column, draft) !== serverValue(row, column),
    );
    if (!changed.length) continue;
    if (Object.keys(rowProblems(row, draft, profiles)).length) {
      blocked.push(row.sku);
      continue;
    }
    const patch: ProductSheetRowPatch["patch"] = {};
    const revisions: Record<string, string> = {};
    const take = (path: string) => {
      revisions[path] = row.revisions[path] ?? "";
    };
    for (const column of changed) {
      const value = cellValue(row, column, draft);
      if (column === "name" || column === "short_description") {
        patch[column] = String(value).trim();
        take(column);
      } else if (column === "price") {
        const cents = parseMoneyCell(String(value));
        if (cents === row.base_price_q) continue;
        patch.base_price_q = cents ?? row.base_price_q;
        take("base_price_q");
      } else if (column === "by_weight") {
        // Desligar o peso devolve a unidade padrão; outra unidade se edita no painel.
        patch.unit = value ? "kg" : "un";
        take("unit");
      } else {
        patch.fiscal = { ...patch.fiscal, [column]: String(value) };
        take(`fiscal.${column}`);
      }
    }
    if (Object.keys(patch).length)
      patches.push({ sku: row.sku, patch, base_revisions: revisions });
  }
  return { patches, blocked };
}

/** As chaves do rascunho que uma linha aplicada confirmou. */
export function confirmedKeys(sku: string): string[] {
  return SHEET_COLUMNS.map((column) => sheetKey(sku, column));
}

const FIELD_LABELS: Record<string, string> = {
  name: "Nome",
  short_description: "Descrição curta",
  base_price_q: "Preço",
  unit: "Vendido por peso",
  "fiscal.profile": "Perfil fiscal",
  "fiscal.ncm": "NCM",
  "fiscal.cest": "CEST",
  "fiscal.origin": "Origem",
};

/** "Nome, Preço: o produto mudou…" — o conflito diz em que campo foi. */
export function failureText(detail: string, fields?: string[]): string {
  if (!fields?.length) return detail;
  return `${fields.map((field) => FIELD_LABELS[field] ?? field).join(", ")}: ${detail}`;
}
