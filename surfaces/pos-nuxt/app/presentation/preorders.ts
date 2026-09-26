// ENCOMENDAS — a seção do PDV que lê o que a casa prometeu (ENCOMENDAS-PDV-PLAN).
//
// O corte é do servidor (`backstage/projections/preorders.py`): todo pedido com
// recebimento — retirada ou entrega —, de qualquer canal, hoje ou depois, pela
// data combinada. Aqui mora só o FORMATO: os intervalos que cada tela pede, o
// agrupamento por janela, e as frases que o balcão lê.
//
// ⚠️ "Encomenda" no resto da suíte é só data futura (o *Agendados* do Gestor).
// A seção diverge por decisão do dono e DIZ o seu corte na tela
// (`PREORDERS_SCOPE_NOTE`), para ninguém procurar a retirada de hoje no Gestor e
// achar que ela sumiu.

import type { OperatorSection } from "../../../operator-kit/app/presentation/appBar";
import type { PreorderCard, PreorderDay, PreorderSituation } from "~/types/preorders";

import { addDays, type TicketRange } from "./orderTickets";
import { dateLabel } from "./schedule";

/** A frase que diz o corte da seção. Uma só, na antesala e nas telas. */
export const PREORDERS_SCOPE_NOTE = "Retiradas e entregas de todos os canais, de hoje em diante.";

/**
 * As seções da barra: as mesmas quatro portas dos cards da antesala, com os
 * mesmos nomes. O detalhe de uma encomenda não é seção — a tela passa
 * `current=""` e nenhuma aba acende.
 */
export const PREORDER_SECTIONS: readonly OperatorSection[] = [
  { key: "search", label: "Cliente veio buscar", icon: "lucide:search", to: "/preorders" },
  { key: "today", label: "Hoje", icon: "lucide:calendar-check", to: "/preorders/today" },
  { key: "week", label: "Semana", icon: "lucide:calendar-days", to: "/preorders/week" },
  { key: "panel", label: "Via Pedido – painel", icon: "lucide:printer", to: "/preorders/panel" },
];

// ── Intervalos ──────────────────────────────────────────────────────────────

/** Só hoje. */
export function todayRange(today: string): TicketRange {
  return { date_from: today, date_to: today };
}

/**
 * A semana da grade: sete dias a partir de hoje, deslocada de sete em sete.
 *
 * Começa HOJE, não na segunda — a mesma régua da Via Pedido – painel: a grade
 * serve para enxergar o que vem pela frente, e uma semana que começa três dias
 * atrás gasta três colunas com o que já passou.
 */
export function weekRange(today: string, offsetWeeks = 0): TicketRange {
  const start = addDays(today, offsetWeeks * 7);
  return { date_from: start, date_to: addDays(start, 6) };
}

/** Quantos dias para trás e para a frente a busca olha. */
export const SEARCH_DAYS_BACK = 7;
export const SEARCH_DAYS_AHEAD = 30;

/**
 * A janela da busca "Cliente veio buscar".
 *
 * Para trás também: quem chega hoje para buscar a encomenda de ontem existe, e
 * é justamente o caso em que o balcão mais precisa achar o pedido.
 */
export function searchRange(today: string): TicketRange {
  return { date_from: addDays(today, -SEARCH_DAYS_BACK), date_to: addDays(today, SEARCH_DAYS_AHEAD) };
}

/** Busca com uma letra casa com meia agenda: a tela pede mais antes de perguntar. */
export const SEARCH_MIN_CHARS = 2;

export function canSearch(query: string): boolean {
  return query.trim().length >= SEARCH_MIN_CHARS;
}

// ── Contagens e frases ──────────────────────────────────────────────────────

/** "nenhuma encomenda" / "1 encomenda" / "3 encomendas" — zero é frase, não "0". */
export function preorderCountLabel(count: number): string {
  if (count <= 0) return "nenhuma encomenda";
  return count === 1 ? "1 encomenda" : `${count} encomendas`;
}

/** Quantas encomendas caem HOJE numa lista que começa hoje. */
export function todayCount(days: readonly PreorderDay[]): number {
  return days.find((day) => day.is_today)?.orders_count ?? 0;
}

/** O resumo do topo de uma lista: "3 encomendas · R$ 120,00". Vazio sem nada. */
export function listSummary(count: number, totalDisplay: string): string {
  return count > 0 ? `${preorderCountLabel(count)} · ${totalDisplay}` : "";
}

/** O cabeçalho da coluna da grade: "sáb 27/09". Hoje diz que é hoje. */
export function dayColumnTitle(day: PreorderDay): string {
  return day.is_today ? `Hoje ${day.day_display}` : `${day.weekday_display} ${day.day_display}`;
}

/** O intervalo em palavras: "Hoje até sex, 02/10". */
export function rangeTitle(range: TicketRange, today: string): string {
  const from = dateLabel(range.date_from, today);
  if (range.date_from === range.date_to) return from;
  return `${from} até ${dateLabel(range.date_to, today)}`;
}

/**
 * A linha de dinheiro do card — o total e o que falta, sem somar grandezas.
 *
 * O saldo é o que decide o gesto no balcão ("cobro ou só entrego?"), então ele
 * vem primeiro quando existe. "Não sei" nunca vira "pago": sem leitura do
 * pagamento, a linha manda conferir.
 */
export function moneyLine(card: Pick<PreorderCard, "balance_q" | "balance_display" | "total_q" | "total_display" | "situation">): string {
  if (card.balance_q === null) return `${card.total_display} · pagamento a conferir`;
  if (card.balance_q > 0) {
    return card.balance_q >= card.total_q
      ? `${card.total_display} a receber`
      : `Falta receber ${card.balance_display} de ${card.total_display}`;
  }
  if (card.situation === "on_account") return `${card.total_display} na conta da casa`;
  return `${card.total_display} pago`;
}

export type SituationTone = "warning" | "success" | "info" | "neutral";

/**
 * O tom do selo de situação. Amarelo só para o que pede gesto do balcão
 * (cobrar, conferir); pronto é o que se entrega; o resto é neutro — amarelo
 * por escolha da casa é ruído.
 */
export function situationTone(situation: PreorderSituation): SituationTone {
  if (situation === "to_pay" || situation === "check_payment") return "warning";
  if (situation === "ready") return "success";
  if (situation === "out_for_delivery") return "info";
  return "neutral";
}

export interface WindowGroup {
  key: string;
  label: string;
  orders: PreorderCard[];
}

/** O rótulo do grupo sem janela combinada. Nunca uma linha em branco. */
export const NO_WINDOW_LABEL = "Sem horário combinado";

/**
 * As encomendas de um dia agrupadas pela janela, na ordem em que o servidor as
 * entregou (a ordem do painel: janela, e o sem-janela no fim do dia).
 */
export function groupByWindow(orders: readonly PreorderCard[]): WindowGroup[] {
  const groups: WindowGroup[] = [];
  for (const order of orders) {
    const label = order.window_label || NO_WINDOW_LABEL;
    const last = groups[groups.length - 1];
    if (last && last.label === label) {
      last.orders.push(order);
      continue;
    }
    groups.push({ key: `${order.window_start || "none"}:${label}`, label, orders: [order] });
  }
  return groups;
}

/** Os cards de uma lista por dia, achatados — para o resultado da busca. */
export function flattenDays(days: readonly PreorderDay[]): PreorderCard[] {
  return days.flatMap((day) => day.orders);
}

/** O que a busca diz quando não acha — e o que fazer em seguida. */
export function searchEmptyMessage(query: string, range: TicketRange, today: string): string {
  return `Nenhuma encomenda com “${query.trim()}” de ${dateLabel(range.date_from, today)} até ${dateLabel(range.date_to, today)}. `
    + "Confira a grafia ou procure pelo telefone.";
}

/** A linha de quem é: nome, e o número do iFood quando o ref não o carrega. */
export function customerLine(card: Pick<PreorderCard, "customer_name" | "ref" | "channel_display_id">): string {
  const name = card.customer_name || card.ref;
  return card.channel_display_id ? `${name} · iFood #${card.channel_display_id}` : name;
}
