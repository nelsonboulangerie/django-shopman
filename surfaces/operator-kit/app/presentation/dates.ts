// Datas das superfícies de operador: os DOIS controles da casa (decisão do dono,
// 02/10/2026) e a aritmética que eles dividem.
//
//   Tipo 1, "Escolha rápida de dia" (`OperatorDayPicker`): passo de wizard ou
//   campo de formulário. Quatro botões grandes: Hoje, Amanhã, a próxima data que o
//   contexto permite (nominada pelo dia da semana) e Outra data.
//
//   Tipo 2, "Período" (`OperatorPeriodPicker`): o botão que DIZ a janela ativa, os
//   chips no popover dele, e ‹ › que andam um período igual ao escolhido. O popover
//   tem quatro grupos: Período (do calendário), Próximos (janelas que começam hoje),
//   Últimos (janelas que terminam hoje) e Personalizado (De/Até). Cada consumidor
//   declara os que fazem sentido para ele: o B.I. só olha o passado, as Encomendas
//   olham também para a frente. Serve o B.I. (análise) e os quadros (Encomendas,
//   Produção, KDS, Gestor).
//
// Tudo aqui é data LOCAL ("YYYY-MM-DD" no fuso do dispositivo). A versão anterior do
// B.I. resolvia o "hoje" por `toISOString()`, que é UTC: depois das 21h em Londrina o
// período de "hoje" já era o de amanhã.

const WEEKDAY_SHORT = ["dom", "seg", "ter", "qua", "qui", "sex", "sáb"] as const;
const WEEKDAY_LONG = [
  "Domingo",
  "Segunda-feira",
  "Terça-feira",
  "Quarta-feira",
  "Quinta-feira",
  "Sexta-feira",
  "Sábado",
] as const;

const ISO = /^(\d{4})-(\d{2})-(\d{2})$/;

/** "2026-10-02" → Date local (meia-noite), ou null se não for data. */
export function parseIsoDate(iso: string): Date | null {
  const match = ISO.exec(iso ?? "");
  if (!match) return null;
  const date = new Date(Number(match[1]), Number(match[2]) - 1, Number(match[3]));
  return Number.isNaN(date.getTime()) ? null : date;
}

/** Date → "YYYY-MM-DD" no fuso do dispositivo (nunca `toISOString`, que é UTC). */
export function isoDate(date: Date): string {
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${date.getFullYear()}-${month}-${day}`;
}

/**
 * O "hoje" em "YYYY-MM-DD". Sem `timeZone`, o do dispositivo; com ele (ex.:
 * `STORE_TIME_ZONE`), o da loja, qualquer que seja o fuso do tablet: às 23h30 de
 * Londrina já são 02h30 em UTC, e o dia da loja continua sendo o de Londrina.
 */
export function todayIso(now: Date = new Date(), timeZone?: string): string {
  if (!timeZone) return isoDate(now);
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(now);
  const part = (type: string) => parts.find((item) => item.type === type)?.value ?? "";
  return `${part("year")}-${part("month")}-${part("day")}`;
}

/** O fuso da casa (Londrina). */
export const STORE_TIME_ZONE = "America/Sao_Paulo";

export function addDays(iso: string, days: number): string {
  const date = parseIsoDate(iso);
  if (!date) return iso;
  date.setDate(date.getDate() + days);
  return isoDate(date);
}

/** Dias de `from` até `to` (negativo se `to` vem antes). */
export function daysBetween(from: string, to: string): number {
  const a = parseIsoDate(from);
  const b = parseIsoDate(to);
  if (!a || !b) return 0;
  return Math.round((b.getTime() - a.getTime()) / 86_400_000);
}

/** "2026-10-02" → "02/10". */
export function shortDayMonth(iso: string): string {
  const match = ISO.exec(iso ?? "");
  return match ? `${match[3]}/${match[2]}` : "";
}

/** "2026-10-02" → "qui". */
export function weekdayShort(iso: string): string {
  const date = parseIsoDate(iso);
  return date ? WEEKDAY_SHORT[date.getDay()]! : "";
}

/** "2026-10-03" → "Sábado"; "2026-10-05" → "Segunda-feira" (por extenso). */
export function weekdayLong(iso: string): string {
  const date = parseIsoDate(iso);
  return date ? WEEKDAY_LONG[date.getDay()]! : "";
}

function capitalize(text: string): string {
  return text ? text[0]!.toUpperCase() + text.slice(1) : text;
}

/** "Qui 02/10": o dia da semana sempre junto da data. */
export function weekdayAndDate(iso: string): string {
  const weekday = weekdayShort(iso);
  return weekday ? `${capitalize(weekday)} ${shortDayMonth(iso)}` : shortDayMonth(iso);
}

/**
 * O rótulo de UM dia, sempre com o dia da semana: "Hoje, qui 02/10",
 * "Amanhã, sex 03/10", "Ontem, qua 01/10" e, longe de hoje, "Ter 29/09".
 */
export function dayLabel(iso: string, today: string): string {
  if (!parseIsoDate(iso)) return "";
  const offset = daysBetween(today, iso);
  const tail = `${weekdayShort(iso)} ${shortDayMonth(iso)}`;
  if (offset === 0) return `Hoje, ${tail}`;
  if (offset === 1) return `Amanhã, ${tail}`;
  if (offset === -1) return `Ontem, ${tail}`;
  return weekdayAndDate(iso);
}

// ── Tipo 1: escolha rápida de dia ────────────────────────────────────────────

export interface DayContext {
  /** O hoje da LOJA (um tablet com fuso errado agendaria para ontem). */
  today: string;
  /** Primeira data aceita. */
  min?: string;
  /** Última data aceita (ex.: `max_preorder_days` do Admin). */
  max?: string;
  /**
   * As datas em que a casa opera, já sem dia fechado e feriado. Uma data que cai
   * DENTRO da lista e não está nela é dia fechado; depois da última, quem decide é
   * o servidor (a lista pode só não ter chegado tão longe).
   */
  availableDates?: readonly string[] | null;
}

/** Os motivos curtos, ditos no próprio botão. */
export const DAY_BLOCK_REASONS = {
  closed: "fechado",
  beforeMin: "indisponível",
  afterMax: "fora do prazo",
} as const;

/** Por que este dia não se escolhe ("" = pode). */
export function dayBlockReason(iso: string, context: DayContext): string {
  if (context.min && iso < context.min) return DAY_BLOCK_REASONS.beforeMin;
  if (context.max && iso > context.max) return DAY_BLOCK_REASONS.afterMax;
  const open = context.availableDates;
  if (open && open.length) {
    const last = open[open.length - 1]!;
    if (iso <= last && !open.includes(iso)) return DAY_BLOCK_REASONS.closed;
  }
  return "";
}

export type QuickDayKey = "today" | "tomorrow" | "next";

export interface QuickDayOption {
  key: QuickDayKey;
  iso: string;
  /** Linha grande: "Hoje", "Amanhã", "Sábado". */
  title: string;
  /** Linha pequena: "Qui 02/10", "04/10", ou "Qui 02/10 · fechado". */
  caption: string;
  /** Motivo de não se escolher ("" = escolhe). */
  reason: string;
}

/** Até onde procurar a próxima data quando nada limita (dois meses). */
const NEXT_DAY_HORIZON = 62;

/**
 * Os três dias de um toque: hoje, amanhã e a próxima data DEPOIS de amanhã que o
 * contexto permite. Hoje e amanhã aparecem sempre (apagados com o motivo quando o
 * contexto não deixa); a terceira é nominada pelo dia da semana por extenso.
 */
export function quickDayOptions(context: DayContext): QuickDayOption[] {
  const { today } = context;
  const tomorrow = addDays(today, 1);
  const fixed = (key: QuickDayKey, iso: string, title: string): QuickDayOption => {
    const reason = dayBlockReason(iso, context);
    const caption = weekdayAndDate(iso);
    return { key, iso, title, caption: reason ? `${caption} · ${reason}` : caption, reason };
  };

  let next = "";
  let candidate = addDays(today, 2);
  for (let step = 0; step < NEXT_DAY_HORIZON; step += 1) {
    if (context.max && candidate > context.max) break;
    if (!dayBlockReason(candidate, context)) {
      next = candidate;
      break;
    }
    candidate = addDays(candidate, 1);
  }
  // Nenhuma data permitida adiante: o botão fica, apagado, com o motivo do
  // depois de amanhã (desaparecer mudaria a posição do "Outra data").
  const nextIso = next || addDays(today, 2);
  const nextReason = next ? "" : dayBlockReason(nextIso, context) || DAY_BLOCK_REASONS.beforeMin;
  return [
    fixed("today", today, "Hoje"),
    fixed("tomorrow", tomorrow, "Amanhã"),
    {
      key: "next",
      iso: nextIso,
      title: weekdayLong(nextIso),
      caption: nextReason ? `${shortDayMonth(nextIso)} · ${nextReason}` : shortDayMonth(nextIso),
      reason: nextReason,
    },
  ];
}

/** A segunda linha do "Outra data": a data escolhida por lá, ou o convite. */
export function otherDayCaption(value: string, options: readonly QuickDayOption[]): string {
  if (value && parseIsoDate(value) && !options.some((option) => option.iso === value)) {
    return weekdayAndDate(value);
  }
  return "No calendário";
}

// ── Tipo 2: período ──────────────────────────────────────────────────────────

/**
 * - `calendar`: o dia, a semana, o mês, o ano que contém a âncora;
 * - `rolling`: os últimos N dias, terminando hoje (o passado);
 * - `upcoming`: os próximos N dias, começando hoje (o futuro).
 */
export type PeriodKind = "calendar" | "rolling" | "upcoming";

export interface PeriodPreset {
  key: string;
  /** O chip, curto, dentro do grupo que já diz "Últimos"/"Próximos": "7D". */
  label: string;
  /** O nome por extenso, no botão: "Últimos 7 dias". Ausente, vale `label`. */
  title?: string;
  kind: PeriodKind;
  /** Só nas janelas móveis; "Máx" corre desde `epoch`. */
  days?: number;
}

/** Período do calendário. A semana começa na segunda. */
export const PERIOD_PRESETS_CALENDAR: readonly PeriodPreset[] = [
  { key: "day", label: "Dia", kind: "calendar" },
  { key: "week", label: "Semana", kind: "calendar" },
  { key: "month", label: "Mês", kind: "calendar" },
  { key: "year", label: "Ano", kind: "calendar" },
];

/** Janelas móveis terminando hoje. */
export const PERIOD_PRESETS_ROLLING: readonly PeriodPreset[] = [
  { key: "7d", label: "7D", title: "Últimos 7 dias", kind: "rolling", days: 7 },
  // 28 e não 30: quatro semanas exatas têm o mesmo mix de dias da semana, então
  // médias e comparações não mentem (sábado não é terça numa padaria).
  { key: "28d", label: "28D", title: "Últimos 28 dias", kind: "rolling", days: 28 },
  { key: "3m", label: "3M", title: "Últimos 3 meses", kind: "rolling", days: 90 },
  { key: "6m", label: "6M", title: "Últimos 6 meses", kind: "rolling", days: 180 },
  { key: "1y", label: "1A", title: "Último ano", kind: "rolling", days: 365 },
  { key: "5y", label: "5A", title: "Últimos 5 anos", kind: "rolling", days: 1826 },
  { key: "max", label: "Máx", title: "Todo o histórico", kind: "rolling" },
];

/** Janelas móveis começando hoje: para quem trabalha com o que está por vir. */
export const PERIOD_PRESETS_UPCOMING: readonly PeriodPreset[] = [
  { key: "next7d", label: "7D", title: "Próximos 7 dias", kind: "upcoming", days: 7 },
  { key: "next14d", label: "14D", title: "Próximos 14 dias", kind: "upcoming", days: 14 },
  { key: "next28d", label: "28D", title: "Próximos 28 dias", kind: "upcoming", days: 28 },
];

export const PERIOD_PRESETS: readonly PeriodPreset[] = [
  ...PERIOD_PRESETS_CALENDAR,
  ...PERIOD_PRESETS_UPCOMING,
  ...PERIOD_PRESETS_ROLLING,
];

/** Tudo o que olha para trás: o que o B.I. oferece. */
export const PAST_PERIOD_PRESETS: readonly string[] = [
  ...PERIOD_PRESETS_CALENDAR,
  ...PERIOD_PRESETS_ROLLING,
].map((preset) => preset.key);

export const CUSTOM_PERIOD = "custom";

/**
 * O período escolhido. O significado de `from`/`to` depende do preset:
 *
 * - calendário (`day`/`week`/`month`/`year`): `from` é a DATA-ÂNCORA, o período é o
 *   que a contém; `""` = o que contém hoje (acompanha a virada do dia);
 * - janela móvel do passado (`7d`…`5y`): `to` é o último dia; `""` = termina hoje;
 * - janela móvel do futuro (`next7d`…): `from` é o primeiro dia; `""` = começa hoje;
 * - `custom`: `from` e `to` são o intervalo.
 */
export interface PeriodSelection {
  preset: string;
  from: string;
  to: string;
}

export interface PeriodBounds {
  today: string;
  /** Primeira data com sentido (nada anda para antes dela). */
  min?: string;
  /** Última data com sentido. No B.I. é hoje: o calendário corre do início até hoje. */
  max?: string;
  /** Onde "Máx" começa (o primeiro dado da casa). */
  epoch?: string;
  /** O intervalo mais longo que o consumidor aceita no personalizado (ex.: 62). */
  maxSpanDays?: number;
}

export interface PeriodRange {
  date_from: string;
  date_to: string;
}

export function findPreset(key: string): PeriodPreset | undefined {
  return PERIOD_PRESETS.find((preset) => preset.key === key);
}

/** O período de calendário que contém `anchor`, inteiro (sem cortar no `max`). */
export function calendarRange(preset: string, anchor: string): PeriodRange {
  const date = parseIsoDate(anchor);
  if (!date) return { date_from: anchor, date_to: anchor };
  if (preset === "week") {
    const monday = addDays(anchor, -((date.getDay() + 6) % 7));
    return { date_from: monday, date_to: addDays(monday, 6) };
  }
  if (preset === "month") {
    const last = new Date(date.getFullYear(), date.getMonth() + 1, 0);
    return { date_from: `${anchor.slice(0, 7)}-01`, date_to: isoDate(last) };
  }
  if (preset === "year") {
    return { date_from: `${date.getFullYear()}-01-01`, date_to: `${date.getFullYear()}-12-31` };
  }
  return { date_from: anchor, date_to: anchor };
}

function clamp(range: PeriodRange, bounds: PeriodBounds): PeriodRange {
  let { date_from, date_to } = range;
  if (bounds.max && date_to > bounds.max) date_to = bounds.max;
  if (bounds.min && date_from < bounds.min) date_from = bounds.min;
  if (date_from > date_to) date_from = date_to;
  return { date_from, date_to };
}

/** Seleção → `date_from`/`date_to` (o servidor ainda normaliza e corta). */
export function resolvePeriod(selection: PeriodSelection, bounds: PeriodBounds): PeriodRange {
  const { today } = bounds;
  if (selection.preset === CUSTOM_PERIOD) {
    if (selection.from && selection.to) return { date_from: selection.from, date_to: selection.to };
    return { date_from: today, date_to: today };
  }
  const preset = findPreset(selection.preset);
  if (!preset || preset.kind === "calendar") {
    return clamp(calendarRange(preset?.key ?? "day", selection.from || today), bounds);
  }
  if (preset.key === "max") {
    return { date_from: bounds.epoch || bounds.min || today, date_to: today };
  }
  if (preset.kind === "upcoming") {
    const start = selection.from || today;
    return { date_from: start, date_to: addDays(start, (preset.days ?? 7) - 1) };
  }
  const end = selection.to || today;
  return { date_from: addDays(end, -((preset.days ?? 28) - 1)), date_to: end };
}

/** O período segue a virada do dia (âncora vazia)? Personalizado nunca segue. */
export function isCurrentPeriod(selection: PeriodSelection): boolean {
  if (selection.preset === CUSTOM_PERIOD) return false;
  const preset = findPreset(selection.preset);
  return preset?.kind === "rolling" ? !selection.to : !selection.from;
}

/** Janela móvel de N dias (do passado ou do futuro)? */
function isWindow(preset: PeriodPreset | undefined): boolean {
  return preset?.kind === "rolling" || preset?.kind === "upcoming";
}

function contains(range: PeriodRange, iso: string): boolean {
  return range.date_from <= iso && iso <= range.date_to;
}

function shiftMonth(anchor: string, months: number): string {
  const date = parseIsoDate(anchor)!;
  return isoDate(new Date(date.getFullYear(), date.getMonth() + months, 1));
}

/**
 * ‹ › — o período igual ao escolhido, um para trás ou para a frente: dia → dia
 * anterior; semana → semana anterior; mês → mês anterior; janela de N dias (7D,
 * 28D, personalizado) → os N dias antes. `null` quando não há para onde andar
 * ("Máx", ou o passo sairia de `min`/`max`).
 */
export function stepPeriod(
  selection: PeriodSelection,
  direction: 1 | -1,
  bounds: PeriodBounds,
): PeriodSelection | null {
  const { today } = bounds;
  const outOfBounds = (range: PeriodRange) =>
    (direction > 0 && !!bounds.max && range.date_from > bounds.max) ||
    (direction < 0 && !!bounds.min && range.date_to < bounds.min);

  if (selection.preset === CUSTOM_PERIOD) {
    if (!selection.from || !selection.to) return null;
    const length = daysBetween(selection.from, selection.to) + 1;
    const next = {
      date_from: addDays(selection.from, direction * length),
      date_to: addDays(selection.to, direction * length),
    };
    if (outOfBounds(next)) return null;
    return { preset: CUSTOM_PERIOD, from: next.date_from, to: next.date_to };
  }

  const preset = findPreset(selection.preset);
  if (!preset || preset.key === "max") return null;

  if (preset.kind === "rolling") {
    const days = preset.days ?? 28;
    const end = addDays(selection.to || today, direction * days);
    const next = { date_from: addDays(end, -(days - 1)), date_to: end };
    if (outOfBounds(next)) return null;
    // Alcançou (ou passou) hoje: volta a ser "os últimos N dias", que acompanha a
    // virada. Já estando nela, não há para onde andar (o toque não pode ser inerte).
    if (end >= today) return isCurrentPeriod(selection) ? null : { preset: preset.key, from: "", to: "" };
    return { preset: preset.key, from: "", to: end };
  }

  if (preset.kind === "upcoming") {
    // O espelho da janela do passado: voltar até hoje (ou antes) volta a ser "os
    // próximos N dias"; já estando nela, ‹ não tem para onde ir.
    const days = preset.days ?? 7;
    const start = addDays(selection.from || today, direction * days);
    const next = { date_from: start, date_to: addDays(start, days - 1) };
    if (outOfBounds(next)) return null;
    if (start <= today) return isCurrentPeriod(selection) ? null : { preset: preset.key, from: "", to: "" };
    return { preset: preset.key, from: start, to: "" };
  }

  const anchor = selection.from || today;
  let target: string;
  if (preset.key === "week") target = addDays(anchor, 7 * direction);
  else if (preset.key === "month") target = shiftMonth(anchor, direction);
  else if (preset.key === "year") target = `${Number(anchor.slice(0, 4)) + direction}-01-01`;
  else target = addDays(anchor, direction);

  const next = calendarRange(preset.key, target);
  if (outOfBounds(next)) return null;
  return { preset: preset.key, from: contains(next, today) ? "" : target, to: "" };
}

/** A âncora de qualquer seleção: o dia que um período de calendário deve conter. */
function anchorOf(selection: PeriodSelection, today: string): string {
  if (selection.preset === CUSTOM_PERIOD) return selection.to || today;
  const preset = findPreset(selection.preset);
  if (preset?.kind === "rolling") return selection.to || today;
  // Calendário e janela do futuro: a âncora é o primeiro dia.
  return selection.from || today;
}

/**
 * Trocar de granularidade. No calendário, a âncora fica (quem olhava a quinta
 * passada e toca "Semana" vê a semana daquela quinta); janela móvel recomeça
 * terminando hoje.
 */
export function withPreset(selection: PeriodSelection, key: string, bounds: PeriodBounds): PeriodSelection {
  const preset = findPreset(key);
  if (!preset || isWindow(preset)) return { preset: key, from: "", to: "" };
  const anchor = anchorOf(selection, bounds.today);
  const range = calendarRange(key, anchor);
  return { preset: key, from: contains(range, bounds.today) ? "" : anchor, to: "" };
}

/**
 * A ponte para os quadros que guardam UM dia (a Produção, a Expedição, o quadro
 * da TV, as Encomendas): o dia do consumidor vira a seleção do período, e volta.
 * Dia vazio é hoje.
 */
export function periodOfDay(preset: string, iso: string, today: string): PeriodSelection {
  return withPreset({ preset, from: iso || today, to: "" }, preset, { today });
}

/** O dia que a seleção aponta: a âncora, ou hoje quando ela acompanha a virada. */
export function periodAnchor(selection: PeriodSelection, today: string): string {
  return anchorOf(selection, today);
}

/** Ir para um dia, mantendo a granularidade de calendário (ou caindo em Dia). */
export function goToDate(selection: PeriodSelection, iso: string, bounds: PeriodBounds): PeriodSelection {
  const preset = findPreset(selection.preset);
  const key = preset?.kind === "calendar" ? preset.key : "day";
  return withPreset({ preset: key, from: iso, to: "" }, key, bounds);
}

export function customPeriod(from: string, to: string): PeriodSelection {
  return from <= to
    ? { preset: CUSTOM_PERIOD, from, to }
    : { preset: CUSTOM_PERIOD, from: to, to: from };
}

/** O período que contém hoje, na mesma granularidade. */
export function currentPeriod(selection: PeriodSelection): PeriodSelection {
  if (selection.preset === CUSTOM_PERIOD) return { preset: "day", from: "", to: "" };
  return { preset: selection.preset, from: "", to: "" };
}

/**
 * O rótulo do botão: o período e a janela efetiva, sempre à vista. Dia diz o dia
 * da semana ("Hoje, qui 02/10"); o resto diz o nome por extenso e o intervalo
 * ("Semana · 29/09 a 05/10", "Próximos 7 dias · 03/10 a 09/10"). O chip pode
 * dizer "7D" porque o grupo diz "Últimos" ou "Próximos"; o botão não tem grupo,
 * e "7D" sozinho não diz se é para trás ou para a frente.
 */
export function periodLabel(selection: PeriodSelection, range: PeriodRange, today: string): string {
  if (selection.preset === "day") return dayLabel(range.date_from, today);
  const preset = findPreset(selection.preset);
  const name =
    selection.preset === CUSTOM_PERIOD ? "Personalizado" : (preset?.title ?? preset?.label ?? "Período");
  if (range.date_from === range.date_to) return `${name} · ${dayLabel(range.date_from, today)}`;
  return `${name} · ${shortDayMonth(range.date_from)} a ${shortDayMonth(range.date_to)}`;
}

/**
 * O gatilho curto (`compact`, no celular): a mesma janela, em menos letras. Dia
 * perto de hoje diz só "Hoje", "Ontem" ou "Amanhã" (as setas e "Voltar para hoje"
 * dizem o resto); longe, "Ter 29/09". O resto troca o nome por extenso pelo chip
 * ("28D · 04/09 a 01/10"): as datas ao lado dizem se é para trás ou para a frente,
 * que era o que o chip sozinho não dizia. O nome inteiro segue no nome acessível.
 */
export function periodShortLabel(selection: PeriodSelection, range: PeriodRange, today: string): string {
  const dayShort = (iso: string) => {
    const offset = daysBetween(today, iso);
    if (offset === 0) return "Hoje";
    if (offset === 1) return "Amanhã";
    if (offset === -1) return "Ontem";
    return weekdayAndDate(iso);
  };
  if (selection.preset === "day") return parseIsoDate(range.date_from) ? dayShort(range.date_from) : "";
  const span =
    range.date_from === range.date_to
      ? dayShort(range.date_from)
      : `${shortDayMonth(range.date_from)} a ${shortDayMonth(range.date_to)}`;
  if (selection.preset === CUSTOM_PERIOD) return span;
  return `${findPreset(selection.preset)?.label ?? "Período"} · ${span}`;
}

/** Nome acessível das setas, na unidade do período. */
export function periodStepLabels(preset: string): { prev: string; next: string } {
  if (preset === "day") return { prev: "Dia anterior", next: "Próximo dia" };
  if (preset === "week") return { prev: "Semana anterior", next: "Próxima semana" };
  if (preset === "month") return { prev: "Mês anterior", next: "Próximo mês" };
  if (preset === "year") return { prev: "Ano anterior", next: "Próximo ano" };
  return { prev: "Período anterior", next: "Próximo período" };
}

// ── Personalizado: o intervalo que o consumidor aceita ──────────────────────

/**
 * Por que o intervalo De/Até não se aplica ("" = aplica). O servidor ainda corta,
 * mas cortar em silêncio faria o botão dizer uma janela e a lista mostrar outra.
 */
export function customPeriodError(from: string, to: string, bounds: Omit<PeriodBounds, "today">): string {
  if (!parseIsoDate(from) || !parseIsoDate(to)) return "Escolha as duas datas.";
  const [start, end] = from <= to ? [from, to] : [to, from];
  if (bounds.min && start < bounds.min) return `A primeira data possível é ${shortDayMonth(bounds.min)}.`;
  if (bounds.max && end > bounds.max) return `A última data possível é ${shortDayMonth(bounds.max)}.`;
  if (bounds.maxSpanDays && daysBetween(start, end) + 1 > bounds.maxSpanDays) {
    return `No máximo ${bounds.maxSpanDays} dias por vez.`;
  }
  return "";
}

// ── O período na URL ─────────────────────────────────────────────────────────
//
// Período sempre na URL (plano SUITE-UX): o favorito do kiosk e o link colado
// numa conversa abrem a mesma janela. Três chaves, as mesmas da seleção: `period`
// (a granularidade), `from` e `to` (só quando não acompanham hoje). O que é igual
// ao padrão do consumidor sai da URL, para o endereço ficar curto.

export interface PeriodQueryOptions {
  /** As granularidades que o consumidor aceita (as mesmas do `presets` do controle). */
  presets: readonly string[];
  /** Aceita personalizado. */
  custom?: boolean;
  /** O período quando a URL não diz nada (ou diz algo que não se aceita). */
  fallback: PeriodSelection;
}

/** As chaves que o período ocupa na URL. */
export const PERIOD_QUERY_KEYS = ["period", "from", "to"] as const;

function firstString(raw: unknown): string {
  const value = Array.isArray(raw) ? raw[0] : raw;
  return typeof value === "string" ? value : "";
}

function dateOrEmpty(raw: unknown): string {
  const value = firstString(raw);
  return parseIsoDate(value) ? value : "";
}

/** URL → seleção. Valor ilegível ou não aceito cai no padrão, nunca em erro. */
export function periodFromQuery(query: Record<string, unknown>, options: PeriodQueryOptions): PeriodSelection {
  const key = firstString(query.period);
  if (!key) return { ...options.fallback };
  const from = dateOrEmpty(query.from);
  const to = dateOrEmpty(query.to);
  if (key === CUSTOM_PERIOD) {
    return options.custom && from && to ? customPeriod(from, to) : { ...options.fallback };
  }
  const preset = findPreset(key);
  if (!preset || !options.presets.includes(key)) return { ...options.fallback };
  if (preset.kind === "rolling") return { preset: key, from: "", to };
  return { preset: key, from, to: "" };
}

/** Seleção → as chaves da URL (vazio quando é o padrão do consumidor). */
export function periodToQuery(selection: PeriodSelection, fallback: PeriodSelection): Record<string, string> {
  if (
    selection.preset === fallback.preset &&
    selection.from === fallback.from &&
    selection.to === fallback.to
  ) {
    return {};
  }
  const query: Record<string, string> = { period: selection.preset };
  if (selection.from) query.from = selection.from;
  if (selection.to) query.to = selection.to;
  return query;
}
