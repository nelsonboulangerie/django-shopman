// Entregas — o custo da TaOn (corridas da casa) e o frete que os clientes
// pagaram nos mesmos pedidos. A projection já conta cada corrida uma vez; aqui
// só a frase da resposta e a forma das séries.
import type { BIDeliveryCostReport } from "~/types/bi";
import { formatInt, formatMoney } from "~/presentation/bi";

/** A resposta em uma frase: quanto a entrega custou e se o frete cobriu. */
export function deliveryAnswer(
  report: Pick<BIDeliveryCostReport, "rides" | "cost_q" | "balance_q">,
): string {
  if (!report.rides) return "Nenhuma corrida da TaOn no período.";
  if (report.balance_q > 0) {
    return `O frete cobriu a TaOn e sobrou ${formatMoney(report.balance_q)}.`;
  }
  if (report.balance_q === 0) return "O frete cobriu a TaOn, exatamente.";
  return `A casa pôs ${formatMoney(-report.balance_q)} do bolso nas entregas.`;
}

/** "3 corridas pela cotação": a parte do custo que ainda não é valor final. */
export function estimatedRidesHint(estimated: number): string {
  if (!estimated) return "";
  return estimated === 1
    ? "1 corrida terminou sem valor final da TaOn e entrou pela cotação."
    : `${formatInt(estimated)} corridas terminaram sem valor final da TaOn e entraram pela cotação.`;
}

/** "12 entregas em 9 corridas": quantas paradas cada corrida levou. */
export function ridesHint(
  report: Pick<BIDeliveryCostReport, "rides" | "deliveries">,
): string {
  const deliveries = `${formatInt(report.deliveries)} ${report.deliveries === 1 ? "entrega" : "entregas"}`;
  const rides = `${formatInt(report.rides)} ${report.rides === 1 ? "corrida" : "corridas"}`;
  return `${deliveries} em ${rides}`;
}
