// A Produção (aba "Sobrou ou faltou" e aba "Lotes no período", `?view=lots`): a parte pura. A página só desenha o que sai
// daqui. A série diária vira os pontos do gráfico de leitura do kit
// (`OperatorReadingChart`) e as linhas do quadro "Dia a dia", que é onde o previsto,
// a perda e o mix de preço ficam à vista de quem toca, usa o teclado ou lê com leitor
// de tela (antes só apareciam no `:hover` da barra; laudo F01).
import type { BIOvenTimeRow, BIProductionReport } from "~/types/bi";
import type {
  ReadingChartPoint,
  ReadingChartSeries,
  ReadingCsv,
} from "../../../operator-kit/app/presentation/readingChart";
import { BUCKET_SPAN_LABELS, bucketLabel, bucketRows, formatInt, formatMinutes } from "./bi";

/** As duas abas da Produção: o dia (padrão, fora da URL) e os lotes no período. */
export const PRODUCTION_VIEWS = [
  { value: "day", label: "Sobrou ou faltou", icon: "i-lucide-scale" },
  { value: "lots", label: "Lotes no período", icon: "i-lucide-layers" },
] as const;

export type ProductionView = (typeof PRODUCTION_VIEWS)[number]["value"];

/** A aba da URL (`?view=lots`); qualquer outro valor é o dia. */
export function productionView(raw: unknown): ProductionView {
  return raw === "lots" ? "lots" : "day";
}

const sum = (values: readonly (string | number)[]) => values.reduce((total: number, v) => total + Number(v), 0);

/** Realizado ÷ previsto em %, ou `null` quando nada foi previsto (sem dado, nunca zero). */
export function yieldPercent(finished: number, started: number): number | null {
  return started ? Math.round((finished * 100) / started) : null;
}

export interface ProductionBucket {
  /** O rótulo do eixo ("14/08", "ago/25"). */
  label: string;
  /** "semana"/"mês" quando a série foi agrupada; vazio no grão diário. */
  span: string;
  started: number;
  finished: number;
  previous: number;
  loss: number;
  fullPrice: number;
  discounted: number;
  yield: number | null;
}

/** A série do período, agrupada como o gráfico a desenha (dia, semana ou mês). */
export function productionBuckets(report: BIProductionReport): ProductionBucket[] {
  const previous = report.previous.finished_by_day;
  const days = report.days.map((day, index) => ({ ...day, prev_finished: Number(previous[index] ?? 0) }));
  return bucketRows(days).map((bucket) => {
    const started = sum(bucket.rows.map((d) => d.started));
    const finished = sum(bucket.rows.map((d) => d.finished));
    return {
      label: bucketLabel(bucket.date, bucket.span),
      span: BUCKET_SPAN_LABELS[bucket.span],
      started,
      finished,
      previous: sum(bucket.rows.map((d) => d.prev_finished)),
      loss: sum(bucket.rows.map((d) => d.loss)),
      fullPrice: sum(bucket.rows.map((d) => d.full_price)),
      discounted: sum(bucket.rows.map((d) => d.discounted)),
      yield: yieldPercent(finished, started),
    };
  });
}

/** O nome do eixo: "Dia", ou "Semana"/"Mês" quando a série longa foi agrupada. */
export function bucketAxisLabel(buckets: readonly ProductionBucket[]): string {
  const span = buckets[0]?.span;
  return span === "semana" ? "Semana" : span === "mês" ? "Mês" : "Dia";
}

export const FINISHED_SERIES: ReadingChartSeries[] = [
  { key: "finished", label: "Saíram do forno" },
  { key: "previous", label: "Período anterior", tone: "neutral" },
];

export const YIELD_SERIES: ReadingChartSeries[] = [{ key: "yield", label: "Aproveitamento" }];

export function finishedPoints(buckets: readonly ProductionBucket[]): ReadingChartPoint[] {
  return buckets.map((b) => ({ label: b.label, values: { finished: b.finished, previous: b.previous } }));
}

export function yieldPoints(buckets: readonly ProductionBucket[]): ReadingChartPoint[] {
  return buckets.map((b) => ({ label: b.label, values: { yield: b.yield } }));
}

export const formatPercentValue = (value: number) => `${value}%`;

/** Uma linha do quadro "Dia a dia", já escrita como a tela a diz. */
export interface ProductionDayRow {
  label: string;
  started: string;
  finished: string;
  loss: string;
  yield: string;
  fullPrice: string;
  discounted: string;
}

export function productionDayRows(buckets: readonly ProductionBucket[]): ProductionDayRow[] {
  return buckets.map((b) => ({
    label: b.label,
    started: formatInt(b.started),
    finished: formatInt(b.finished),
    loss: formatInt(b.loss),
    yield: b.yield === null ? "sem produção" : `${b.yield}%`,
    fullPrice: formatInt(b.fullPrice),
    discounted: formatInt(b.discounted),
  }));
}

/** O CSV do "Dia a dia": número cru, para quem abre fazer conta. */
export function productionDaysCsv(buckets: readonly ProductionBucket[]): ReadingCsv {
  return {
    header: [bucketAxisLabel(buckets), "Previsto", "Saíram do forno", "Período anterior", "Perda", "Aproveitamento (%)", "A preço cheio", "Com desconto"],
    rows: buckets.map((b) => [b.label, b.started, b.finished, b.previous, b.loss, b.yield ?? "", b.fullPrice, b.discounted]),
  };
}

// ── Tempo de forno ───────────────────────────────────────────────────────────

/** Linhas antes do "Ver todas" (o padrão "+N" do Gestor; laudo F20). */
export const OVEN_FOCUS_ROWS = 8;

export interface OvenRow {
  ref: string;
  label: string;
  /** A média em minutos, crua, para a barra da célula. */
  minutes: number;
  average: string;
  p90: string;
  planned: string;
  runs: string;
}

export function ovenRows(rows: readonly BIOvenTimeRow[]): OvenRow[] {
  return rows.map((row) => ({
    ref: row.ref,
    label: row.label,
    minutes: Number(row.avg_minutes),
    average: formatMinutes(row.avg_minutes),
    p90: formatMinutes(row.p90_minutes),
    planned: formatMinutes(row.avg_planned_minutes),
    runs: formatInt(row.runs),
  }));
}

/** O teto da barra de média: a maior média da lista (nunca zero, para a barra não dividir por zero). */
export function ovenScale(rows: readonly OvenRow[]): number {
  return Math.max(1, ...rows.map((row) => row.minutes));
}

export function ovenCsv(first: string, rows: readonly BIOvenTimeRow[]): ReadingCsv {
  return {
    header: [first, "Média (min)", "p90 (min)", "Armado (min)", "Medições"],
    rows: rows.map((row) => [row.label, row.avg_minutes, row.p90_minutes, row.avg_planned_minutes, row.runs]),
  };
}

/** O botão que abre o resto da lista: diz quantas faltam. */
export function showAllLabel(total: number, noun: { one: string; many: string }): string {
  return `Ver ${total === 1 ? `a ${noun.one}` : `as ${formatInt(total)} ${noun.many}`}`;
}
