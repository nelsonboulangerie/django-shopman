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

/**
 * Delta vs o período anterior (F7). Sem base = diz que não há base — nunca
 * um "+∞" fingido. Sem cor: a semântica de "subir" muda por métrica (perda
 * subindo é ruim; faturamento subindo é bom), e cor é só funcional no DS.
 */
export function deltaLabel(current: number, previous: number): string {
  if (!previous) return "sem base anterior";
  const pct = Math.round(((current - previous) / Math.abs(previous)) * 100);
  if (pct === 0) return "estável vs anterior";
  return `${pct > 0 ? "▲" : "▼"} ${Math.abs(pct)}% vs anterior`;
}

/** Cobertura da medição de forno, sempre com o denominador à vista. */
export function coverageLabel(measured: number, finished: number): string {
  if (!finished) return "sem fornadas no período";
  return `${formatInt(measured)} de ${formatInt(finished)} fornadas medidas`;
}

// ── Janela de análise ────────────────────────────────────────────────────────
// Padrão de bolsa nos chips (1 toque), vocabulário de varejo onde importa
// ("No ano" = YTD) e "Máx" cobrindo o histórico inteiro (Yooga, jul/2024).

/** Primeiro dado da casa (export Yooga começa em jul/2024; folga no mês). */
export const DATA_EPOCH = "2024-01-01";

export interface WindowPreset {
  key: string;
  label: string;
  days?: number; // ausente = resolvido por regra (ytd/max)
}

export const WINDOW_PRESETS: readonly WindowPreset[] = [
  { key: "1d", label: "1D", days: 1 },
  { key: "7d", label: "7D", days: 7 },
  // 28 e não 30: quatro semanas exatas têm o mesmo mix de dias-da-semana,
  // então médias e comparações não mentem (sábado ≠ terça numa padaria).
  { key: "28d", label: "28D", days: 28 },
  { key: "3m", label: "3M", days: 90 },
  { key: "6m", label: "6M", days: 180 },
  { key: "12m", label: "12M", days: 365 },
  { key: "ytd", label: "No ano" },
  { key: "max", label: "Máx" },
];

export interface WindowSelection {
  preset: string; // key de WINDOW_PRESETS ou "custom"
  from: string; // ISO, só para custom
  to: string; // ISO, só para custom
}

/** Resolve a seleção em date_from/date_to (o backend normaliza e clampa). */
export function resolveWindowRange(
  selection: WindowSelection,
  today: Date = new Date(),
): { date_from: string; date_to: string } {
  const iso = (d: Date) => d.toISOString().slice(0, 10);
  const to = iso(today);
  if (selection.preset === "custom" && selection.from && selection.to) {
    return { date_from: selection.from, date_to: selection.to };
  }
  if (selection.preset === "ytd") {
    return { date_from: `${today.getFullYear()}-01-01`, date_to: to };
  }
  if (selection.preset === "max") {
    return { date_from: DATA_EPOCH, date_to: to };
  }
  const preset = WINDOW_PRESETS.find((p) => p.key === selection.preset);
  const days = preset?.days ?? 28;
  return { date_from: iso(new Date(today.getTime() - (days - 1) * 86_400_000)), date_to: to };
}

// ── Agrupamento de séries longas ─────────────────────────────────────────────

export type BucketSpan = "day" | "week" | "month";

export const BUCKET_SPAN_LABELS: Record<BucketSpan, string> = {
  day: "", // dia é o grão natural: não precisa se anunciar
  week: "semana",
  month: "mês",
};

const MONTH_ABBR = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"];

/** Rótulo do balde: dia/semana viram "14/08"; mês vira "ago/25". */
export function bucketLabel(date: string, span: BucketSpan): string {
  if (span !== "month") return shortDate(date);
  const [year, month] = date.split("-");
  return `${MONTH_ABBR[Number(month) - 1]}/${year!.slice(2)}`;
}

/**
 * Série longa não cabe em barras diárias: acima de `maxDaily` dias agrega por
 * semana (segunda-feira) e, acima de ~2 anos, por mês. Devolve os dias de cada
 * balde para a página somar do jeito da métrica dela.
 */
export function bucketRows<T extends { date: string }>(
  rows: readonly T[],
  maxDaily = 120,
): { date: string; span: BucketSpan; rows: T[] }[] {
  const span: BucketSpan = rows.length <= maxDaily ? "day" : rows.length <= 740 ? "week" : "month";
  if (span === "day") {
    return rows.map((row) => ({ date: row.date, span, rows: [row] }));
  }
  const buckets = new Map<string, { date: string; span: BucketSpan; rows: T[] }>();
  for (const row of rows) {
    let key: string;
    if (span === "month") {
      key = `${row.date.slice(0, 7)}-01`;
    } else {
      const parsed = new Date(`${row.date}T12:00:00`);
      parsed.setDate(parsed.getDate() - ((parsed.getDay() + 6) % 7)); // segunda
      key = parsed.toISOString().slice(0, 10);
    }
    const bucket = buckets.get(key) ?? { date: key, span, rows: [] };
    bucket.rows.push(row);
    buckets.set(key, bucket);
  }
  return [...buckets.values()].sort((a, b) => a.date.localeCompare(b.date));
}

export interface SalesDayLike {
  date: string;
  orders: number;
  revenue_q: number;
  source: string;
  /** Faturamento do dia correspondente do período anterior (F7, alinhado). */
  prev_revenue_q?: number;
}

/** Um balde da série de vendas (dia, semana ou mês, conforme a janela). */
export interface SalesBucket {
  date: string;
  orders: number;
  revenue_q: number;
  prev_revenue_q: number;
  source: string;
  span: BucketSpan;
}

/**
 * Um balde é "yooga" só se TODO dia com venda nele for histórico — balde
 * misto veste a cor nativa (a legenda cobre).
 */
export function bucketSalesDays(days: readonly SalesDayLike[], maxDaily = 120): SalesBucket[] {
  return bucketRows(days, maxDaily).map((bucket) => {
    const withSales = bucket.rows.filter((d) => d.orders > 0);
    return {
      date: bucket.date,
      span: bucket.span,
      orders: bucket.rows.reduce((sum, d) => sum + d.orders, 0),
      revenue_q: bucket.rows.reduce((sum, d) => sum + d.revenue_q, 0),
      prev_revenue_q: bucket.rows.reduce((sum, d) => sum + (d.prev_revenue_q ?? 0), 0),
      source: withSales.length && withSales.every((d) => d.source === "yooga") ? "yooga" : "shopman",
    };
  });
}
