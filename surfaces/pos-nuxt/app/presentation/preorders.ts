// ENCOMENDAS — a seção do PDV que lê o que a casa prometeu (ENCOMENDAS-PDV-PLAN).
//
// Uma tela só (redesenho aprovado pelo dono, 28/09/2026): a busca "Cliente veio
// buscar" sempre no topo, o Período do kit na barra (o dia, a semana, os próximos
// dias, um intervalo; ‹ › e a data),
// a linha "Hoje", os recortes de todo dia em botões de um toque com o "Filtrar"
// do kit para o resto, e o lote das vias que faltam no que está visível. O estado inteiro
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

import type { ActiveFilters, FilterDimension } from "../../../operator-kit/app/types/filters";
import type {
  PreorderCard,
  PreorderDay,
  PreorderListResponse,
  PreorderPaymentState,
  PreorderSearchResponse,
  PreorderSituation,
} from "~/types/preorders";

import {
  CUSTOM_PERIOD,
  resolvePeriod,
  type PeriodSelection,
} from "../../../operator-kit/app/presentation/dates";

import { addDays } from "./orderTickets";
import { parseLocalDate } from "./schedule";

/** A frase que diz o corte da seção. */
export const PREORDERS_SCOPE_NOTE = "Retiradas e entregas de todos os canais, pela data combinada.";

// ── O estado da tela (a URL) ────────────────────────────────────────────────

/**
 * O que o Período das Encomendas oferece (o `presets` do controle do kit). O
 * balcão olha sobretudo para a frente: o dia, a semana, o mês, os próximos dias;
 * e, para conferir o que passou, os últimos dias e o personalizado.
 */
export const PREORDERS_PERIOD_PRESETS = ["day", "week", "month", "next7d", "next14d", "next28d", "7d", "28d"] as const;

/** O teto do intervalo que o servidor aceita (`projections.preorders.MAX_SPAN_DAYS`). */
export const PREORDERS_MAX_SPAN_DAYS = 62;

export type PreordersMode = (typeof PREORDERS_PERIOD_PRESETS)[number] | typeof CUSTOM_PERIOD;

const PREORDERS_MODES: readonly PreordersMode[] = [...PREORDERS_PERIOD_PRESETS, CUSTOM_PERIOD];
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
  /**
   * O dia escolhido. Na semana e no mês, o período é o que contém este dia; nos
   * próximos dias e no personalizado, é o primeiro dia; nos últimos dias, o último.
   */
  date: string;
  /** O último dia, só no personalizado ("" nos outros modos). */
  to: string;
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
  const to = first(query.to);
  let mode = oneOf(query.mode, PREORDERS_MODES, DEFAULT_MODE);
  // Personalizado sem a data final não é intervalo: cai no padrão.
  if (mode === CUSTOM_PERIOD && !(parseLocalDate(date) && parseLocalDate(to))) mode = DEFAULT_MODE;
  return {
    mode,
    date: parseLocalDate(date) ? date : today,
    to: mode === CUSTOM_PERIOD ? to : "",
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
  if (view.date !== today || view.mode === CUSTOM_PERIOD) query.date = view.date;
  if (view.mode === CUSTOM_PERIOD && view.to) query.to = view.to;
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

// ── A ponte com o Período do kit ────────────────────────────────────────────

/**
 * O estado da URL → a seleção do controle. A data de hoje vira âncora vazia, que
 * é como o controle sabe que o período acompanha hoje (e mostra "Voltar para
 * hoje" quando não acompanha).
 */
export function periodSelectionOf(view: Pick<PreordersView, "mode" | "date" | "to">, today: string): PeriodSelection {
  if (view.mode === CUSTOM_PERIOD) return { preset: CUSTOM_PERIOD, from: view.date, to: view.to };
  const anchor = view.date === today ? "" : view.date;
  if (view.mode === "7d" || view.mode === "28d") return { preset: view.mode, from: "", to: anchor };
  if (view.mode === "day" || view.mode.startsWith("next")) return { preset: view.mode, from: anchor, to: "" };
  // Semana e mês: hoje dentro do período é o período de hoje.
  const range = resolvePeriod({ preset: view.mode, from: view.date, to: "" }, { today });
  const containsToday = range.date_from <= today && today <= range.date_to;
  return { preset: view.mode, from: containsToday ? "" : view.date, to: "" };
}

/** A seleção do controle → o que muda na URL. */
export function viewOfPeriod(selection: PeriodSelection, today: string): Pick<PreordersView, "mode" | "date" | "to"> {
  const mode = PREORDERS_MODES.includes(selection.preset as PreordersMode)
    ? (selection.preset as PreordersMode)
    : DEFAULT_MODE;
  if (mode === CUSTOM_PERIOD) return { mode, date: selection.from, to: selection.to };
  const date = mode === "7d" || mode === "28d" ? selection.to : selection.from;
  return { mode, date: date || today, to: "" };
}

/** O que a tela pede ao servidor para o período do estado. */
export function periodParams(view: Pick<PreordersView, "mode" | "date" | "to">): Record<string, string> {
  if (view.mode === "day") return { date_from: view.date, date_to: view.date };
  if (view.mode === "week") return { week: isoWeek(view.date) };
  // O resto pelas datas: a seleção com a âncora explícita resolve sem depender de hoje.
  const range = resolvePeriod(periodSelectionOf(view, ""), { today: view.date });
  return { date_from: range.date_from, date_to: range.date_to };
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

/**
 * O cabeçalho da coluna da grade: "Ter 29/09". Hoje diz que é hoje SEM perder
 * o dia da semana: "Hoje, ter 29/09". A maiúscula é daqui, não do CSS
 * (`capitalize` faria "Hoje, Ter").
 */
export function dayColumnTitle(day: Pick<PreorderDay, "is_today" | "weekday_display" | "day_display">): string {
  const weekday = `${day.weekday_display} ${day.day_display}`.trim();
  if (day.is_today) return `Hoje, ${weekday}`;
  return weekday.charAt(0).toUpperCase() + weekday.slice(1);
}

/** O período vazio, por extenso. */
export function periodEmptyMessage(mode: PreordersMode): string {
  return `Nenhuma encomenda ${periodPhrase(mode)}.`;
}

/** "neste dia", "nesta semana", "neste mês", "neste período". */
function periodPhrase(mode: PreordersMode): string {
  if (mode === "day") return "neste dia";
  if (mode === "week") return "nesta semana";
  if (mode === "month") return "neste mês";
  return "neste período";
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
      ? toReceiveLabel(card.total_display)
      : `${toReceiveLabel(card.balance_display)} de ${card.total_display}`;
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

// ── Os filtros na barra de uma linha (a `FilterBar` do operator-kit) ────────
//
// A barra é genérica: dimensões com opções e contagem, e o estado como listas.
// "Todas" não é opção dela: filtro ausente É "Todas", e o X do chip (ou tocar
// de novo na opção escolhida) volta para lá. O estado da tela continua o de
// sempre (`PreorderFilters`, na URL); aqui só se traduz entre os dois.

const FILTER_LABELS: Record<keyof PreorderFilters, string> = {
  fulfillment: "Recebimento",
  pay: "Pagamento",
  print: "Via Pedido",
};

/** "A conferir" só vira opção quando já está escolhido (pelo aviso próprio), para o chip dizer o que filtra. */
const CHECK_OPTION_LABEL = "A conferir";

export function filterDimensions(cards: readonly FilterCard[], filters: PreorderFilters): FilterDimension[] {
  const chips = filterChips(cards, filters);
  const options = <K extends string>(list: FilterChip<K>[]) => list
    .filter((chip) => chip.key !== "all")
    .map(({ key, label, count }) => ({ value: key, label, count }));
  const pay = options(chips.pay);
  if (filters.pay === "check") pay.push({ value: "check", label: CHECK_OPTION_LABEL, count: checkCount(cards, filters) });
  return [
    { id: "fulfillment", label: FILTER_LABELS.fulfillment, type: "single-select", options: options(chips.fulfillment) },
    { id: "pay", label: FILTER_LABELS.pay, type: "single-select", options: pay },
    { id: "print", label: FILTER_LABELS.print, type: "single-select", options: options(chips.print) },
  ];
}

/** O estado da tela → o da barra (o que é "Todas" fica de fora). */
export function toActiveFilters(filters: PreorderFilters): ActiveFilters {
  const active: ActiveFilters = {};
  for (const key of Object.keys(FILTER_LABELS) as (keyof PreorderFilters)[]) {
    if (filters[key] !== "all") active[key] = [filters[key]];
  }
  return active;
}

/** O estado da barra → o da tela. Valor desconhecido cai em "Todas", nunca em erro. */
export function fromActiveFilters(active: ActiveFilters): PreorderFilters {
  return {
    fulfillment: oneOf(active.fulfillment, FULFILLMENT_FILTERS, "all"),
    pay: parsePaymentFilter(active.pay),
    print: oneOf(active.print, PRINT_FILTERS, "all"),
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
  return `Nenhuma encomenda com estes filtros ${periodPhrase(mode)}.`;
}

// ── "A receber": uma grandeza, uma apresentação ─────────────────────────────
//
// O que falta cobrar aparece em três alturas da tela (o período, o dia da grade
// e a encomenda) e diz a MESMA coisa nas três: a mesma frase ("A receber R$ X")
// e o mesmo peso (`TO_RECEIVE_CLASS`). Antes eram três escalas: "A receber:" com
// dois-pontos no topo, sem eles no dia, e "R$ X a receber" de trás para a frente
// na linha, cada uma num tamanho de letra.

/** O peso do "A receber" onde quer que ele apareça. */
export const TO_RECEIVE_CLASS = "text-sm font-semibold tabular-nums text-foreground";

/** "A receber R$ 62,00". A frase única do que falta cobrar. */
export function toReceiveLabel(display: string): string {
  return `A receber ${display}`;
}

/** O "A receber" do período; sem nada, a frase inteira. Zero não é código. */
export function toReceiveLine(toReceiveQ: number, toReceiveDisplay: string): string {
  return toReceiveQ > 0 ? toReceiveLabel(toReceiveDisplay) : "Nada a receber";
}

/** O "A receber" de um dia da grade, só quando há o que receber. */
export function dayToReceiveLine(day: Pick<PreorderDay, "to_receive_q" | "to_receive_display">): string {
  return day.to_receive_q > 0 ? toReceiveLabel(day.to_receive_display) : "";
}

/** O saldo pede destaque na linha: é o que o balcão cobra. */
export function balanceStandsOut(card: Pick<PreorderCard, "payment_state" | "balance_q">): boolean {
  return card.payment_state === "to_receive" && (card.balance_q ?? 0) > 0;
}

// ── O lote: as vias que faltam, do que está visível ─────────────────────────

export interface PrintPlan {
  date_from: string;
  date_to: string;
  /** Os refs visíveis ainda sem Via Pedido, na ordem da tela (que é a do painel). */
  refs: string[];
}

/**
 * O lote do botão "Imprimir N vias que faltam": o período que a tela mostra e,
 * dos pedidos que os filtros deixaram visíveis, só os que ainda não têm a Via
 * Pedido (P2 do dono, 02/10: o lote nunca reimprime; a via que já saiu se
 * reimprime no detalhe). O servidor recorta o período por esses refs e nunca
 * alarga (`order_ticket.select_refs`).
 */
export function printPlan(list: Pick<PreorderListResponse, "date_from" | "date_to">, visibleDays: readonly PreorderDay[]): PrintPlan {
  const refs = flattenDays(visibleDays).filter((card) => !card.ticket_printed).map((card) => card.ref);
  return { date_from: list.date_from, date_to: list.date_to, refs };
}

// ── Cliente veio buscar ─────────────────────────────────────────────────────

/**
 * O que se digita: exatamente o que a busca do servidor compara
 * (`backstage/projections/preorders._matches`). O título "Cliente veio
 * buscar?" já está ao lado; o campo não o repete.
 */
export const SEARCH_PLACEHOLDER = "Nome, telefone, CPF ou CNPJ, endereço ou número do pedido";

/** O nome do campo para o leitor de tela: o título e o que se digita, numa frase. */
export const SEARCH_LABEL = "Procurar encomenda por nome, telefone, CPF ou CNPJ, endereço ou número do pedido";

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

// ── Os recortes de um toque (decisão do dono, P1 de 02/10) ──────────────────
//
// Os recortes de todo dia do balcão saem de trás do menu de dois passos e viram
// botões de um toque: A receber, Sem Via Pedido, Retiradas, Entregas. Cada um
// liga e desliga o MESMO estado da URL que o "Filtrar" escrevia (nenhum estado
// novo). O "Filtrar" do kit fica para o resto (Pagas, Na conta da casa, e o
// "A conferir" que o aviso liga): um recorte mora num lugar só, e a barra não
// repete em chip o botão que já está apertado.

export interface Shortcut {
  /** A dimensão do estado que o botão escreve. */
  dimension: keyof PreorderFilters;
  value: string;
  label: string;
}

export const SHORTCUTS: readonly Shortcut[] = [
  { dimension: "pay", value: "to_receive", label: "A receber" },
  { dimension: "print", value: "pending", label: "Sem Via Pedido" },
  { dimension: "fulfillment", value: "pickup", label: "Retiradas" },
  { dimension: "fulfillment", value: "delivery", label: "Entregas" },
];

export interface ShortcutChip extends Shortcut {
  count: number;
  pressed: boolean;
}

function isShortcut(dimension: keyof PreorderFilters, value: string | undefined): boolean {
  return SHORTCUTS.some((shortcut) => shortcut.dimension === dimension && shortcut.value === value);
}

/**
 * Os botões de um toque, com a contagem do que cada um mostraria com os outros
 * filtros como estão (a mesma conta do "Filtrar"). Botão que não mostraria nada
 * não aparece, a menos que esteja apertado: zero não é código.
 */
export function shortcutChips(cards: readonly FilterCard[], filters: PreorderFilters): ShortcutChip[] {
  const chips = filterChips(cards, filters);
  return SHORTCUTS.map((shortcut) => {
    const options = chips[shortcut.dimension] as FilterChip<string>[];
    const count = options.find((chip) => chip.key === shortcut.value)?.count ?? 0;
    return { ...shortcut, count, pressed: filters[shortcut.dimension] === shortcut.value };
  }).filter((chip) => chip.pressed || chip.count > 0);
}

/** Apertar o botão liga o recorte; apertado, desliga (a dimensão volta a "Todas"). */
export function toggleShortcut(filters: PreorderFilters, shortcut: Pick<Shortcut, "dimension" | "value">): PreorderFilters {
  const pressed = filters[shortcut.dimension] === shortcut.value;
  return fromActiveFilters({
    ...toActiveFilters(filters),
    [shortcut.dimension]: pressed ? [] : [shortcut.value],
  });
}

/** O "Filtrar" sem o que já tem botão: só as dimensões e as opções que sobram. */
export function barDimensions(cards: readonly FilterCard[], filters: PreorderFilters): FilterDimension[] {
  return filterDimensions(cards, filters)
    .map((dimension) => ({
      ...dimension,
      options: dimension.options.filter((option) => !isShortcut(dimension.id as keyof PreorderFilters, option.value)),
    }))
    .filter((dimension) => dimension.options.length > 0);
}

/** O estado da tela → o da barra do "Filtrar", sem os recortes que moram nos botões. */
export function toBarFilters(filters: PreorderFilters): ActiveFilters {
  return Object.fromEntries(Object.entries(toActiveFilters(filters))
    .filter(([key, values]) => !isShortcut(key as keyof PreorderFilters, values[0])));
}

/**
 * O que a barra devolveu → o estado da tela. A barra só fala do que ela mostra:
 * a dimensão que ela não traz e que está num botão apertado continua como está.
 */
export function fromBarFilters(current: PreorderFilters, bar: ActiveFilters): PreorderFilters {
  const merged: ActiveFilters = {};
  for (const key of Object.keys(FILTER_LABELS) as (keyof PreorderFilters)[]) {
    const fromBar = bar[key];
    if (fromBar?.length) merged[key] = fromBar;
    else if (isShortcut(key, current[key])) merged[key] = [current[key]];
  }
  return fromActiveFilters(merged);
}

// ── A linha "Hoje" ──────────────────────────────────────────────────────────
//
// O que falta para o dia, sempre de HOJE, qualquer que seja o período na tela.
// Feita só com o que a lista já traz: o dia de hoje vem do período (quando ele
// contém hoje) ou da leitura que o selo da barra lateral já faz (hoje e os seis
// dias seguintes). Nenhuma leitura nova. Conta, não decide: saldo, Via Pedido e
// pagamento são do servidor.

/** O dia de hoje, da primeira lista que o tiver. */
export function todayOf(...lists: (Pick<PreorderListResponse, "days"> | null | undefined)[]): PreorderDay | null {
  for (const list of lists) {
    const day = list?.days.find((candidate) => candidate.is_today);
    if (day) return day;
  }
  return null;
}

export interface TodayFact {
  key: "leaving" | "to_receive" | "tickets" | "check";
  text: string;
  /** O fato pede gesto do balcão (cobrar, imprimir, conferir). */
  urgent: boolean;
}

/**
 * Os fatos de hoje, na ordem em que o balcão age: quantas faltam entregar,
 * quanto falta receber, quantas Vias Pedido faltam e, só quando há, quantas
 * estão com o pagamento a conferir. A entregue já saiu e não conta. Zero é
 * frase, nunca "0".
 */
export function todayFacts(day: PreorderDay | null): TodayFact[] {
  if (!day) return [];
  if (!day.orders.length) return [{ key: "leaving", text: "Nenhuma encomenda", urgent: false }];
  const pending = day.orders.filter((card) => card.situation !== "delivered");
  if (!pending.length) return [{ key: "leaving", text: "Todas entregues", urgent: false }];

  const tickets = pending.filter((card) => !card.ticket_printed).length;
  const check = pending.filter((card) => card.payment_state === "check").length;
  const facts: TodayFact[] = [
    { key: "leaving", text: `${pending.length} para entregar`, urgent: false },
    {
      key: "to_receive",
      text: day.to_receive_q > 0 ? toReceiveLabel(day.to_receive_display) : "Nada a receber",
      urgent: day.to_receive_q > 0,
    },
    {
      key: "tickets",
      text: tickets > 0 ? `${tickets} sem Via Pedido` : "Todas as vias impressas",
      urgent: tickets > 0,
    },
  ];
  if (check > 0) facts.push({ key: "check", text: `${check} com pagamento a conferir`, urgent: true });
  return facts;
}

/** O período na tela é só o dia de hoje: o resumo dele repetiria a linha "Hoje". */
export function periodIsToday(view: Pick<PreordersView, "mode" | "date">, today: string): boolean {
  return view.mode === "day" && view.date === today;
}

/** O rótulo do resumo do período. */
export function periodSummaryLabel(mode: PreordersMode): string {
  if (mode === "day") return "No dia";
  if (mode === "week") return "Na semana";
  if (mode === "month") return "No mês";
  return "No período";
}

// ── A linha da encomenda (uma forma só: dia, semana e busca) ────────────────

/** A janela primeiro, porque é a ordem em que o balcão trabalha. */
export function rowWindow(card: Pick<PreorderCard, "window_start">): string {
  return card.window_start || "A combinar";
}

/** "1 item" / "3 itens": item é unidade, nunca linha. */
export function itemsCountLabel(count: number): string {
  return count === 1 ? "1 item" : `${count} itens`;
}

/** A segunda linha: número, canal, recebimento, a data (na busca) e quantos itens. */
export function rowDetailLine(
  card: Pick<PreorderCard, "ref" | "channel_label" | "fulfillment_label" | "commitment_date_display" | "items_count">,
  showDate: boolean,
): string {
  const parts = [card.ref, card.channel_label, card.fulfillment_label];
  if (showDate) parts.push(card.commitment_date_display);
  if (card.items_count > 0) parts.push(itemsCountLabel(card.items_count));
  return parts.filter(Boolean).join(" · ");
}

/**
 * O selo de situação só quando diz o que o dinheiro não diz. "A pagar", "Pago",
 * "Na conta da casa" e "Conferir pagamento" já estão na linha do dinheiro;
 * "Pronto", "Saiu para entrega" e "Entregue" não estão. A régua é uma só: a linha
 * da lista e o painel do Balcão no detalhe da encomenda leem esta função.
 */
export function rowShowsSituation(situation: PreorderSituation): boolean {
  return situation === "ready" || situation === "out_for_delivery" || situation === "delivered";
}

/**
 * A frase do dinheiro em pedaços, com cada valor ("R$ 86,00") inteiro: na coluna
 * estreita a linha quebra entre as palavras, nunca entre o "R$" e o número.
 */
export function moneyPieces(text: string): { text: string; amount: boolean }[] {
  return text.split(/(R\$\s[\d.,]+)/).filter(Boolean).map((piece) => ({ text: piece, amount: /^R\$\s/.test(piece) }));
}

/** A Via Pedido que já saiu, escrita: o ícone sozinho não diz. */
export const PRINTED_LABEL = "Via impressa";
