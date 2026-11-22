// Entregas — o custo das corridas, por serviço de entrega (o nome do cadastro), e o
// frete que os clientes pagaram nos mesmos pedidos. A projection já conta cada
// corrida uma vez; aqui só a frase da resposta, as linhas por serviço e a forma das
// séries. Uma linha por serviço e o total embaixo: a casa entrega por mais de um
// serviço e o B.I. existe para compará-los (#3144).
import type {
  BIDeliveryCostReport,
  BIDeliveryCostService,
  BIDeliveryTimingReport,
  BIRideTimingService,
} from "~/types/bi";
import type { ReadingCsv } from "../../../operator-kit/app/presentation/readingChart";
import { csvMoney, formatInt, formatMoney } from "~/presentation/bi";
import { minutesLabel } from "~/presentation/preorderKitchen";

/** A resposta em uma frase: quanto a entrega custou e se o frete cobriu. */
export function deliveryAnswer(
  report: Pick<BIDeliveryCostReport, "rides" | "cost_q" | "balance_q">,
): string {
  if (!report.rides) return "Nenhuma corrida no período.";
  if (report.balance_q > 0) {
    return `O frete cobriu as entregas e sobrou ${formatMoney(report.balance_q)}.`;
  }
  if (report.balance_q === 0) return "O frete cobriu as entregas, exatamente.";
  return `A casa pôs ${formatMoney(-report.balance_q)} do bolso nas entregas.`;
}

/** "3 corridas pela cotação": a parte do custo que ainda não é valor final. */
export function estimatedRidesHint(estimated: number): string {
  if (!estimated) return "";
  return estimated === 1
    ? "1 corrida terminou sem valor final e entrou pela cotação."
    : `${formatInt(estimated)} corridas terminaram sem valor final e entraram pela cotação.`;
}

/** A chave da linha do total, que nenhum `ref` de serviço usa. */
export const DELIVERY_TOTAL_KEY = "__total__";

/** Uma linha da tabela por serviço: a do serviço, ou a do total (`service = DELIVERY_TOTAL_KEY`). */
export type DeliveryServiceRow = BIDeliveryCostService;

/** As linhas por serviço, do que mais custou ao que menos, e o total embaixo. */
export function deliveryServiceRows(
  report: Pick<
    BIDeliveryCostReport,
    "services" | "rides" | "deliveries" | "cost_q" | "fee_q" | "balance_q" | "cost_per_delivery_q"
  >,
): DeliveryServiceRow[] {
  if (!report.services.length) return [];
  return [
    ...report.services,
    {
      service: DELIVERY_TOTAL_KEY,
      name: "Total",
      rides: report.rides,
      deliveries: report.deliveries,
      cost_q: report.cost_q,
      fee_q: report.fee_q,
      balance_q: report.balance_q,
      cost_per_delivery_q: report.cost_per_delivery_q,
    },
  ];
}

/** O CSV da tabela por serviço, com o total na última linha. */
export function deliveryServiceCsv(rows: readonly DeliveryServiceRow[]): ReadingCsv {
  return {
    header: ["Serviço", "Corridas", "Entregas", "Custo (R$)", "Frete cobrado (R$)", "Frete menos custo (R$)", "Custo por entrega (R$)"],
    rows: rows.map((row) => [
      row.name,
      row.rides,
      row.deliveries,
      csvMoney(row.cost_q),
      csvMoney(row.fee_q),
      csvMoney(row.balance_q),
      csvMoney(row.cost_per_delivery_q),
    ]),
  };
}

/** "12 entregas em 9 corridas": quantas paradas cada corrida levou. */
export function ridesHint(
  report: Pick<BIDeliveryCostReport, "rides" | "deliveries">,
): string {
  const deliveries = `${formatInt(report.deliveries)} ${report.deliveries === 1 ? "entrega" : "entregas"}`;
  const rides = `${formatInt(report.rides)} ${report.rides === 1 ? "corrida" : "corridas"}`;
  return `${deliveries} em ${rides}`;
}

// ── Tempo das corridas (#2467) ───────────────────────────────────────────────

/** Uma linha da tabela de tempos: a de um serviço, ou a do total (`service = DELIVERY_TOTAL_KEY`). */
export type RideTimingRow = BIRideTimingService;

/** "4 min", "12,5 min"; "Sem medida" quando nenhuma corrida chegou àquele marco no período. */
export const rideMinutes = minutesLabel;

/** As linhas por serviço, na ordem do nome, e o total embaixo (o servidor já manda assim). */
export function rideTimingRows(report: Pick<BIDeliveryTimingReport, "services">): RideTimingRow[] {
  return [...report.services];
}

/** O CSV da tabela de tempos, em minutos, com o total na última linha. */
export function rideTimingCsv(rows: readonly RideTimingRow[]): ReadingCsv {
  const cell = (value: number | null) => (value === null ? "" : String(value).replace(".", ","));
  return {
    header: ["Serviço", "Corridas", "Até aceitar (min)", "Até a coleta (min)", "Na rua (min)", "Total (min)"],
    rows: rows.map((row) => [
      row.name,
      row.rides,
      cell(row.accept_minutes),
      cell(row.pickup_minutes),
      cell(row.street_minutes),
      cell(row.total_minutes),
    ]),
  };
}
