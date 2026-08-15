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

export type DeltaTone = "positive" | "negative" | "neutral";

export interface DeltaBadge {
  text: string;
  tone: DeltaTone;
}

/**
 * Delta vs o período anterior (F7). Sem base = travessão de dado ausente
 * (decisão do dono; a proibição do travessão vale para prosa, não para
 * placeholder). O tom veste os tokens semânticos dessaturados do tema
 * (success/destructive): cor por MELHOROU/PIOROU, não por sinal — perda
 * subindo é ruim, faturamento subindo é bom (`downIsGood` inverte).
 */
export function delta(
  current: number,
  previous: number,
  opts: { downIsGood?: boolean } = {},
): DeltaBadge {
  if (!previous) return { text: "—", tone: "neutral" };
  const pct = Math.round(((current - previous) / Math.abs(previous)) * 100);
  if (pct === 0) return { text: "Estável vs Período anterior", tone: "neutral" };
  const improved = pct > 0 !== Boolean(opts.downIsGood);
  return {
    text: `${pct > 0 ? "▲" : "▼"} ${Math.abs(pct)}% vs Período anterior`,
    tone: improved ? "positive" : "negative",
  };
}

/** Cobertura da medição de forno, sempre com o denominador à vista. */
export function coverageLabel(measured: number, finished: number): string {
  if (!finished) return "Sem fornadas no período";
  return `${formatInt(measured)} de ${formatInt(finished)} fornadas medidas`;
}

// ── Janela de análise ────────────────────────────────────────────────────────
// Dois vocabulários que coexistem (decisão do dono): "Período atual" é
// CALENDÁRIO (o dia/semana/mês/ano corrente, do início até hoje) e "Últimos"
// são as janelas MÓVEIS de bolsa (7D…5A; Máx cobre o histórico inteiro).

/** Primeiro dado da casa (export Yooga começa em jul/2024; folga no mês). */
export const DATA_EPOCH = "2024-01-01";

/** Formata um valor do explorador conforme a unidade do contrato. */
export function formatExploreValue(unit: string, value: number): string {
  if (unit === "q") return formatMoney(value);
  if (unit === "qty") return formatQty(String(value));
  if (unit === "percent") return `${value}%`;
  if (unit === "minutes") return formatMinutes(String(value));
  if (unit === "hours") return formatHours(value);
  return formatInt(value);
}

/** Horas com uma casa: "7 h", "1,5 h". Zero é resposta, não vazio. */
export function formatHours(value: number): string {
  const rounded = Math.round(value * 10) / 10;
  const text = Number.isInteger(rounded)
    ? String(rounded)
    : rounded.toFixed(1).replace(".", ",");
  return `${text} h`;
}

/** Rótulos pt-BR das dimensões do explorador (espelham a gramática). */
export const EXPLORE_DIMENSION_LABELS: Record<string, string> = {
  time: "Tempo (dia)",
  channel: "Canal",
  hour: "Hora do dia",
  weekday: "Dia da semana",
  month_of_year: "Mês do ano",
  week_of_year: "Semana do ano",
  source: "Fonte (Shopman/Yooga)",
  sku: "Produto",
  recipe: "Receita",
  oven: "Forno",
  operator: "Operador",
  grade: "Grau de qualidade",
  defect: "Defeito",
};

/** Cenários de exemplo — chips de partida quando não há salvos (F9).
 *
 * Curadoria pelas perguntas que se toma decisão em cima, na ordem em que a
 * semana acontece: primeiro quanto assar, depois o que o cliente procura,
 * depois como a casa foi. Cruzamento por forno fica de fora — a casa tem um
 * forno só, e um recorte que nunca recorta é ruído.
 */
export const EXPLORE_EXAMPLES = [
  // Está faltando ou sobrando pão?
  { name: "Produtos que mais acabam", config: { metric: "soldout_days", by: "sku", by2: "" } },
  { name: "Horas sem produto por SKU", config: { metric: "hours_without_stock", by: "sku", by2: "" } },
  { name: "Sobra por produto", config: { metric: "leftover", by: "sku", by2: "" } },
  { name: "Falta por dia da semana", config: { metric: "hours_without_stock", by: "weekday", by2: "sku" } },
  // Quando o cliente vem e o que ele leva
  { name: "Faturamento por hora", config: { metric: "revenue", by: "hour", by2: "" } },
  { name: "Movimento por hora × dia da semana", config: { metric: "orders", by: "hour", by2: "weekday" } },
  { name: "O que vende em cada hora", config: { metric: "qty_sold", by: "hour", by2: "sku" } },
  { name: "Sazonalidade por mês do ano", config: { metric: "revenue", by: "month_of_year", by2: "" } },
  { name: "Ticket médio por canal", config: { metric: "average_ticket", by: "channel", by2: "" } },
  { name: "Antes e depois do Shopman", config: { metric: "revenue", by: "time", by2: "source" } },
  // Produção e caixa
  { name: "Perda por defeito × receita", config: { metric: "loss", by: "defect", by2: "recipe" } },
  { name: "Perda por dia da semana", config: { metric: "loss", by: "weekday", by2: "recipe" } },
  { name: "Tempo de forno por receita", config: { metric: "oven_minutes", by: "recipe", by2: "" } },
  { name: "Rendimento por receita", config: { metric: "yield_percent", by: "recipe", by2: "" } },
  { name: "Quebra de caixa por operador", config: { metric: "cash_difference", by: "operator", by2: "" } },
] as const;

export interface WindowPreset {
  key: string;
  label: string;
  days?: number; // só nas janelas móveis; calendário resolve por regra
}

/** Período CORRENTE do calendário — a semana começa na segunda. */
export const WINDOW_PRESETS_CALENDAR: readonly WindowPreset[] = [
  { key: "day", label: "Dia" },
  { key: "week", label: "Semana" },
  { key: "month", label: "Mês" },
  { key: "year", label: "Ano" },
];

/** Janelas móveis terminando hoje. */
export const WINDOW_PRESETS_ROLLING: readonly WindowPreset[] = [
  { key: "7d", label: "7D", days: 7 },
  // 28 e não 30: quatro semanas exatas têm o mesmo mix de dias-da-semana,
  // então médias e comparações não mentem (sábado ≠ terça numa padaria).
  { key: "28d", label: "28D", days: 28 },
  { key: "3m", label: "3M", days: 90 },
  { key: "6m", label: "6M", days: 180 },
  { key: "1y", label: "1A", days: 365 },
  { key: "5y", label: "5A", days: 1826 },
  { key: "max", label: "Máx" },
];

export const WINDOW_PRESETS: readonly WindowPreset[] = [
  ...WINDOW_PRESETS_CALENDAR,
  ...WINDOW_PRESETS_ROLLING,
];

export interface WindowSelection {
  preset: string; // key de WINDOW_PRESETS ou "custom"
  from: string; // ISO, só para custom
  to: string; // ISO, só para custom
}

/** Rótulo do botão de período: preset + a janela efetiva, sempre à vista. */
export function windowButtonLabel(
  selection: WindowSelection,
  range: { date_from: string; date_to: string },
): string {
  const preset = WINDOW_PRESETS.find((p) => p.key === selection.preset);
  const name = selection.preset === "custom" ? "Personalizado" : (preset?.label ?? "Período");
  if (range.date_from === range.date_to) return `${name} · ${shortDate(range.date_from)}`;
  return `${name} · ${shortDate(range.date_from)} – ${shortDate(range.date_to)}`;
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
  if (selection.preset === "day") {
    return { date_from: to, date_to: to };
  }
  if (selection.preset === "week") {
    const monday = new Date(today.getTime());
    monday.setDate(monday.getDate() - ((monday.getDay() + 6) % 7));
    return { date_from: iso(monday), date_to: to };
  }
  if (selection.preset === "month") {
    return { date_from: `${to.slice(0, 7)}-01`, date_to: to };
  }
  if (selection.preset === "year") {
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
