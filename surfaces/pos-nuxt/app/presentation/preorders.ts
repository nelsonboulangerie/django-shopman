// ENCOMENDAS — a seção do PDV que lê o que a casa prometeu (ENCOMENDAS-PDV-PLAN).
//
// Uma tela só (redesenho aprovado pelo dono, 28/09/2026): a busca "Cliente veio
// buscar" sempre no topo, os modos Dia | Semana com ‹ › e a data, os filtros em
// chips combináveis e o "Imprimir N vias" do que está visível. O estado inteiro
// (modo, data, filtros, busca) mora na URL, para a volta do detalhe cair no
// mesmo lugar e para o kiosk guardar o favorito.
//
// O corte é do servidor (`backstage/projections/preorders.py`): todo pedido com
// recebimento — retirada ou entrega —, de qualquer canal, pela data combinada.
// Aqui mora só o FORMATO: o estado da tela, a aritmética da semana, os filtros e
// as frases que o balcão lê.
//
// ⚠️ "Encomenda" no resto da suíte é só data futura (o *Agendados* do Gestor).
// A seção diverge por decisão do dono e DIZ o seu corte na tela
// (`PREORDERS_SCOPE_NOTE`), para ninguém procurar a retirada de hoje no Gestor e
// achar que ela sumiu.

import type { OperatorSection } from "../../../operator-kit/app/presentation/appBar";
import type {
  PreorderCard,
  PreorderDay,
  PreorderListResponse,
  PreorderPaymentState,
  PreorderSearchResponse,
  PreorderSituation,
} from "~/types/preorders";

import { addDays } from "./orderTickets";
import { dateLabel, parseLocalDate, shortDate } from "./schedule";

/** A frase que diz o corte da seção. */
export const PREORDERS_SCOPE_NOTE = "Retiradas e entregas de todos os canais, pela data combinada.";

// ── O estado da tela (a URL) ────────────────────────────────────────────────

export type PreordersMode = "day" | "week";
export type FulfillmentFilter = "all" | "pickup" | "delivery";
export type PrintFilter = "all" | "pending";
export type PaymentFilter = "all" | PreorderPaymentState;

export interface PreorderFilters {
  fulfillment: FulfillmentFilter;
  pay: PaymentFilter;
  print: PrintFilter;
}

export interface PreordersView extends PreorderFilters {
  mode: PreordersMode;
  /** O dia escolhido. No modo Semana, a semana é a que contém este dia. */
  date: string;
  /** A busca "Cliente veio buscar" (vazia = a tela mostra o período). */
  q: string;
  /** "Incluir concluídas" — só vale para a busca. */
  completed: boolean;
}

/**
 * A tela abre na SEMANA de hoje: o panorama da semana é o centro da seção
 * (redesenho de 28/09). "O que sai hoje?" é o dia destacado na grade, a um
 * toque do modo Dia.
 */
export const DEFAULT_MODE: PreordersMode = "week";

export const NO_FILTERS: PreorderFilters = { fulfillment: "all", pay: "all", print: "all" };

const PAYMENT_FILTERS: readonly PaymentFilter[] = ["all", "to_receive", "paid", "on_account", "check"];
const FULFILLMENT_FILTERS: readonly FulfillmentFilter[] = ["all", "pickup", "delivery"];
const PRINT_FILTERS: readonly PrintFilter[] = ["all", "pending"];

function first(raw: unknown): string {
  const value = Array.isArray(raw) ? raw[0] : raw;
  return typeof value === "string" ? value : "";
}

function oneOf<T extends string>(raw: unknown, allowed: readonly T[], fallback: T): T {
  const value = first(raw);
  return allowed.includes(value as T) ? (value as T) : fallback;
}

/** O filtro de dinheiro que veio na URL (`?pay=to_receive`); qualquer outra coisa é "Todas". */
export function parsePaymentFilter(raw: unknown): PaymentFilter {
  return oneOf(raw, PAYMENT_FILTERS, "all");
}

/** A URL → o estado da tela. Valor ilegível cai no padrão, nunca em erro. */
export function parseView(query: Record<string, unknown>, today: string): PreordersView {
  const date = first(query.date);
  return {
    mode: oneOf(query.mode, ["day", "week"] as const, DEFAULT_MODE),
    date: parseLocalDate(date) ? date : today,
    fulfillment: oneOf(query.fulfillment, FULFILLMENT_FILTERS, "all"),
    pay: parsePaymentFilter(query.pay),
    print: oneOf(query.print, PRINT_FILTERS, "all"),
    q: first(query.q),
    completed: first(query.completed) === "1",
  };
}

/** O estado → a URL, sem o que é padrão (o favorito fica curto e legível). */
export function viewQuery(view: PreordersView, today: string): Record<string, string> {
  const query: Record<string, string> = {};
  if (view.mode !== DEFAULT_MODE) query.mode = view.mode;
  if (view.date !== today) query.date = view.date;
  if (view.fulfillment !== "all") query.fulfillment = view.fulfillment;
  if (view.pay !== "all") query.pay = view.pay;
  if (view.print !== "all") query.print = view.print;
  if (view.q.trim()) query.q = view.q.trim();
  if (view.completed) query.completed = "1";
  return query;
}

/** O endereço de um estado: `/preorders?mode=day&date=…`. */
export function viewPath(view: PreordersView, today: string): string {
  const params = new URLSearchParams(viewQuery(view, today)).toString();
  return params ? `/preorders?${params}` : "/preorders";
}

/**
 * As abas Dia | Semana da barra da seção, levando o resto do estado junto
 * (a data e os filtros): trocar de modo não perde o que o operador escolheu.
 * Sem estado (o detalhe), as abas levam ao dia e à semana de hoje.
 */
export function modeSections(view: PreordersView | null, today: string): OperatorSection[] {
  const base = view ?? { mode: DEFAULT_MODE, date: today, ...NO_FILTERS, q: "", completed: false };
  return [
    { key: "day", label: "Dia", icon: "lucide:calendar-check", to: viewPath({ ...base, mode: "day", q: "", completed: false }, today) },
    { key: "week", label: "Semana", icon: "lucide:calendar-days", to: viewPath({ ...base, mode: "week", q: "", completed: false }, today) },
  ];
}

// ── A semana (de segunda a domingo) ─────────────────────────────────────────

/** A segunda-feira da semana de `iso` (decisão do dono: a semana começa na segunda). */
export function mondayOf(iso: string): string {
  const date = parseLocalDate(iso);
  if (!date) return iso;
  const back = (date.getDay() + 6) % 7; // domingo = 6 dias depois da segunda
  return addDays(iso, -back);
}

/**
 * A semana ISO de `iso`: "2026-W40". É o que o servidor lê (`?week=`), e a
 * semana ISO começa na segunda — o mesmo corte da tela.
 */
export function isoWeek(iso: string): string {
  const thursday = parseLocalDate(addDays(mondayOf(iso), 3));
  if (!thursday) return "";
  // O ano da semana é o da sua quinta-feira; a semana 1 é a que tem a primeira quinta.
  const year = thursday.getFullYear();
  const jan1 = new Date(year, 0, 1);
  const dayOfYear = Math.round((thursday.getTime() - jan1.getTime()) / 86_400_000);
  const week = Math.floor(dayOfYear / 7) + 1;
  return `${year}-W${String(week).padStart(2, "0")}`;
}

/** O que a tela pede ao servidor para o período do estado. */
export function periodParams(view: Pick<PreordersView, "mode" | "date">): Record<string, string> {
  return view.mode === "day"
    ? { date_from: view.date, date_to: view.date }
    : { week: isoWeek(view.date) };
}

/** ‹ › — um dia no modo Dia, uma semana no modo Semana. */
export function stepDate(view: Pick<PreordersView, "mode" | "date">, direction: -1 | 1): string {
  return addDays(view.date, direction * (view.mode === "day" ? 1 : 7));
}

/** O período mostrado contém hoje? Sem isso, a tela oferece "Voltar para hoje". */
export function showsToday(view: Pick<PreordersView, "mode" | "date">, today: string): boolean {
  if (view.mode === "day") return view.date === today;
  return mondayOf(view.date) === mondayOf(today);
}

/**
 * O período em palavras. Dia: "Hoje, 28/09" · "Amanhã, 29/09" · "qua, 30/09".
 * Semana: "Esta semana: 28/09 a 04/10" · "Semana de 05/10 a 11/10".
 */
export function periodTitle(view: Pick<PreordersView, "mode" | "date">, today: string): string {
  if (view.mode === "day") {
    const label = dateLabel(view.date, today);
    return label === "Hoje" || label === "Amanhã" ? `${label}, ${shortDate(view.date)}` : label;
  }
  const monday = mondayOf(view.date);
  const span = `${shortDate(monday)} a ${shortDate(addDays(monday, 6))}`;
  return showsToday(view, today) ? `Esta semana: ${span}` : `Semana de ${span}`;
}

/** Os rótulos de ‹ ›, por extenso para o leitor de tela. */
export function stepLabels(mode: PreordersMode): { prev: string; next: string } {
  return mode === "day"
    ? { prev: "Dia anterior", next: "Próximo dia" }
    : { prev: "Semana anterior", next: "Próxima semana" };
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

/** O cabeçalho da coluna da grade: "seg 28/09". Hoje diz que é hoje. */
export function dayColumnTitle(day: PreorderDay): string {
  return day.is_today ? `Hoje ${day.day_display}` : `${day.weekday_display} ${day.day_display}`;
}

/** O período vazio, por extenso. */
export function periodEmptyMessage(mode: PreordersMode): string {
  return mode === "day" ? "Nenhuma encomenda neste dia." : "Nenhuma encomenda nesta semana.";
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

/**
 * O dinheiro do card estreito da grade: o saldo quando há ("R$ 36,00 a
 * receber"), senão só a palavra ("pago", "na conta da casa", "conferir
 * pagamento"). O total do dia está no topo da coluna.
 */
export function compactMoneyLine(card: Pick<PreorderCard, "balance_q" | "balance_display" | "situation" | "payment_state">): string {
  if (card.balance_q === null || card.payment_state === "check") return "conferir pagamento";
  if (card.balance_q > 0) return `${card.balance_display} a receber`;
  if (card.payment_state === "on_account") return "na conta da casa";
  return "pago";
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

/** Os cards de uma lista por dia, achatados. */
export function flattenDays(days: readonly PreorderDay[]): PreorderCard[] {
  return days.flatMap((day) => day.orders);
}

/** A linha de quem é: nome, e o número do iFood quando o ref não o carrega. */
export function customerLine(card: Pick<PreorderCard, "customer_name" | "ref" | "channel_display_id">): string {
  const name = card.customer_name || card.ref;
  return card.channel_display_id ? `${name} · iFood #${card.channel_display_id}` : name;
}

// ── Os filtros (chips combináveis, com contagem) ────────────────────────────
//
// Prioridade do dono (26/09): o balcão controla o que falta receber. O filtro
// de dinheiro lê o ESTADO DO DINHEIRO (`payment_state`, do servidor), nunca a
// situação — uma encomenda "Pronto" pode ter saldo, e é o saldo que decide
// "cobro ou só entrego?".
//
//   Recebimento  Todas · Retiradas · Entregas
//   Pagamento    Todas · A receber · Pagas — e "Na conta da casa" só quando
//                existe: não é "a receber" (cobrar de novo seria cobrar duas
//                vezes) nem "paga". "A conferir" não é chip: o Payman não
//                respondeu, e "não sei" nunca entra calado num dos dois lados.
//                Ganha aviso próprio, com o gesto de mostrar só elas.
//   Via Pedido   Todas · Falta imprimir
//
// A contagem de cada chip é a do que ELE mostraria com os OUTROS filtros como
// estão: "A receber 3" com "Entregas" ligado quer dizer 3 entregas a receber.

type FilterCard = Pick<PreorderCard, "fulfillment_type" | "payment_state" | "ticket_printed">;

function matchesFulfillment(card: FilterCard, filter: FulfillmentFilter): boolean {
  return filter === "all" || (filter === "delivery" ? card.fulfillment_type === "delivery" : card.fulfillment_type !== "delivery");
}

function matchesPay(card: FilterCard, filter: PaymentFilter): boolean {
  return filter === "all" || card.payment_state === filter;
}

function matchesPrint(card: FilterCard, filter: PrintFilter): boolean {
  return filter === "all" || !card.ticket_printed;
}

export function matchesFilters(card: FilterCard, filters: PreorderFilters): boolean {
  return matchesFulfillment(card, filters.fulfillment) && matchesPay(card, filters.pay) && matchesPrint(card, filters.print);
}

export function hasFilters(filters: PreorderFilters): boolean {
  return filters.fulfillment !== "all" || filters.pay !== "all" || filters.print !== "all";
}

/** Os dias com as encomendas filtradas. A conta de cada dia continua a do dia inteiro. */
export function filterDays(days: readonly PreorderDay[], filters: PreorderFilters): PreorderDay[] {
  if (!hasFilters(filters)) return [...days];
  return days.map((day) => ({ ...day, orders: day.orders.filter((card) => matchesFilters(card, filters)) }));
}

export interface FilterChip<K extends string> {
  key: K;
  label: string;
  count: number;
}

export interface FilterChips {
  fulfillment: FilterChip<FulfillmentFilter>[];
  pay: FilterChip<PaymentFilter>[];
  print: FilterChip<PrintFilter>[];
}

export function filterChips(cards: readonly FilterCard[], filters: PreorderFilters): FilterChips {
  const byPay = cards.filter((c) => matchesFulfillment(c, filters.fulfillment) && matchesPrint(c, filters.print));
  const byFulfillment = cards.filter((c) => matchesPay(c, filters.pay) && matchesPrint(c, filters.print));
  const byPrint = cards.filter((c) => matchesFulfillment(c, filters.fulfillment) && matchesPay(c, filters.pay));
  const count = <T>(list: readonly T[], test: (item: T) => boolean) => list.filter(test).length;

  const pay: FilterChip<PaymentFilter>[] = [
    { key: "all", label: "Todas", count: byPay.length },
    { key: "to_receive", label: "A receber", count: count(byPay, (c) => c.payment_state === "to_receive") },
    { key: "paid", label: "Pagas", count: count(byPay, (c) => c.payment_state === "paid") },
  ];
  const onAccount = count(byPay, (c) => c.payment_state === "on_account");
  if (onAccount > 0 || filters.pay === "on_account") pay.push({ key: "on_account", label: "Na conta da casa", count: onAccount });

  return {
    fulfillment: [
      { key: "all", label: "Todas", count: byFulfillment.length },
      { key: "pickup", label: "Retiradas", count: count(byFulfillment, (c) => c.fulfillment_type !== "delivery") },
      { key: "delivery", label: "Entregas", count: count(byFulfillment, (c) => c.fulfillment_type === "delivery") },
    ],
    pay,
    print: [
      { key: "all", label: "Todas", count: byPrint.length },
      { key: "pending", label: "Falta imprimir", count: count(byPrint, (c) => !c.ticket_printed) },
    ],
  };
}

/** Quantas estão com o pagamento a conferir, com os outros filtros como estão. */
export function checkCount(cards: readonly FilterCard[], filters: PreorderFilters): number {
  return cards.filter((c) => c.payment_state === "check" && matchesFulfillment(c, filters.fulfillment) && matchesPrint(c, filters.print)).length;
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

/** O que a lista diz quando os filtros esvaziaram o período. */
export function filterEmptyMessage(mode: PreordersMode): string {
  return mode === "day"
    ? "Nenhuma encomenda com estes filtros neste dia."
    : "Nenhuma encomenda com estes filtros nesta semana.";
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

// ── Imprimir N vias (o que está visível) ────────────────────────────────────

export interface PrintPlan {
  date_from: string;
  date_to: string;
  /** Os refs visíveis, na ordem da tela (que é a do painel). */
  refs: string[];
}

/**
 * O lote do botão "Imprimir N vias": o período que a tela mostra e só os
 * pedidos que os filtros deixaram visíveis. O servidor recorta o período por
 * esses refs e nunca alarga (`order_ticket.select_refs`).
 */
export function printPlan(list: Pick<PreorderListResponse, "date_from" | "date_to">, visibleDays: readonly PreorderDay[]): PrintPlan {
  return { date_from: list.date_from, date_to: list.date_to, refs: flattenDays(visibleDays).map((card) => card.ref) };
}

// ── Cliente veio buscar ─────────────────────────────────────────────────────

export const SEARCH_PLACEHOLDER = "Cliente veio buscar? Nome, telefone, CPF, endereço ou número";

/** Busca com uma letra casa com meia agenda: a tela pede mais antes de perguntar. */
export const SEARCH_MIN_CHARS = 2;

export function canSearch(query: string): boolean {
  return query.trim().length >= SEARCH_MIN_CHARS;
}

/** A busca em aberto não achou nada: a frase e, ao lado, a oferta das concluídas. */
export function searchOpenEmptyMessage(query: string): string {
  return `Nenhuma encomenda em aberto para “${query.trim()}”.`;
}

/** Nem em aberto nem nas concluídas. */
export function searchEmptyMessage(query: string, completedDays: number): string {
  return `Nenhuma encomenda para “${query.trim()}”, nem em aberto nem nas concluídas dos últimos ${completedDays} dias. `
    + "Confira a grafia ou procure pelo telefone.";
}

export function searchOpenHeading(count: number): string {
  return count === 1 ? "1 encomenda em aberto" : `${count} encomendas em aberto`;
}

export function searchCompletedHeading(count: number, completedDays: number): string {
  if (count <= 0) return `Nenhuma concluída nos últimos ${completedDays} dias`;
  return `${count === 1 ? "1 concluída" : `${count} concluídas`} nos últimos ${completedDays} dias`;
}

/** "Mostrando as 50 primeiras de 73." quando o servidor cortou; senão nada. */
export function searchLimitNote(shown: number, total: number): string {
  return total > shown ? `Mostrando as ${shown} primeiras de ${total}. Refine a busca para achar as outras.` : "";
}

/** Um resultado só (em aberto e concluídas somadas): Enter abre o detalhe. */
export function singleResult(search: Pick<PreorderSearchResponse, "open" | "completed" | "open_count" | "completed_count"> | null | undefined): PreorderCard | null {
  if (!search || search.open_count + search.completed_count !== 1) return null;
  return search.open[0] ?? search.completed[0] ?? null;
}

// ── O selo da barra lateral ─────────────────────────────────────────────────

/**
 * As encomendas de HOJE que ainda não foram entregues — o selo do item
 * "Encomendas" da barra lateral. "Saiu para entrega" ainda não é entregue: conta.
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
  return badge === "1" ? "Encomendas: 1 para entregar hoje" : `Encomendas: ${badge} para entregar hoje`;
}
