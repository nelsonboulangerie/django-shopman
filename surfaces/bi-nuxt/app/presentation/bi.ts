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
  // 12 meses só faz sentido com o histórico Yooga ingerido (BI-PLAN F6).
  { days: 365, label: "12 meses" },
];

export interface SalesDayLike {
  date: string;
  orders: number;
  revenue_q: number;
  source: string;
}

/** Um balde da série de vendas: um dia, ou uma semana quando a janela é longa. */
export interface SalesBucket {
  date: string;
  orders: number;
  revenue_q: number;
  source: string;
  weekly: boolean;
}

/**
 * Janela longa não cabe em barras diárias: acima de `maxDaily` dias, agrega
 * por semana (segunda-feira). Um balde é "yooga" só se TODO dia com venda
 * nele for histórico — semana mista veste a cor nativa (a legenda cobre).
 */
export function bucketSalesDays(days: readonly SalesDayLike[], maxDaily = 120): SalesBucket[] {
  if (days.length <= maxDaily) {
    return days.map((d) => ({ ...d, weekly: false }));
  }
  const buckets = new Map<string, SalesBucket>();
  for (const day of days) {
    const parsed = new Date(`${day.date}T12:00:00`);
    parsed.setDate(parsed.getDate() - ((parsed.getDay() + 6) % 7)); // segunda
    const key = parsed.toISOString().slice(0, 10);
    const bucket = buckets.get(key) ?? {
      date: key, orders: 0, revenue_q: 0, source: "yooga", weekly: true,
    };
    bucket.orders += day.orders;
    bucket.revenue_q += day.revenue_q;
    if (day.orders > 0 && day.source !== "yooga") bucket.source = "shopman";
    buckets.set(key, bucket);
  }
  return [...buckets.values()].sort((a, b) => a.date.localeCompare(b.date));
}
