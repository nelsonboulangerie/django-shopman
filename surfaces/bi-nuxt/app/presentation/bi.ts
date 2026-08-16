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
  // Contexto: só chegam na gramática quando alguém injetou o dado
  // (import_holidays / import_weather). Sem dado, o servidor nem oferece.
  outage_reason: "Motivo (esgotado/pausado)",
  day_kind: "Tipo de dia (feriado, data comercial)",
  temperature: "Temperatura do dia",
  rain: "Chuva",
};

/** Cenários que dependem de contexto injetado — só valem se o servidor oferecer. */
export const CONTEXT_EXAMPLES = [
  { name: "Faturamento por temperatura", config: { metric: "revenue", by: "temperature", by2: "" } },
  { name: "O que vende no calor", config: { metric: "qty_sold", by: "temperature", by2: "sku" } },
  { name: "Feriado, data comercial e véspera", config: { metric: "revenue", by: "day_kind", by2: "" } },
  { name: "O que vende no dia das mães", config: { metric: "qty_sold", by: "day_kind", by2: "sku" } },
  { name: "Falta em véspera de data especial", config: { metric: "unavailable_hours", by: "day_kind", by2: "sku" } },
  { name: "Movimento com e sem chuva", config: { metric: "orders", by: "rain", by2: "" } },
] as const;

/**
 * Junta os exemplos fixos com os de contexto que a gramática do servidor
 * declara suportar agora. Um chip que abriria vazio não aparece: a tela cresce
 * quando o dado chega, e não promete o que não tem.
 */
export function availableExamples(
  supportedDimensions: readonly string[],
): ReadonlyArray<{ name: string; config: { metric: string; by: string; by2: string } }> {
  const supported = new Set(supportedDimensions);
  return [
    ...EXPLORE_EXAMPLES,
    ...CONTEXT_EXAMPLES.filter(
      (example) =>
        supported.has(example.config.by) &&
        (!example.config.by2 || supported.has(example.config.by2)),
    ),
  ];
}

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
  { name: "Horas sem poder vender", config: { metric: "unavailable_hours", by: "sku", by2: "" } },
  { name: "Sem vender por canal", config: { metric: "unavailable_hours", by: "channel", by2: "sku" } },
  { name: "Esgotado ou pausado?", config: { metric: "unavailable_hours", by: "outage_reason", by2: "sku" } },
  { name: "Tempo pausado por produto", config: { metric: "paused_hours", by: "sku", by2: "" } },
  { name: "Horas sem produto na prateleira", config: { metric: "hours_without_stock", by: "sku", by2: "" } },
  { name: "Sobra por produto", config: { metric: "leftover", by: "sku", by2: "" } },
  { name: "Falta por dia da semana", config: { metric: "unavailable_hours", by: "weekday", by2: "sku" } },
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

// ── "O que esperar": a prestação de contas vira frase ────────────────────────
//
// O número da projeção só pode aparecer acompanhado de como se chegou nele.
// Estas funções traduzem o `basis` cru — que é vocabulário de código — na frase
// que o gestor lê para decidir se confia.

const CRITERION_LABELS: Record<string, string> = {
  weekday: "dia da semana",
  day_kind: "tipo de dia",
  season: "estação",
  temperature: "temperatura",
};

const MISSING_LABELS: Record<string, string> = {
  amostra_insuficiente: "Não temos dias parecidos o bastante para dizer.",
  sem_movimento_recente: "Falta movimento recente para servir de referência.",
  patamar_nao_representativo:
    "Os últimos dias registram uma fração do que a casa costuma vender. Enquanto a operação não estiver toda no sistema, o patamar de hoje não serve de base.",
};

export interface ForecastBasisLike {
  sample_size: number;
  applied: string[];
  relaxed: string[];
  unavailable: string[];
  window_from: string;
  window_to: string;
  excluded_closed: number;
  excluded_disrupted: number;
  without_sales: number;
  level_days: number;
}

function list(keys: string[]): string {
  const names = keys.map((key) => CRITERION_LABELS[key] ?? key);
  if (names.length <= 1) return names.join("");
  return `${names.slice(0, -1).join(", ")} e ${names[names.length - 1]}`;
}

const plural = (count: number) => (count === 1 ? "" : "s");
const days = (count: number) => `${formatInt(count)} dia${plural(count)}`;
const stayedOut = (count: number) => (count === 1 ? "ficou de fora" : "ficaram de fora");

/**
 * "14 quartas-feiras parecidas, casadas por dia da semana e tipo de dia."
 *
 * O gênero acompanha o dia: em pt-BR os dias em "-feira" são femininos e
 * sábado e domingo são masculinos, e o plural de "quarta-feira" flexiona as
 * duas partes. Uma concordância errada num número que o gestor vai usar para
 * decidir tira a autoridade do número.
 */
export function basisHeadline(basis: ForecastBasisLike, weekdayLabel: string): string {
  const many = basis.sample_size !== 1;
  const feminine = weekdayLabel.endsWith("-feira");
  const gender = feminine ? "a" : "o";
  const s = many ? "s" : "";
  const day = !many
    ? weekdayLabel
    : feminine
      ? weekdayLabel.replace("-feira", "s-feiras")
      : `${weekdayLabel}s`;
  const criteria = basis.applied.length
    ? `, casad${gender}${s} por ${list(basis.applied)}`
    : "";
  return `${formatInt(basis.sample_size)} ${day} parecid${gender}${s}${criteria}.`;
}

/**
 * As ressalvas, cada uma dita por inteiro. Afrouxado e indisponível são coisas
 * diferentes: o primeiro é escolha do cálculo diante de amostra curta, o
 * segundo é dado que a casa não tem.
 */
export function basisNotes(basis: ForecastBasisLike): string[] {
  const notes: string[] = [];
  if (basis.relaxed.length) {
    notes.push(`Ignoramos ${list(basis.relaxed)}: com esse recorte sobravam poucos dias.`);
  }
  if (basis.unavailable.length) {
    notes.push(
      `Não sabemos ${list(basis.unavailable)} do dia perguntado, então esse recorte não entrou no casamento.`,
    );
  }
  if (basis.without_sales) {
    notes.push(
      `${days(basis.without_sales)} parecido${plural(basis.without_sales)} sem venda registrada ${stayedOut(basis.without_sales)}: ausência não é zero.`,
    );
  }
  if (basis.excluded_closed) {
    notes.push(
      `${days(basis.excluded_closed)} em que a casa não abriu ${stayedOut(basis.excluded_closed)}.`,
    );
  }
  if (basis.excluded_disrupted) {
    notes.push(
      `${days(basis.excluded_disrupted)} atrapalhado${plural(basis.excluded_disrupted)} por episódio ${stayedOut(basis.excluded_disrupted)}.`,
    );
  }
  notes.push(
    `O patamar aplicado é o movimento típico de agora, medido em ${formatInt(basis.level_days)} dias.`,
  );
  return notes;
}

export function missingLabel(reason: string): string {
  return MISSING_LABELS[reason] ?? "Não temos base para projetar este dia.";
}

/** "R$ 1.240 a R$ 1.680" — a faixa onde caiu metade dos dias parecidos. */
export function rangeLabel(low: number, high: number): string {
  return `${formatMoneyCompact(low)} a ${formatMoneyCompact(high)}`;
}

export const HORIZON_LABELS = [
  { key: "day", label: "O dia" },
  { key: "week", label: "A semana" },
  { key: "month", label: "O mês" },
] as const;

/**
 * ISO "2025-06-12" → "12/06/2025". O ano é obrigatório quando as linhas são
 * ocorrências de anos diferentes: sem ele, dois dias das mães aparecem com o
 * mesmo rótulo e a lista deixa de fazer sentido.
 */
export function shortDateWithYear(iso: string): string {
  const [year, month, day] = iso.split("-");
  return `${day}/${month}/${year}`;
}
