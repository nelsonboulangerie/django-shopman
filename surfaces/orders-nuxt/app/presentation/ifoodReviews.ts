// Frases das avaliações do iFood: puras, testáveis sem runtime.
// Copy: inequívoco primeiro (docs/reference/omotenashi-copy.md).
import type { IFoodReviewError, IFoodReviewSummary } from "~/types/ifoodReviews";

/**
 * Política de Avaliações do iFood: o link fica na tela mesmo quando o iFood não
 * responde (exigência da homologação). Espelho de ``POLICY_URL`` na projeção.
 */
export const IFOOD_REVIEW_POLICY_URL = "https://portal.ifood.com.br/evaluation-policies";

/** A recusa como o operador lê: a frase da casa e, embaixo, o que o iFood respondeu. */
export interface ReviewErrorText {
  title: string;
  ifood: string;
}

export function reviewErrorText(
  data: IFoodReviewError | null | undefined,
  fallback: string,
): ReviewErrorText {
  const title = data?.detail?.trim() || fallback;
  const status = data?.ifood_status ?? 0;
  const message = data?.ifood_message?.trim() ?? "";
  if (!status) return { title, ifood: "" };
  return {
    title,
    ifood: message
      ? `Resposta do iFood (HTTP ${status}): ${message}`
      : `Resposta do iFood: HTTP ${status}`,
  };
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

/** "Nota 4,3 · 142 avaliações (53 contam na nota)". Sem dado, string vazia. */
export function summaryLine(summary: IFoodReviewSummary | null | undefined): string {
  if (!summary || summary.score_display === "") return "";
  const parts = [`Nota ${summary.score_display}`];
  if (summary.total_reviews !== null) {
    const total = summary.total_reviews;
    parts.push(`${total} ${total === 1 ? "avaliação" : "avaliações"}`);
  }
  const line = parts.join(" · ");
  return summary.valid_reviews !== null
    ? `${line} (${summary.valid_reviews} contam na nota)`
    : line;
}

/** "Página 1 de 5 · 45 avaliações" (ou só a página, sem contagem do iFood). */
export function pageLine(
  page: number,
  pageCount: number | null,
  total: number | null,
): string {
  const of = pageCount ? ` de ${pageCount}` : "";
  const count =
    total === null ? "" : ` · ${total} ${total === 1 ? "avaliação" : "avaliações"}`;
  return `Página ${page}${of}${count}`;
}

/** Cor do selo da situação: só "Aguardando resposta" pede ação. */
export function statusColor(status: string): "warning" | "success" | "neutral" | "error" {
  if (status === "NOT_REPLIED") return "warning";
  if (status === "REPLIED") return "success";
  if (status === "DISCARDED" || status === "INVALID") return "error";
  return "neutral";
}
