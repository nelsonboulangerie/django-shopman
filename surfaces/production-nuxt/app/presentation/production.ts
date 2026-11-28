// Presentation — production grid shaping. Pure transforms over the production
// projections (served by shopman/backstage/projections/production.py). The
// projections are already screen-ready (status_label, timer status, step state,
// can_* flags pre-resolved); this layer only derives the view shape and the
// functional-color tone. No lifecycle arithmetic (the backend owns the
// WorkOrder lifecycle).
import type {
  ForecastStatus,
  ProductionMatrixRowProjection,
  ProductionPromisedProjection,
  PromisedOrderProjection,
  ProductionShortageError,
  ProductionTimerStatusCode,
  WorkOrderCardProjection,
} from "~/types/production";
import {
  timeTone,
  type TimeTone,
} from "../../../operator-kit/app/presentation/timeTone";
import { formatClock } from "../../../operator-kit/app/presentation/clock";
import {
  daysBetween,
  shortDayMonth,
  weekdayShort,
} from "../../../operator-kit/app/presentation/dates";

// O prometido por produto e data, lido da régua das reservas (WP-F08): o
// planejado, o encomendado, o livre e os pedidos com nome, hora e retirada ou
// entrega. É a única fonte do que a Produção diz sobre encomenda (WP-F10).
export type {
  ProductionPromisedProjection,
  PromisedOrderProjection,
} from "~/types/production";

// ── Timer tone (urgency of the started clock) ──────────────────────────────

export type TimerTone = TimeTone;

export function timerTone(status: ProductionTimerStatusCode): TimerTone {
  if (status === "late") return timeTone("late");
  if (status === "warning") return timeTone("warning");
  return timeTone("on_time");
}

/** O painel mantém Planejado, Previsto e Fechado neutros; só Atrasado é tempo vermelho. */
export function forecastTimeTone(status: ForecastStatus): TimerTone {
  return timeTone(status === "delayed" ? "late" : "on_time");
}

/** Tonal chip classes for the live timer. Calm by default; only warning/late
 *  carry saturated meaning. */
export function timerChip(tone: TimerTone): string {
  switch (tone) {
    case "late":
      return "border-red-500/40 bg-red-500/10 text-red-700 dark:text-red-300";
    case "warning":
      return "border-amber-500/40 bg-amber-500/10 text-amber-700 dark:text-amber-300";
    case "ready":
      return "border-success/40 bg-success/10 text-success";
    default:
      return "border-border bg-muted text-muted-foreground";
  }
}

/** Progress-bar fill class for a timer tone (the step progress within a card). */
// ── Elapsed helper ──────────────────────────────────────────────────────────

/** Elapsed seconds → compact label. Seconds in the first minute, then whole
 *  minutes, then "1h 5m". */
export function elapsedLabel(seconds: number): string {
  const s = Math.max(0, Math.round(seconds));
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m`;
  const h = Math.floor(m / 60);
  return m % 60 ? `${h}h ${m % 60}m` : `${h}h`;
}

// ── Datas (chips Hoje · Amanhã · dia-da-semana + data cheia fixa) ──────────

const WEEKDAYS_PT = [
  "Domingo",
  "Segunda",
  "Terça",
  "Quarta",
  "Quinta",
  "Sexta",
  "Sábado",
];
const MONTHS_PT = [
  "jan",
  "fev",
  "mar",
  "abr",
  "mai",
  "jun",
  "jul",
  "ago",
  "set",
  "out",
  "nov",
  "dez",
];

// A superfície é renderizada duas vezes: primeiro no contêiner Nitro (UTC) e
// depois no navegador da loja (BRT). "Horário local" do processo produziria
// duas datas diferentes entre 21h e meia-noite; a data operacional precisa ser
// a da padaria em ambos os lados.
export const STORE_TIME_ZONE = "America/Sao_Paulo";

const STORE_DATE_TIME = new Intl.DateTimeFormat("en-US", {
  timeZone: STORE_TIME_ZONE,
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",  // hora-ok: cálculo no fuso da loja, não exibição
  hourCycle: "h23",
});

function storeDateTimeParts(now: Date): {
  year: number;
  month: number;
  day: number;
  hour: number;
} {
  const parts = Object.fromEntries(
    STORE_DATE_TIME.formatToParts(now).map((part) => [part.type, part.value]),
  );
  return {
    year: Number(parts.year),
    month: Number(parts.month),
    day: Number(parts.day),
    hour: Number(parts.hour),
  };
}

function parseISODate(iso: string): Date | null {
  const [y, m, d] = iso.split("-").map(Number);
  if (!y || !m || !d) return null;
  return new Date(y, m - 1, d);
}

/** "2026-07-04" → "Sábado" — rótulo do chip quando a data foi escolhida à mão. */
export function weekdayLabel(iso: string): string {
  const date = parseISODate(iso);
  return date ? WEEKDAYS_PT[date.getDay()]! : "";
}

/** "2026-07-04" → "04 jul 2026" — a data cheia, sempre no mesmo lugar. */
export function fullDateLabel(iso: string): string {
  const date = parseISODate(iso);
  if (!date) return "";
  return `${String(date.getDate()).padStart(2, "0")} ${MONTHS_PT[date.getMonth()]} ${date.getFullYear()}`;
}

/** ISO operacional (YYYY-MM-DD) da padaria para hoje + offsetDays. */
export function isoForOffset(
  offsetDays: number,
  now: Date = new Date(),
): string {
  const local = storeDateTimeParts(now);
  const d = new Date(Date.UTC(local.year, local.month - 1, local.day + offsetDays));
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())}`;
}

/** Hora corrente no fuso operacional, idêntica no SSR e no navegador. */
export function storeHour(now: Date = new Date()): number {
  return storeDateTimeParts(now).hour;
}

/**
 * Resolve a virada de dia do kiosk. À meia-noite `todayISO` avança; se a seleção
 * acompanhava "hoje", ela rola junto (a TV não amanhece nas fornadas de ontem).
 * Pura e testável — o componente só a chama num tick de minuto.
 */
export function resolveDayRollover(
  prevTodayISO: string,
  selectedISO: string,
  now: Date = new Date(),
): {
  todayISO: string;
  tomorrowISO: string;
  selectedDate: string;
  rolled: boolean;
} {
  const todayISO = isoForOffset(0, now);
  const tomorrowISO = isoForOffset(1, now);
  const rolled = todayISO !== prevTodayISO;
  const selectedDate =
    rolled && selectedISO === prevTodayISO ? todayISO : selectedISO;
  return { todayISO, tomorrowISO, selectedDate, rolled };
}

/** Segundos restantes → "12:34" (contagem regressiva do timer do forno). */
export function countdownLabel(secondsLeft: number): string {
  const s = Math.max(0, Math.round(secondsLeft));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

// ── Production grid shaping ────────────────────────────────────────────────

/** Whether a matrix row has anything actionable/visible (avoids empty noise). */
export function rowHasActivity(row: ProductionMatrixRowProjection): boolean {
  return (
    row.planned_orders.length > 0 ||
    row.started_orders.length > 0 ||
    row.finished_orders.length > 0 ||
    row.suggestion != null
  );
}

/** O texto que a bancada lê primeiro: o nome da ficha.
 *  Cai no SKU quando a ficha não tem nome — a linha continua legível, e o
 *  padeiro vê o código em vez de uma linha em branco. */
export function rowLabel(row: {
  recipe_name?: string;
  output_sku: string;
}): string {
  return row.recipe_name?.trim() || row.output_sku;
}

/** Filter matrix rows by a free-text query over SKU + recipe name + WO refs.
 *  Refs matter for alert deep-links ("WO-2026-00042" lands on its row). */
export function matchesRowQuery(
  row: ProductionMatrixRowProjection,
  rawQuery: string,
): boolean {
  const q = rawQuery.trim().toLowerCase();
  if (!q) return true;
  const refs = [
    ...row.planned_orders,
    ...row.started_orders,
    ...row.finished_orders,
  ].map((wo) => wo.ref);
  return [row.output_sku, row.recipe_name, ...refs]
    .join(" ")
    .toLowerCase()
    .includes(q);
}

/** Whether a planning row can be started (has a planned order and no started yet). */
export function startableWorkOrder(
  row: ProductionMatrixRowProjection,
): WorkOrderCardProjection | null {
  return plannedWorkOrder(row);
}

/**
 * A fornada planejada que esta linha AJUSTARIA, a mesma confirmada na Produção.
 *
 * Mesmo objeto, nome diferente: quem planeja não está pensando em iniciar, e é dela
 * que sai o `rev` que o ajuste devolve ao servidor. Duas leituras do mesmo fato pedem
 * dois nomes; uma implementação só evita que elas divirjam.
 */
export function plannedWorkOrder(
  row: ProductionMatrixRowProjection,
): WorkOrderCardProjection | null {
  return row.planned_orders.length === 1 ? row.planned_orders[0]! : null;
}

// ── Números da bancada (V6-PROD R07) ─────────────────────────────────────────
// A quantidade chega do servidor como texto com ponto decimal ("1230.77"). A tela
// fala português e diz a unidade: base em gramas acima de um quilo vira quilo
// ("18,72 kg"), que é como o padeiro conta; peça fica só o número.
const QTY_FORMAT = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 2 });
const COUNT_UNITS = new Set(["", "un", "un.", "und", "pc", "pç", "unidade"]);

/** "1.230,77 g", "18,72 kg", "52" (peças sem unidade), "1,5 l". */
export function formatQty(value: string | number, unit = ""): string {
  const amount =
    typeof value === "number"
      ? value
      : Number.parseFloat(String(value ?? "0").replace(",", ".")) || 0;
  const normalized = (unit ?? "").trim().toLowerCase();
  if (COUNT_UNITS.has(normalized)) return QTY_FORMAT.format(amount);
  if (normalized === "g" && Math.abs(amount) >= 1000)
    return `${QTY_FORMAT.format(amount / 1000)} kg`;
  if (normalized === "ml" && Math.abs(amount) >= 1000)
    return `${QTY_FORMAT.format(amount / 1000)} l`;
  return `${QTY_FORMAT.format(amount)} ${normalized}`;
}

/** A quantidade com a unidade sempre escrita: "26 un.", "1,2 kg". */
export function formatQtyUnit(value: string | number, unit = ""): string {
  const normalized = (unit ?? "").trim().toLowerCase();
  return COUNT_UNITS.has(normalized)
    ? `${formatQty(value)} un.`
    : formatQty(value, normalized);
}

/** A linha do dia no cabeçalho do Planejamento (R04): ocasião e clima.
 *  "Sábado comum, sem feriado · previsão 24 °C e sol (como os sábados usados na
 *  conta)". Vazio quando o servidor não sabe nada do dia. */
export function dayContextLine(
  context:
    | { occasion: string; weather: string; weather_kind: string }
    | null
    | undefined,
  sampleNote = "",
): string {
  if (!context) return "";
  const parts: string[] = [];
  if (context.occasion) parts.push(context.occasion);
  if (context.weather) {
    parts.push(
      context.weather_kind === "forecast"
        ? `previsão ${context.weather}`
        : context.weather,
    );
  }
  const line = parts.join(" · ");
  return line && sampleNote ? `${line} (${sampleNote})` : line;
}

// ── Etiqueta do lote (R19) ───────────────────────────────────────────────────
// A etiqueta de preparo leva um QR com `shopman-lote:<SKU>` (impressa pelo relay
// em ESC/POS e pelo navegador). A Finalização lê e abre o lote daquele produto.
// Aceita também o código do lote ("WO-2026-00020") e o SKU puro, digitados ou
// lidos de outra etiqueta.
export const LOT_LABEL_PREFIX = "shopman-lote:";

export function lotLabelPayload(outputSku: string): string {
  return `${LOT_LABEL_PREFIX}${outputSku}`;
}

/** O lote aberto que o código lido identifica, ou `null`. */
export function matchLotCode<T extends { ref: string; output_sku: string }>(
  rawCode: string,
  orders: readonly T[],
): T | null {
  const code = rawCode.trim();
  if (!code) return null;
  const lower = code.toLowerCase();
  const sku = lower.startsWith(LOT_LABEL_PREFIX)
    ? code.slice(LOT_LABEL_PREFIX.length).split(":")[0]!.trim().toLowerCase()
    : "";
  if (sku) return orders.find((order) => order.output_sku.toLowerCase() === sku) ?? null;
  return (
    orders.find((order) => order.ref.toLowerCase() === lower) ??
    orders.find((order) => order.output_sku.toLowerCase() === lower) ??
    null
  );
}

// ── O prometido (WP-F10): a régua das reservas na tela ─────────────────────
// Tudo o que a Produção diz sobre encomenda sai de `promised` (WP-F08): o produto
// na data, das reservas dos pedidos abertos daquele dia. Uma grandeza por rótulo
// (omotenashi-copy D4): o chip conta unidades e diz QUANDO; a hora só aparece
// quando vale para todas elas. A Produção vê primeiro nome e hora, nunca dinheiro.

function parseQty(value: string | null | undefined): number {
  return Number.parseFloat(String(value ?? "0").replace(",", ".")) || 0;
}

/** Os pedidos da data que contam no prometido do produto, pela hora. */
export function rowPromisedOrders(
  row: Pick<ProductionMatrixRowProjection, "promised">,
): PromisedOrderProjection[] {
  return row.promised?.orders ?? [];
}

/** Unidades encomendadas do produto na data (0 sem encomenda). */
export function orderedUnits(
  promised: ProductionPromisedProjection | null | undefined,
): number {
  return parseQty(promised?.ordered_qty);
}

export function rowOrderedUnits(
  row: Pick<ProductionMatrixRowProjection, "promised">,
): number {
  return orderedUnits(row.promised);
}

/** "1 un. encomendada", "6 un. encomendadas", "1,2 kg encomendados". */
export function orderedLabel(units: number | string, unit = ""): string {
  const amount = typeof units === "number" ? units : parseQty(units);
  const quantity = formatQtyUnit(amount, unit);
  // "un." é feminino (unidades); peso e volume são masculinos (quilos, litros).
  if (!quantity.endsWith(" un.")) return `${quantity} encomendados`;
  return `${quantity} ${amount === 1 ? "encomendada" : "encomendadas"}`;
}

/** O dia da encomenda, curto: "hoje", "amanhã", "sáb 29/11". */
export function promisedDay(iso: string, today: string): string {
  const offset = daysBetween(today, iso);
  if (offset === 0) return "hoje";
  if (offset === 1) return "amanhã";
  return `${weekdayShort(iso)} ${shortDayMonth(iso)}`.trim();
}

/** Quando as encomendas da data são para: "amanhã 9h" (todas na mesma hora),
 *  "amanhã, das 8h30 às 11h" (horas diferentes) ou só "amanhã" (algum pedido
 *  sem hora marcada: a faixa mentiria sobre ele). */
export function promisedWhen(
  promised: ProductionPromisedProjection,
  today: string,
): string {
  const day = promisedDay(promised.date, today);
  const orders = promised.orders ?? [];
  if (!orders.length || orders.some((order) => !order.due_time)) return day;
  const times = [...new Set(orders.map((order) => order.due_time))].sort();
  const first = formatClock(times[0]!);
  if (times.length === 1) return `${day} ${first}`;
  return `${day}, das ${first} às ${formatClock(times.at(-1)!)}`;
}

/** O chip da linha: "1 un. · amanhã 9h". Vazio sem encomenda na data. */
export function promisedChipLabel(
  row: Pick<ProductionMatrixRowProjection, "promised" | "output_unit">,
  today: string,
): string {
  const promised = row.promised;
  const units = orderedUnits(promised);
  if (!promised || units <= 0) return "";
  return `${formatQtyUnit(units, row.output_unit)} · ${promisedWhen(promised, today)}`;
}

const FULFILLMENT_LABEL: Record<string, string> = {
  pickup: "retirada",
  delivery: "entrega",
};

/** Uma encomenda em uma linha: "Clara · retirada · 9h · 1 un.". Sem nome, o
 *  código do pedido; sem hora ou sem modo, a parte some (nunca um traço). */
export function promisedOrderLine(
  order: PromisedOrderProjection,
  unit = "",
): string {
  return [
    order.customer_first_name || order.ref,
    FULFILLMENT_LABEL[order.fulfillment_type] ?? "",
    order.due_time ? formatClock(order.due_time) : "",
    formatQtyUnit(order.qty, unit),
  ]
    .filter(Boolean)
    .join(" · ");
}

/** O que o plano da data não cobre, em uma frase; vazio quando cobre. */
export function promisedGap(
  promised: ProductionPromisedProjection | null | undefined,
  unit = "",
): string {
  const over = parseQty(promised?.over_plan_qty);
  if (!promised || over <= 0) return "";
  if (parseQty(promised.planned_qty) <= 0)
    return "Nenhum lote planejado para esta data.";
  return `O plano da data fica ${formatQtyUnit(over, unit)} abaixo das encomendas.`;
}

/**
 * WP-F13 (P1-04): o pedido à Produção. Encomenda da data que o plano não cobre,
 * pela régua das reservas (`promised.over_plan_qty`, WP-F08): sem lote nenhum
 * ("Encomendado sem lote: Croissant 12", "Planejar 12") ou acima do plano
 * ("Encomendado acima do plano: Croissant 3", "Planejar mais 3"). A Produção só
 * planeja (D-042, item 2): não há aceitar nem recusar aqui; se a casa não vai
 * produzir, a encomenda segue em "Promessa em risco" no Gestor.
 */
export interface UnbackedOrder {
  row: ProductionMatrixRowProjection;
  kind: "no-lot" | "over-plan";
  /** O que falta planejar para cobrir as encomendas da data. */
  missing: number;
  /** O planejado da data depois do gesto: o que vai ao servidor. */
  targetQty: string;
  /**
   * A sugestão da linha do dia, quando ela já conta as encomendas ("196"); "" quando
   * não há linha com número próprio. Coberta numa linha, a encomenda NÃO vai para a
   * faixa (decisão da coordenação, 28/11): a linha já diz tudo (o chip e o número), e um
   * segundo "Planejar" com outro número era armadilha (tocar "Planejar 12" fechava o dia
   * com 12 em vez de 196). Só o vazio da Produção, que não tem linha, ainda a lista.
   */
  coveredBy: string;
  headline: string;
  subject: string;
  actionLabel: string;
}

/** A linha do dia tem número próprio que já cobre as encomendas (e nenhum lote ainda). */
function lineCovers(row: ProductionMatrixRowProjection, ordered: number): string {
  if (!row.suggestion || row.planned_orders.length) return "";
  const suggested = parseQty(row.suggestion.quantity);
  return suggested > 0 && suggested >= ordered ? row.suggestion.quantity : "";
}

function qtyString(value: number): string {
  return Number.isInteger(value) ? String(value) : value.toFixed(3).replace(/\.?0+$/, "");
}

export function unbackedOrders(rows: ProductionMatrixRowProjection[]): UnbackedOrder[] {
  return rows
    .flatMap((row): UnbackedOrder[] => {
      const missing = parseQty(row.promised?.over_plan_qty);
      if (!row.promised || missing <= 0 || !rowPromisedOrders(row).length) return [];
      const planned = parseQty(row.promised.planned_qty);
      const kind = planned > 0 ? "over-plan" : "no-lot";
      const amount = formatQty(missing, row.output_unit);
      return [
        {
          row,
          kind,
          missing,
          targetQty: qtyString(planned + missing),
          coveredBy: kind === "no-lot" ? lineCovers(row, missing) : "",
          headline: kind === "no-lot" ? "Encomendado sem lote" : "Encomendado acima do plano",
          subject: `${rowLabel(row)} ${amount}`,
          actionLabel: kind === "no-lot" ? `Planejar ${amount}` : `Planejar mais ${amount}`,
        },
      ];
    })
    .sort((a, b) => rowLabel(a.row).localeCompare(rowLabel(b.row), "pt-BR"));
}

/** O que vai para a faixa do Planejamento: só o que nenhuma linha do dia cobre. */
export function bandOrders(items: UnbackedOrder[]): UnbackedOrder[] {
  return items.filter((item) => !item.coveredBy);
}

/** A hora do plano mais recente entre os planejados ("15h12"), ou "". */
export function latestPlanTime(rows: ProductionMatrixRowProjection[]): string {
  const times = rows
    .flatMap((row) => [
      ...row.planned_orders,
      ...row.started_orders,
      ...row.finished_orders,
    ])
    .map((order) => order.created_at_time ?? "")
    .filter(Boolean)
    .sort();
  return formatClock(times.at(-1) ?? "");
}

/** Planejou exatamente o que a sugestão dizia. */
export function plannedAsSuggested(row: ProductionMatrixRowProjection): boolean {
  if (!row.suggestion) return false;
  const planned =
    row.planned_qty !== "0"
      ? row.planned_qty
      : row.started_qty !== "0"
        ? row.started_qty
        : row.finished_qty;
  return (
    (Number.parseFloat(planned) || 0) ===
    (Number.parseFloat(row.suggestion.quantity) || 0)
  );
}

// ── Honest board feedback (stale data beats an empty board) ────────────────

/** Como um board TOLERANTE a dado velho deve se apresentar. Só troca o board por uma
 *  tela de carregando/erro/vazio quando NÃO há dado nenhum; havendo dado, mostra-o
 *  SEMPRE (mesmo que a última atualização tenha falhado — o chip de degradação avisa). */
export type BoardDisplay = "loading" | "error" | "empty" | "ready";

export function boardDisplay(opts: {
  pending: boolean;
  error: boolean;
  hasData: boolean;
}): BoardDisplay {
  if (opts.hasData) return "ready";
  if (opts.pending) return "loading";
  if (opts.error) return "error";
  return "empty";
}

/** Há dado na tela porém a última atualização falhou → o quadro está velho. É o gatilho
 *  do indicador honesto de degradação (dado velho visível > quadro vazio; nunca no vácuo
 *  — [[feedback_transparent_timeouts]]). */
export function isStale(opts: { error: boolean; hasData: boolean }): boolean {
  return opts.error && opts.hasData;
}

// ── Shortage envelope parsing ──────────────────────────────────────────────

/** Pull the structured shortage error out of a proxied 409 response body, if any.
 *  The floor app renders the material/order shortage modal from this. */
export function parseShortage(
  errorBody: unknown,
): ProductionShortageError | null {
  const error = (errorBody as { error?: unknown })?.error;
  if (!error || typeof error !== "object") return null;
  const code = (error as { code?: string }).code;
  if (code === "material_shortage" || code === "order_shortage") {
    return error as ProductionShortageError;
  }
  return null;
}

// ── Sanidade da quantidade (abrir ou planejar lote) ──────────────────────────

/** Acima de quantas vezes o número de referência a tela pede para conferir. */
export const OUTSIZED_FACTOR = 3;

/**
 * Um zero a mais vira um lote que ninguém consegue assar (beta 05/11: 42 virou
 * 4.200). Diferença de rendimento continua sendo só um aviso; passar de três
 * vezes a referência pede um segundo toque, com o número escrito na frase.
 * Devolve a frase da conferência, ou null quando o número é plausível.
 */
export function outsizedQuantityWarning(
  quantity: string | number,
  reference: string | number | null | undefined,
  referenceLabel = "o planejado",
): string | null {
  const parse = (value: string | number | null | undefined) =>
    typeof value === "number"
      ? value
      : Number.parseFloat(String(value ?? "").replace(",", ".")) || 0;
  const amount = parse(quantity);
  const base = parse(reference);
  if (amount <= 0 || base <= 0) return null;
  if (amount <= base * OUTSIZED_FACTOR) return null;
  const times = Math.round(amount / base);
  return `${QTY_FORMAT.format(amount)} é ${QTY_FORMAT.format(times)} vezes ${referenceLabel} (${QTY_FORMAT.format(base)}). Confira o número antes de seguir.`;
}

// ── Letreiro (painel Solari) ─────────────────────────────────────────────────

const MASS_TO_KG: Record<string, number> = { g: 1 / 1000, kg: 1 };

/**
 * A quantidade como a palheta escreve, com a unidade que a projeção traz:
 * peça é "12 UN"; massa é sempre em quilo ("18,5 KG", "0,8 KG"), porque é
 * assim que o padeiro lê a masseira; volume segue a régua da casa ("1,5 L").
 */
export function boardQtyLabel(qty: string, unit = ""): string {
  const normalized = (unit ?? "").trim().toLowerCase();
  const amount = Number.parseFloat(String(qty ?? "0").replace(",", ".")) || 0;
  const toKg = MASS_TO_KG[normalized];
  if (toKg !== undefined) return `${QTY_FORMAT.format(amount * toKg)} KG`;
  if (COUNT_UNITS.has(normalized)) return `${QTY_FORMAT.format(amount)} UN`;
  return formatQty(amount, normalized).toUpperCase();
}

/**
 * Largura da coluna de quantidade, em palhetas: a maior quantidade do dia
 * cabe inteira (beta 05/11: "4200 U" perdia o N). Nunca menos que "999 UN".
 */
export function boardQtyChars(
  rows: readonly { qty: string; unit?: string }[],
): number {
  return Math.max(6, ...rows.map((row) => boardQtyLabel(row.qty, row.unit).length));
}

/** Largura máxima da coluna do nome, em palhetas por linha. Nome maior quebra em
 *  duas linhas de palhetas em vez de encolher a letra de todo o Letreiro. */
export const BOARD_NAME_MAX_CHARS = 22;
const BOARD_NAME_MIN_CHARS = 12;
const BOARD_NAME_MAX_LINES = 2;

/**
 * Largura da coluna do nome, em palhetas: o maior nome do dia, inteiro, até o
 * teto (P2-15: a coluna fixa em 22 cortava o nome). Dia de nomes curtos ganha
 * letra maior, porque a escala divide a largura pelo total de palhetas.
 */
export function boardNameChars(rows: readonly { recipe_name: string }[]): number {
  const longest = Math.max(0, ...rows.map((row) => row.recipe_name.trim().length));
  return Math.min(BOARD_NAME_MAX_CHARS, Math.max(BOARD_NAME_MIN_CHARS, longest));
}

/**
 * O nome em linhas de palhetas: quebra entre palavras, até duas linhas. Só o que
 * passa de duas linhas cheias termina em "…" ("Mini Focaccia Cebola," / "Bacon e
 * Tomilho" cabe inteiro em 22).
 */
export function boardNameLines(name: string, width: number): string[] {
  const size = Math.max(1, width);
  const words = name.trim().split(/\s+/).filter(Boolean);
  const lines: string[] = [];
  let current = "";
  for (let word of words) {
    while (word.length > size) {
      if (current) {
        lines.push(current);
        current = "";
      }
      lines.push(word.slice(0, size));
      word = word.slice(size);
    }
    const next = current ? `${current} ${word}` : word;
    if (next.length <= size) current = next;
    else {
      lines.push(current);
      current = word;
    }
  }
  if (current) lines.push(current);
  if (lines.length <= BOARD_NAME_MAX_LINES) return lines.length ? lines : [""];
  const kept = lines.slice(0, BOARD_NAME_MAX_LINES);
  const last = kept[BOARD_NAME_MAX_LINES - 1]!;
  kept[BOARD_NAME_MAX_LINES - 1] = `${last.slice(0, size - 1).trimEnd()}…`;
  return kept;
}

/** "Planejado", o maior rótulo de situação do painel. */
export const BOARD_STATUS_CHARS = 9;
/** "10h30", o maior horário da casa. */
export const BOARD_ETA_CHARS = 5;

/** O que a linha diz a quem não enxerga a palheta: "Croissant: 18,5 kg às 8h, Planejado". */
export function boardRowSpoken(row: {
  recipe_name: string;
  qty: string;
  unit?: string;
  eta_display: string;
  status_label: string;
}): string {
  const qty = boardQtyLabel(row.qty, row.unit)
    .replace(/ UN$/, " unidades")
    .replace(/ KG$/, " kg")
    .replace(/ L$/, " l");
  const eta = row.eta_display && row.eta_display !== "—" ? ` às ${row.eta_display}` : "";
  return `${row.recipe_name}: ${qty}${eta}, ${row.status_label}`;
}

/**
 * O aviso de conexão perdida, a maior coisa da tela: o quadro que fica é o da
 * última leitura, e a pessoa precisa saber de quando ele é.
 */
export function boardStaleNotice(readAt: string): string {
  return readAt ? `Sem conexão. Lido às ${readAt}` : "Sem conexão. Mostrando a última leitura";
}

/** O aviso nas palhetas do Letreiro: maiúsculas de painel, mas a hora da casa
 *  guarda o "h" minúsculo ("SEM CONEXÃO. LIDO ÀS 6h42"). */
export function boardStaleFlaps(readAt: string): string {
  return boardStaleNotice(readAt)
    .toUpperCase()
    .replace(/(\d)H(\d{2})?\b/g, (_, hour: string, minute = "") => `${hour}h${minute}`);
}
