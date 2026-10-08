// Vendas (PR-B3 do WP-BI-CANON-LAUDO): a parte pura da tela. Monta os pontos que o
// `OperatorReadingChart` do kit desenha e as linhas da tabela "Por canal", a partir do
// `BISalesReport`. Sem Vue; testada em `tests/sales.test.ts`.
import type { ReadingChartPoint, ReadingChartSeries } from "../../../operator-kit/app/presentation/readingChart";
import type { BISalesReport } from "~/types/bi";
import {
  BUCKET_SPAN_LABELS,
  WEEKDAY_LABELS,
  bucketLabel,
  bucketSalesDays,
  channelIcon,
  sharePercent,
  reais,
} from "./bi";

/** "período anterior" vira "Período anterior": o nome da série de comparação. */
function capitalize(text: string): string {
  return text ? text.charAt(0).toUpperCase() + text.slice(1) : text;
}

export function revenueSeries(against: string): ReadingChartSeries[] {
  return [
    { key: "revenue", label: "Faturamento" },
    { key: "previous", label: capitalize(against) },
  ];
}

export interface RevenueReading {
  points: ReadingChartPoint[];
  /** O grão do eixo ("dia", "semana", "mês"), que a descrição do quadro diz. */
  span: "dia" | "semana" | "mês";
}

/**
 * Faturamento por balde (dia, semana ou mês, conforme a janela) e o mesmo balde do
 * período de comparação. O balde só tem o grão da janela inteira, então ele vai na
 * descrição do quadro, não em cada rótulo do eixo.
 */
export function revenueReading(report: Pick<BISalesReport, "days" | "previous">): RevenueReading {
  const previous = report.previous.revenue_by_day ?? [];
  const rows = report.days.map((day, index) => ({ ...day, prev_revenue_q: previous[index] ?? 0 }));
  const buckets = bucketSalesDays(rows);
  const span = buckets[0]?.span ?? "day";
  return {
    span: span === "day" ? "dia" : (BUCKET_SPAN_LABELS[span] as "semana" | "mês"),
    points: buckets.map((bucket) => ({
      label: bucketLabel(bucket.date, bucket.span),
      // Em reais: o gráfico do kit recebe reais (`readingMoneyFormat`).
      values: { revenue: reais(bucket.revenue_q), previous: reais(bucket.prev_revenue_q) },
    })),
  };
}

export const ORDERS_SERIES: ReadingChartSeries[] = [{ key: "orders", label: "Pedidos" }];

export function hourPoints(ordersByHour: readonly number[]): ReadingChartPoint[] {
  return ordersByHour.map((count, hour) => ({ label: `${hour}h`, values: { orders: count } }));
}

/**
 * Pedidos por dia da semana. O dia em que a casa fecha diz isso no próprio rótulo
 * ("dom, fechado"): zero pedido num dia fechado não é dia fraco.
 */
export function weekdayPoints(ordersByWeekday: readonly number[], closedWeekdays: readonly number[]): ReadingChartPoint[] {
  const closed = new Set(closedWeekdays);
  return ordersByWeekday.map((count, index) => {
    const name = WEEKDAY_LABELS[index] ?? String(index);
    return { label: closed.has(index) ? `${name}, fechado` : name, values: { orders: count } };
  });
}

export interface ChannelRow {
  ref: string;
  name: string;
  icon: string;
  orders: number;
  revenue_q: number;
  share: string;
}

export function channelRows(report: Pick<BISalesReport, "by_channel" | "revenue_total_q">): ChannelRow[] {
  return report.by_channel.map((row) => ({
    ref: row.channel_ref,
    name: row.name,
    icon: channelIcon(row.kind),
    orders: row.orders,
    revenue_q: row.revenue_q,
    share: sharePercent(row.revenue_q, report.revenue_total_q),
  }));
}
