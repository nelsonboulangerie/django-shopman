// Frases das avaliações do iFood: puras, testáveis sem runtime.
// Copy: inequívoco primeiro (docs/reference/omotenashi-copy.md).
import type { IFoodReviewError, IFoodReviewSummary } from "~/types/ifoodReviews";

/**
 * Política de Avaliações do iFood: o link fica na tela mesmo quando o iFood não
 * responde (exigência da homologação). Espelho de ``POLICY_URL`` na projeção.
 */
export const IFOOD_REVIEW_POLICY_URL = "https://portal.ifood.com.br/evaluation-policies";

/** As abas, com a situação que cada uma pede ao servidor ("" = todas, paginada). */
export type ReviewTab = "waiting" | "replied" | "all";
export const REVIEW_TABS: { value: ReviewTab; label: string; status: string }[] = [
  { value: "waiting", label: "Aguardando resposta", status: "NOT_REPLIED" },
  { value: "replied", label: "Respondidas", status: "REPLIED" },
  { value: "all", label: "Todas", status: "" },
];

/** A aba da query (`?tab=replied`); sem ou desconhecida, a fila de quem responde. */
export function reviewTabFromQuery(value: unknown): ReviewTab {
  const raw = Array.isArray(value) ? value[0] : value;
  return REVIEW_TABS.some((t) => t.value === raw) ? (raw as ReviewTab) : "waiting";
}

/**
 * A recusa como o operador lê: UMA frase em português e, em letra pequena, a
 * mensagem original do iFood (a homologação confere a recusa dele).
 */
export interface ReviewErrorText {
  title: string;
  ifood: string;
}

export function reviewErrorText(
  data: IFoodReviewError | null | undefined,
  fallback: string,
): ReviewErrorText {
  const title = data?.detail?.trim() || fallback;
  const message = data?.ifood_message?.trim() ?? "";
  return { title, ifood: message ? `Mensagem do iFood: ${message}` : "" };
}

/** Contador da resposta: orienta pelo limite do iFood, sem impedir o envio. */
export function replyLengthHint(text: string, min: number, max: number): {
  label: string;
  outside: boolean;
} {
  const length = text.length;
  const outside = length < min || length > max;
  return { label: `${length} de ${min} a ${max} caracteres`, outside };
}

function reviewsCount(n: number): string {
  return `${n} ${n === 1 ? "avaliação" : "avaliações"}`;
}

/**
 * "Nota 4,3 · 142 avaliações". Quando nem todas contam (o iFood só conta os
 * últimos 3 meses), diz quantas e por quê. Sem dado, string vazia.
 */
export function summaryLine(summary: IFoodReviewSummary | null | undefined): string {
  if (!summary || summary.score_display === "") return "";
  const total = summary.total_reviews;
  const valid = summary.valid_reviews;
  if (total === null) return `Nota ${summary.score_display}`;
  const line = `Nota ${summary.score_display} · ${reviewsCount(total)}`;
  if (valid === null || valid === total) return line;
  return `${line} (a nota usa as ${valid} dos últimos 3 meses)`;
}

/** "Página 1 de 5 · 45 avaliações" (ou só a página, sem contagem do iFood). */
export function pageLine(
  page: number,
  pageCount: number | null,
  total: number | null,
): string {
  const of = pageCount ? ` de ${pageCount}` : "";
  return `Página ${page}${of}${total === null ? "" : ` · ${reviewsCount(total)}`}`;
}

/** Cor do selo da situação: só "Aguardando resposta" pede ação. */
export function statusColor(status: string): "warning" | "success" | "neutral" | "error" {
  if (status === "NOT_REPLIED") return "warning";
  if (status === "REPLIED") return "success";
  if (status === "DISCARDED" || status === "INVALID") return "error";
  return "neutral";
}

/** O vazio de cada aba, dito pelo que a aba promete. */
export function emptyTitle(tab: ReviewTab): string {
  if (tab === "waiting") return "Nenhuma avaliação aguardando resposta";
  if (tab === "replied") return "Nenhuma avaliação respondida no período";
  return "Nenhuma avaliação no período";
}
