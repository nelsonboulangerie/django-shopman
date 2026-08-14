// Presentation pura do B.I. — copy pt-BR e formatação; a projection manda os
// dados crus (centavos `_q`, quantidades string, datas ISO) e AQUI eles viram
// texto. Números em gráfico usam tokens de texto, nunca a cor da série.

const moneyFmt = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" });
const intFmt = new Intl.NumberFormat("pt-BR");

/** Centavos → "R$ 1.234,56". */
export function formatMoney(cents: number): string {
  return moneyFmt.format(cents / 100);
}

/** Centavos → "R$ 1,2 mil" curto para tiles/eixos (mantém leitura num relance). */
export function formatMoneyCompact(cents: number): string {
  const value = cents / 100;
  if (Math.abs(value) >= 1000) {
    return `R$ ${intFmt.format(Math.round(value / 100) / 10)} mil`;
  }
  return moneyFmt.format(value);
}

export function formatInt(value: number): string {
  return intFmt.format(value);
}

/** Quantidade string da projection ("38.5") → "38,5". */
export function formatQty(value: string): string {
  return value.replace(".", ",");
}

/** Minutos string ("23.5") → "23,5 min". */
export function formatMinutes(value: string): string {
  return `${value.replace(".", ",")} min`;
}

/** ISO "2026-08-14" → "14/08". */
export function shortDate(iso: string): string {
  const [, month, day] = iso.split("-");
  return `${day}/${month}`;
}

/** 0 = segunda (convenção da projection). */
export const WEEKDAY_LABELS = ["seg", "ter", "qua", "qui", "sex", "sáb", "dom"] as const;

export function hourLabel(hour: number): string {
  return `${hour}h`;
}

/** Cobertura da medição de forno, sempre com o denominador à vista. */
export function coverageLabel(measured: number, finished: number): string {
  if (!finished) return "sem fornadas no período";
  return `${formatInt(measured)} de ${formatInt(finished)} fornadas medidas`;
}

export interface WindowPreset {
  days: number;
  label: string;
}

export const WINDOW_PRESETS: readonly WindowPreset[] = [
  { days: 7, label: "7 dias" },
  { days: 28, label: "28 dias" },
  { days: 90, label: "90 dias" },
];
