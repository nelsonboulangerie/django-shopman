// Presentation — fechamento do DIA (contagem cega de sobras/perdas).
//
// Transforms puras sobre a DayClosingProjection. As BADGES derivam de
// `classification` AQUI (a projection não carrega presentation — cada app
// decide a própria pele). Desde o C4 o LOTE decide o destino da sobra: o
// que tem validade FICA; o que vence hoje (ou está marcado) vira perda no
// fechamento — nada se move de posição.

import type {
  ClosingItemProjection,
  ClosingPendingProduction,
  ClosingProductionRow,
} from "~/types/closing";

export interface ClosingBadge {
  label: string;
  css: string;
}

export function closingBadge(classification: string): ClosingBadge {
  if (classification === "expired") {
    return { label: "Vira perda", css: "border-destructive/50 bg-destructive/10 text-destructive" };
  }
  if (classification === "mixed") {
    return { label: "Parte vence", css: "border-warning/50 bg-warning/10 text-warning" };
  }
  return { label: "Fica", css: "border-border bg-muted text-muted-foreground" };
}

/** Linhas da tabela "Produção do dia" (SKU · planejado · feito · perda). */
export function productionRows(
  summary: Record<string, ClosingProductionRow> | null | undefined,
): Array<{ sku: string; planned: number; finished: number; loss: number }> {
  if (!summary) return [];
  return Object.entries(summary)
    .map(([recipeRef, row]) => ({
      sku: row.output_sku || recipeRef,
      planned: row.planned ?? 0,
      finished: row.finished ?? 0,
      loss: row.loss ?? 0,
    }))
    .sort((a, b) => a.sku.localeCompare(b.sku));
}

/** Status da produção pendente, marcando atraso como o Admin fazia. */
export function pendingStatusDisplay(row: ClosingPendingProduction): string {
  return row.is_overdue ? `${row.status_label} (atrasada)` : row.status_label;
}

/** Contagem cega: só dígitos (quantidades inteiras, nunca negativas). */
export function sanitizeQtyInput(raw: string): string {
  return raw.replace(/\D/g, "");
}

/** O formulário só envia quando TODO item tem uma contagem explícita. */
export function allQuantitiesFilled(
  items: ClosingItemProjection[],
  inputs: Record<string, string>,
): boolean {
  if (!items.length) return false;
  return items.every((item) => /^\d+$/.test((inputs[item.sku] ?? "").trim()));
}

/**
 * O primeiro item cuja contagem ainda não vale — é ELE que a dica acusa.
 *
 * "Preencha todos os itens" com a tela toda aparentemente preenchida era uma
 * dica que mandava procurar sem dizer onde: um "1,5" colado deixava o campo
 * com texto e o CTA travado. A dica agora aponta o item, e o `@input`
 * sanitizado torna o caso raro — mas colar acontece, e a dica tem de saber
 * responder.
 */
export function firstUnfilledItemName(
  items: ClosingItemProjection[],
  inputs: Record<string, string>,
): string {
  const pendente = items.find((item) => !/^\d+$/.test((inputs[item.sku] ?? "").trim()));
  return pendente ? pendente.name || pendente.sku : "";
}

/** Payload do POST: { sku: "qty" } com tudo validado. */
export function buildQuantitiesPayload(
  items: ClosingItemProjection[],
  inputs: Record<string, string>,
): Record<string, string> {
  const payload: Record<string, string> = {};
  for (const item of items) {
    payload[item.sku] = String(parseInt((inputs[item.sku] ?? "0").trim() || "0", 10));
  }
  return payload;
}

/**
 * A ordem da contagem é a do NOME, não a do SKU: o operador anda pela vitrine
 * lendo etiquetas, e "BAG-01, CRO-02" não é o que está escrito nelas.
 */
export function closingCountOrder(items: ClosingItemProjection[]): ClosingItemProjection[] {
  return [...items].sort((a, b) => (a.name || a.sku).localeCompare(b.name || b.sku, "pt-BR"));
}

/** Quantos itens já têm contagem que vale — o "12 de 30" do progresso. */
export function countedItems(
  items: ClosingItemProjection[],
  inputs: Record<string, string>,
): number {
  return items.filter((item) => /^\d+$/.test((inputs[item.sku] ?? "").trim())).length;
}

// ── Fim do dia em corredor (V4-PDV, `fim-do-dia.jpg`) ──────────────────────────

/**
 * O resumo da vitrine no passo 3, em PEÇAS e só com o que o operador contou: quanto
 * fica para amanhã, quanto vira perda e quanto é de lote misto (parte vence; quanto
 * exatamente, só o servidor sabe, e ele não diz antes do registro). Nunca dinheiro.
 */
export interface ClosingCountSummary {
  keep: number;
  loss: number;
  mixed: number;
}

export function closingCountSummary(
  items: ClosingItemProjection[],
  inputs: Record<string, string>,
): ClosingCountSummary {
  const summary: ClosingCountSummary = { keep: 0, loss: 0, mixed: 0 };
  for (const item of items) {
    const raw = (inputs[item.sku] ?? "").trim();
    if (!/^\d+$/.test(raw)) continue;
    const qty = Number(raw);
    if (item.classification === "expired") summary.loss += qty;
    else if (item.classification === "mixed") summary.mixed += qty;
    else summary.keep += qty;
  }
  return summary;
}

/** "1 peça" / "22 peças". */
export function piecesLabel(count: number): string {
  return count === 1 ? "1 peça" : `${count} peças`;
}

/** Os três passos do corredor, com o estado de cada um (nunca valor). */
export interface ClosingStepView {
  key: "cash" | "count" | "day";
  label: string;
  detail: string;
  state: "done" | "current" | "todo";
}

export function closingSteps(input: {
  /** Turno da gaveta aberto? `null` quando a leitura do terminal não respondeu. */
  cashOpen: boolean | null;
  counted: number;
  total: number;
  step: "count" | "day";
  dayClosed: boolean;
}): ClosingStepView[] {
  const cash: ClosingStepView = input.cashOpen === false
    ? { key: "cash", label: "Fechar caixa", detail: "contagem registrada", state: "done" }
    : {
        key: "cash",
        label: "Fechar caixa",
        detail: input.cashOpen ? "caixa aberto" : "contagem cega",
        state: input.cashOpen ? "current" : "todo",
      };
  const countDone = input.dayClosed || (input.step === "day" && input.total > 0 && input.counted === input.total);
  const count: ClosingStepView = {
    key: "count",
    label: "Contar a vitrine",
    detail: input.dayClosed ? "conferido" : input.total ? `${input.counted} de ${input.total}` : "nada a contar",
    state: countDone ? "done" : input.step === "count" ? "current" : "todo",
  };
  const day: ClosingStepView = {
    key: "day",
    label: "Fechar o dia",
    detail: input.dayClosed ? "fechado" : "resumo e selo",
    state: input.dayClosed ? "done" : input.step === "day" ? "current" : "todo",
  };
  return [cash, count, day];
}
