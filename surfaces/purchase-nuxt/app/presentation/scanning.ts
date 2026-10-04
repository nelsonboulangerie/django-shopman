// O que a câmera do receber lê, traduzido para a conferência (V6-COMPRAS).
//
// - **GS1** (C21, "Ler da embalagem"): o código da caixa (GS1-128 ou GS1
//   DataMatrix) carrega a validade (AI 17), o "consumir antes de" (AI 15) e o
//   lote do fornecedor (AI 10). Lê os dois jeitos que a câmera devolve: com os
//   parênteses ("(17)261012(10)L42") ou cru, com o separador FNC1 (GS, 0x1D).
// - **EAN** (C11, "Ler EAN"): acha o item da entrada pelo código da caixa ou da
//   unidade que a nota trouxe, ou pelo EAN que o cadastro de compra já conhece.
import type { Material, ReceiptLine } from "~/types/purchase";

const GS = String.fromCharCode(29);

/** AIs de tamanho fixo (dígitos de dado depois do AI de 2 dígitos). */
const FIXED_2: Record<string, number> = {
  "00": 18,
  "01": 14,
  "02": 14,
  "11": 6,
  "12": 6,
  "13": 6,
  "15": 6,
  "16": 6,
  "17": 6,
  "20": 2,
};
/** AIs de tamanho variável (até o separador ou o fim). */
const VARIABLE_2 = new Set(["10", "21", "22", "30", "37", "90", "91", "92", "93", "94", "95", "96", "97", "98", "99"]);

export interface Gs1Reading {
  gtin: string;
  /** Validade ISO ("2026-10-12"): AI 17, ou AI 15 quando só há "consumir antes de". */
  expiry: string;
  lot: string;
}

function yymmddToIso(raw: string): string {
  if (!/^\d{6}$/.test(raw)) return "";
  const yy = Number(raw.slice(0, 2));
  const mm = Number(raw.slice(2, 4));
  let dd = Number(raw.slice(4, 6));
  if (mm < 1 || mm > 12) return "";
  // Século pela janela GS1: até 49 anos à frente é 20xx.
  const year = yy <= 49 ? 2000 + yy : 1900 + yy;
  // Dia 00 = último dia do mês (regra GS1).
  if (dd === 0) dd = new Date(Date.UTC(year, mm, 0)).getUTCDate();
  const date = new Date(Date.UTC(year, mm - 1, dd));
  if (date.getUTCMonth() !== mm - 1) return "";
  return date.toISOString().slice(0, 10);
}

function parseParenthesized(text: string): Record<string, string> {
  const out: Record<string, string> = {};
  const re = /\((\d{2,4})\)([^(]*)/g;
  let match: RegExpExecArray | null;
  while ((match = re.exec(text))) out[match[1]!] = match[2]!.trim();
  return out;
}

function parseRaw(text: string): Record<string, string> {
  const out: Record<string, string> = {};
  // Símbolos de identificação que alguns leitores devolvem na frente.
  let rest = text.replace(/^\]([CdQe])\d/, "").replace(/^è/, "");
  let guard = 0;
  while (rest.length >= 2 && guard++ < 20) {
    if (rest.startsWith(GS)) {
      rest = rest.slice(1);
      continue;
    }
    const ai2 = rest.slice(0, 2);
    if (ai2 in FIXED_2) {
      const size = FIXED_2[ai2]!;
      out[ai2] = rest.slice(2, 2 + size);
      rest = rest.slice(2 + size);
      continue;
    }
    // Pesos e medidas: AI de 4 dígitos (310n…369n) + 6 dígitos.
    if (/^3[1-6]\d\d/.test(rest)) {
      out[rest.slice(0, 4)] = rest.slice(4, 10);
      rest = rest.slice(10);
      continue;
    }
    if (VARIABLE_2.has(ai2)) {
      const end = rest.indexOf(GS, 2);
      out[ai2] = end === -1 ? rest.slice(2) : rest.slice(2, end);
      rest = end === -1 ? "" : rest.slice(end + 1);
      continue;
    }
    break;
  }
  return out;
}

/** Lê validade, lote e GTIN de um código GS1. `null` quando não é GS1. */
export function parseGs1(text: string): Gs1Reading | null {
  const raw = (text ?? "").trim();
  if (!raw) return null;
  const fields = raw.includes("(") ? parseParenthesized(raw) : parseRaw(raw);
  const expiry = yymmddToIso(fields["17"] ?? "") || yymmddToIso(fields["15"] ?? "");
  const lot = (fields["10"] ?? "").slice(0, 20);
  const gtin = fields["01"] ?? fields["02"] ?? "";
  if (!expiry && !lot && !gtin) return null;
  return { gtin, expiry, lot };
}

/** Só os dígitos de um EAN/GTIN, sem zeros de enchimento à esquerda (GTIN-14 → 13). */
export function normalizeGtin(code: string): string {
  const digits = String(code ?? "").replace(/\D/g, "");
  return digits.replace(/^0+(?=\d{8})/, "");
}

/** O item da entrada que este código de barras identifica, ou `null`. */
export function receiptLineForEan(
  code: string,
  lines: readonly ReceiptLine[],
  materials: readonly Material[],
): ReceiptLine | null {
  const wanted = normalizeGtin(code);
  if (!wanted) return null;
  const same = (value?: string) => Boolean(value) && normalizeGtin(value!) === wanted;
  const byInvoice = lines.find(
    (line) => same(line.invoiceEan) || same(line.invoicePackageEan) || same(line.scannedEan),
  );
  if (byInvoice) return byInvoice;
  const material = materialForEan(code, materials);
  return material ? (lines.find((line) => line.materialSku === material.sku) ?? null) : null;
}

/** O insumo cujo cadastro de compra já conhece este EAN, ou `null`. */
export function materialForEan(code: string, materials: readonly Material[]): Material | null {
  const wanted = normalizeGtin(code);
  if (!wanted) return null;
  return materials.find((material) => (material.eans ?? []).some((ean) => normalizeGtin(ean) === wanted)) ?? null;
}
