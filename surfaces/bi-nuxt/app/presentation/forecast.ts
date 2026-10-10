// O que só a Projeção ("O que esperar?") diz: o rótulo de cada dia, o gráfico do
// período, a tabela dia a dia e o CSV dos mesmos números. Puro e testado em
// tests/forecast.test.ts; a página só compõe.
import type { ReadingChartPoint, ReadingChartSeries, ReadingCsv } from "../../../operator-kit/app/presentation/readingChart";
import { csvMoney, formatInt, formatMoney, missingLabel, rangeLabel, reais, shortDate, shortDateWithYear } from "./bi";
import type { DayForecast, ForecastOccasion, OccasionYear } from "~/types/bi";

export type ForecastHorizon = "day" | "week" | "month";

/** "sexta-feira" → "Sex 09/10": o rótulo do eixo e da primeira coluna. */
export function forecastDayLabel(day: Pick<DayForecast, "weekday_label" | "date">): string {
  const short = day.weekday_label.slice(0, 3);
  return `${short.charAt(0).toUpperCase()}${short.slice(1)} ${shortDate(day.date)}`;
}

/**
 * "Uma sexta-feira comum", "Um sábado comum". O artigo segue o gênero do dia da
 * semana: a tela dizia "Um sexta-feira comum".
 */
export function ordinaryWeekdayLabel(weekdayLabel: string): string {
  const article = weekdayLabel.endsWith("-feira") ? "Uma" : "Um";
  return `${article} ${weekdayLabel} comum`;
}

/**
 * "Dia das Mães (véspera)" em vez de tentar "Véspera do/da …": o artigo depende
 * do gênero do nome, que vem do calendário e não é derivável da string.
 */
export function occasionTitle(occasion: Pick<ForecastOccasion, "name" | "is_eve">): string {
  return `${occasion.name}${occasion.is_eve ? " (véspera)" : ""}`;
}

/** "1,2×": quantas vezes um dia normal da época a ocorrência fez. */
export function occasionRatioLabel(ratio: number): string {
  return `${ratio.toFixed(1).replace(".", ",")}×`;
}

export interface OccasionYearRow {
  date: string;
  label: string;
  revenue: string;
  ratio: string;
}

export function occasionYearRows(years: OccasionYear[]): OccasionYearRow[] {
  return years.map((year) => ({
    date: year.date,
    label: shortDateWithYear(year.date),
    revenue: formatMoney(year.revenue_q),
    ratio: occasionRatioLabel(year.ratio),
  }));
}

export function occasionYearsCsv(years: OccasionYear[]): ReadingCsv {
  return {
    header: ["Ocorrência", "Faturamento (R$)", "Contra um dia normal"],
    rows: years.map((year) => [shortDateWithYear(year.date), csvMoney(year.revenue_q), Number(year.ratio.toFixed(2))]),
  };
}

// ── O período (semana ou mês) ───────────────────────────────────────────────

/** O provável em linha com área; as duas pontas da faixa em linha fina. */
export const FORECAST_SERIES: ReadingChartSeries[] = [
  { key: "expected", label: "Faturamento provável", tone: "primary" },
  { key: "low", label: "Ponta baixa da faixa", tone: "neutral" },
  { key: "high", label: "Ponta alta da faixa", tone: "neutral" },
];

/** Dia fechado ou sem base não vira zero: o ponto fica sem dado. */
export function forecastChartPoints(days: DayForecast[]): ReadingChartPoint[] {
  return days.map((day) => ({
    label: forecastDayLabel(day),
    values: {
      expected: day.closed ? null : reais(day.revenue_q?.expected),
      low: day.closed ? null : reais(day.revenue_q?.low),
      high: day.closed ? null : reais(day.revenue_q?.high),
    },
  }));
}

export interface ForecastDayRow {
  date: string;
  label: string;
  revenue: string;
  range: string;
  orders: string;
  note: string;
}

/** O que a linha diz quando não há número: fechado (e por quê) ou sem base. */
export function forecastDayNote(day: DayForecast): string {
  if (day.closed) return `Fechado${day.closed_reason ? ` (${day.closed_reason})` : ""}`;
  if (!day.revenue_q) return missingLabel(day.missing_reason);
  return "";
}

const NO_NUMBER = "sem dado";

export function forecastDayRows(days: DayForecast[]): ForecastDayRow[] {
  return days.map((day) => {
    const open = !day.closed;
    return {
      date: day.date,
      label: forecastDayLabel(day),
      revenue: open && day.revenue_q ? formatMoney(Math.round(day.revenue_q.expected)) : NO_NUMBER,
      range: open && day.revenue_q ? rangeLabel(day.revenue_q.low, day.revenue_q.high) : NO_NUMBER,
      orders: open && day.orders ? formatInt(Math.round(day.orders.expected)) : NO_NUMBER,
      note: forecastDayNote(day),
    };
  });
}

export function forecastDaysCsv(days: DayForecast[]): ReadingCsv {
  return {
    header: [
      "Dia",
      "Data",
      "Faturamento provável (R$)",
      "Ponta baixa da faixa (R$)",
      "Ponta alta da faixa (R$)",
      "Pedidos prováveis",
      "Observação",
    ],
    rows: days.map((day) => {
      const open = !day.closed;
      return [
        day.weekday_label,
        shortDateWithYear(day.date),
        open ? csvMoney(day.revenue_q?.expected) : "",
        open ? csvMoney(day.revenue_q?.low) : "",
        open ? csvMoney(day.revenue_q?.high) : "",
        open && day.orders ? Math.round(day.orders.expected) : "",
        forecastDayNote(day),
      ];
    }),
  };
}

/** "Sem total do período": os dias sem base, por extenso. */
export function missingDaysLabel(dates: string[]): string {
  return dates.map(shortDate).join(", ");
}

// ── O período na URL ────────────────────────────────────────────────────────

const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;
const HORIZONS: readonly ForecastHorizon[] = ["day", "week", "month"];

function first(value: unknown): string {
  const raw = Array.isArray(value) ? value[0] : value;
  return typeof raw === "string" ? raw : "";
}

/**
 * O planejamento mora na URL (`?horizon=week&target=2026-10-12`), para o "Copiar
 * link desta leitura" e o compartilhar abrirem o mesmo dia. Chaves próprias, não
 * as `period`/`from` da janela das outras telas: o futuro planejado não pode
 * vazar para a janela do passado ao trocar de aba. Valor ilegível cai no padrão.
 */
export function forecastFromQuery(
  query: Record<string, unknown>,
  fallbackTarget: string,
): { horizon: ForecastHorizon; target: string } {
  const horizon = first(query.horizon);
  const target = first(query.target);
  return {
    horizon: (HORIZONS as readonly string[]).includes(horizon) ? (horizon as ForecastHorizon) : "day",
    target: ISO_DATE.test(target) ? target : fallbackTarget,
  };
}

/** Só o que difere do padrão (amanhã, um dia) ocupa a URL. */
export function forecastToQuery(
  value: { horizon: ForecastHorizon; target: string },
  fallbackTarget: string,
): Record<string, string> {
  const query: Record<string, string> = {};
  if (value.horizon !== "day") query.horizon = value.horizon;
  if (value.target !== fallbackTarget) query.target = value.target;
  return query;
}
