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
import type { SessionTile } from "~/presentation/cash";
import type {
  PreorderCard,
  PreorderDay,
  PreorderListResponse,
  PreorderPaymentState,
  PreorderSituation,
} from "~/types/preorders";

import { addDays, type TicketRange } from "./orderTickets";
import { dateLabel } from "./schedule";

/** A frase que diz o corte da seção. Uma só, na antesala e nas telas. */
export const PREORDERS_SCOPE_NOTE = "Retiradas e entregas de todos os canais, de hoje em diante.";

/**
 * As seções da barra: as mesmas quatro portas dos cards da casa (`/preorders`),
 * com os mesmos nomes. "Cliente veio buscar" É a casa — o campo de busca vem
 * primeiro nela, focado. O detalhe de uma encomenda não é seção — a tela passa
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

// ── O dinheiro: o que falta receber × o que já está pago ────────────────────
//
// Prioridade do dono (26/09): o balcão controla o que falta receber. O filtro
// lê o ESTADO DO DINHEIRO (`payment_state`, do servidor), nunca a situação — uma
// encomenda "Pronto" pode ter saldo, e é o saldo que decide "cobro ou só
// entrego?".
//
//   Todas · A receber · Pagas — sempre, com a contagem em cada um.
//   Na conta da casa          — só quando existe: não é "a receber" (cobrar de
//                               novo seria cobrar duas vezes) nem "paga".
//   A conferir                — não é chip: o Payman não respondeu, e "não sei"
//                               nunca entra calado num dos dois lados. Ganha um
//                               aviso próprio, com o gesto de mostrar só elas.

export type PaymentFilter = "all" | PreorderPaymentState;

export type PaymentCounts = Record<PaymentFilter, number>;

export function paymentCounts(cards: readonly Pick<PreorderCard, "payment_state">[]): PaymentCounts {
  const counts: PaymentCounts = { all: cards.length, to_receive: 0, paid: 0, on_account: 0, check: 0 };
  for (const card of cards) counts[card.payment_state] += 1;
  return counts;
}

export function filterByPayment<T extends Pick<PreorderCard, "payment_state">>(cards: readonly T[], filter: PaymentFilter): T[] {
  return filter === "all" ? [...cards] : cards.filter((card) => card.payment_state === filter);
}

/** Os dias com as encomendas filtradas. A conta de cada dia continua a do dia inteiro. */
export function filterDaysByPayment(days: readonly PreorderDay[], filter: PaymentFilter): PreorderDay[] {
  if (filter === "all") return [...days];
  return days.map((day) => ({ ...day, orders: filterByPayment(day.orders, filter) }));
}

export interface PaymentFilterChip {
  key: PaymentFilter;
  label: string;
  count: number;
}

export function paymentFilterChips(counts: PaymentCounts): PaymentFilterChip[] {
  const chips: PaymentFilterChip[] = [
    { key: "all", label: "Todas", count: counts.all },
    { key: "to_receive", label: "A receber", count: counts.to_receive },
    { key: "paid", label: "Pagas", count: counts.paid },
  ];
  if (counts.on_account > 0) chips.push({ key: "on_account", label: "Na conta da casa", count: counts.on_account });
  return chips;
}

const PAYMENT_FILTERS: readonly PaymentFilter[] = ["all", "to_receive", "paid", "on_account", "check"];

/** O filtro que veio na URL (`?pay=to_receive`); qualquer outra coisa é "Todas". */
export function parsePaymentFilter(raw: unknown): PaymentFilter {
  const value = Array.isArray(raw) ? raw[0] : raw;
  return PAYMENT_FILTERS.includes(value as PaymentFilter) ? (value as PaymentFilter) : "all";
}

/**
 * O aviso das encomendas cujo pagamento o sistema não conseguiu ler. Vazio
 * quando não há nenhuma — o aviso só existe quando pede gesto.
 */
export function checkPaymentNotice(count: number): string {
  if (count <= 0) return "";
  const subject = count === 1 ? "1 encomenda está" : `${count} encomendas estão`;
  return `${subject} com o pagamento a conferir: o sistema não conseguiu ler o que foi pago, `
    + "e elas não entram em A receber nem em Pagas.";
}

/** O que a lista diz quando o filtro esvaziou o período. */
export function filterEmptyMessage(filter: PaymentFilter): string {
  if (filter === "to_receive") return "Nenhuma encomenda a receber neste período.";
  if (filter === "paid") return "Nenhuma encomenda paga neste período.";
  if (filter === "on_account") return "Nenhuma encomenda na conta da casa neste período.";
  if (filter === "check") return "Nenhuma encomenda com pagamento a conferir neste período.";
  return "";
}

/** "A receber: R$ 62,00" — ou, sem nada, a frase inteira. Zero não é código. */
export function toReceiveLine(toReceiveQ: number, toReceiveDisplay: string): string {
  return toReceiveQ > 0 ? `A receber: ${toReceiveDisplay}` : "Nada a receber";
}

/** O dinheiro de uma coluna da grade, só quando há o que receber. */
export function dayToReceiveLine(day: Pick<PreorderDay, "to_receive_q" | "to_receive_display">): string {
  return day.to_receive_q > 0 ? `A receber ${day.to_receive_display}` : "";
}

/** O saldo pede destaque na linha: é o que o balcão cobra. */
export function balanceStandsOut(card: Pick<PreorderCard, "payment_state" | "balance_q">): boolean {
  return card.payment_state === "to_receive" && (card.balance_q ?? 0) > 0;
}

// ── A casa e o selo da barra lateral ────────────────────────────────────────

/**
 * As encomendas de HOJE que ainda não foram entregues — o selo do item
 * "Encomendas" da barra lateral e do card Hoje. "Saiu para entrega" ainda não é
 * entregue: conta.
 */
export function todayPendingCount(days: readonly PreorderDay[]): number {
  const today = days.find((day) => day.is_today);
  return today ? today.orders.filter((card) => card.situation !== "delivered").length : 0;
}

/** O selo: número só quando há o que entregar; zero não é selo. */
export function railBadge(list: Pick<PreorderListResponse, "days"> | null | undefined): string | undefined {
  const count = list ? todayPendingCount(list.days) : 0;
  return count > 0 ? String(count) : undefined;
}

/** O nome acessível do item da barra, com o selo por extenso. */
export function railAriaLabel(badge: string | undefined): string {
  if (!badge) return "Encomendas";
  return badge === "1" ? "Encomendas — 1 para entregar hoje" : `Encomendas — ${badge} para entregar hoje`;
}

export interface PreorderHomeSummary {
  todayPending: number;
  weekCount: number;
  todayToReceiveQ: number;
  todayToReceiveDisplay: string;
  weekToReceiveQ: number;
  weekToReceiveDisplay: string;
  checkCount: number;
}

/** O resumo da casa, lido da semana que começa hoje (a resposta padrão da rota). */
export function homeSummary(list: PreorderListResponse): PreorderHomeSummary {
  const today = list.days.find((day) => day.is_today);
  return {
    todayPending: todayPendingCount(list.days),
    weekCount: list.count,
    todayToReceiveQ: today?.to_receive_q ?? 0,
    todayToReceiveDisplay: today?.to_receive_display ?? "",
    weekToReceiveQ: list.to_receive_q,
    weekToReceiveDisplay: list.to_receive_display,
    checkCount: paymentCounts(flattenDays(list.days)).check,
  };
}

/**
 * Os três cards da casa depois do campo "Cliente veio buscar": Hoje, Semana e
 * a Via Pedido – painel. ⚠️ Zero não vira selo: sem encomenda, o selo some e a
 * descrição diz, por extenso, que não há nada.
 */
export function preorderHomeTiles(summary: PreorderHomeSummary): SessionTile[] {
  const { todayPending, weekCount } = summary;
  return [
    {
      key: "preorders:today",
      icon: "lucide:calendar-check",
      label: "Hoje",
      description: todayPending > 0
        ? `${preorderCountLabel(todayPending)} para entregar, por horário`
        : "Nenhuma encomenda para entregar hoje",
      disabled: false,
      tone: "default",
      badge: todayPending > 0 ? String(todayPending) : undefined,
    },
    {
      key: "preorders:week",
      icon: "lucide:calendar-days",
      label: "Semana",
      description: weekCount > 0 ? "Hoje e os próximos 6 dias, com a conta de cada dia" : "Nenhuma encomenda nos próximos 7 dias",
      disabled: false,
      tone: "default",
      badge: weekCount > 0 ? String(weekCount) : undefined,
    },
    {
      key: "preorders:panel",
      icon: "lucide:printer",
      label: "Via Pedido – painel",
      description: "Imprimir as encomendas de um período para o painel de parede",
      disabled: false,
      tone: "default",
    },
  ];
}

/** Para onde cada card da casa leva. */
export const PREORDER_TILE_ROUTES: Record<string, string> = {
  "preorders:today": "/preorders/today",
  "preorders:week": "/preorders/week",
  "preorders:panel": "/preorders/panel",
};
