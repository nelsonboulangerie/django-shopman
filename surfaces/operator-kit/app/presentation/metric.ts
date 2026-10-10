// O contrato da `OperatorMetric` (PR-K2 do WP-BI-CANON-LAUDO).
//
// A peça não calcula nada: recebe a figura já formatada e o delta já pronto da
// presentation de quem a usa. É o mesmo formato que o B.I. já monta para a
// comparação com o período anterior (`delta()` em `bi-nuxt/app/presentation/bi.ts`),
// para o B.I. trocar `StatTile` por esta peça sem reescrever a regra do delta.

/** Cor por MELHOROU/PIOROU, nunca por sinal: perda subindo é `negative`. */
export type MetricDeltaTone = "positive" | "negative" | "neutral";

export interface MetricDelta {
  /** A frase inteira, para leitor de tela: "queda de 23% vs período anterior (3.384)". */
  text: string;
  tone: MetricDeltaTone;
  /** A pílula: "23%". Vazia quando não há base de comparação. */
  percent: string;
  direction: "up" | "down" | "flat" | "none";
  /** O que vem depois da pílula: "vs período anterior (3.384)". */
  caption: string;
}

/** O tom da figura quando ela É um veredito (faltou, sobrou, na medida). */
export type MetricTone = "error" | "warning" | "success";

/**
 * Tamanho da figura:
 * - `figure`: o número do cartão, em grade de três ou quatro;
 * - `hero`: o número sozinho e maior (o faturamento no celular);
 * - `statement`: a resposta em uma frase ("Faltou pão de queijo em 3 dos 7 dias"),
 *   quando o que o cartão diz não é número.
 */
export type MetricSize = "figure" | "hero" | "statement";

export const METRIC_DELTA_COLOR = {
  positive: "success",
  negative: "error",
  neutral: "neutral",
} as const satisfies Record<MetricDeltaTone, string>;

export const METRIC_DELTA_ICON = {
  up: "i-lucide-trending-up",
  down: "i-lucide-trending-down",
  flat: "i-lucide-minus",
  none: undefined,
} as const satisfies Record<MetricDelta["direction"], string | undefined>;

export const METRIC_TONE_CLASS = {
  error: "text-error",
  warning: "text-warning",
  success: "text-success",
} as const satisfies Record<MetricTone, string>;

export const METRIC_SIZE_CLASS = {
  figure: "op-figure",
  hero: "op-display tnum",
  statement: "op-title",
} as const satisfies Record<MetricSize, string>;
