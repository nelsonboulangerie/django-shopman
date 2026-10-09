// A tela única das Encomendas: o estado na URL, a semana de segunda a domingo,
// os filtros combináveis, o lote das vias que faltam, a busca e as frases
// que o balcão lê. O corte é do servidor; aqui se prende o FORMATO.
import { describe, expect, it } from "vitest";

import {
  DEFAULT_MODE,
  LAYOUT_OPTIONS,
  canDropOn,
  canMoveCard,
  moveConfirmLabel,
  moveDescription,
  moveQuestion,
  moveTargets,
  parseLayout,
  shortcutBlocks,
  NO_FILTERS,
  NO_WINDOW_LABEL,
  balanceStandsOut,
  barDimensions,
  canSearch,
  checkCount,
  checkPaymentNotice,
  customerLine,
  dayColumnTitle,
  dayToReceiveLine,
  filterChips,
  filterDays,
  filterDimensions,
  fromActiveFilters,
  fromBarFilters,
  filterEmptyMessage,
  flattenDays,
  groupByWindow,
  hasFilters,
  isoWeek,
  itemsCountLabel,
  listSummary,
  matchesFilters,
  mondayOf,
  moneyLine,
  moneyPieces,
  parsePaymentFilter,
  parseView,
  periodEmptyMessage,
  periodIsToday,
  periodParams,
  periodSelectionOf,
  periodSummaryLabel,
  preorderCountLabel,
  printPlan,
  railBadge,
  rowDetailLine,
  rowShowsSituation,
  rowWindow,
  searchCompletedHeading,
  searchEmptyMessage,
  toActiveFilters,
  searchLimitNote,
  searchOpenEmptyMessage,
  searchOpenHeading,
  shortcutChips,
  singleResult,
  situationTone,
  toBarFilters,
  toReceiveLine,
  todayFacts,
  todayOf,
  todayPendingCount,
  toggleShortcut,
  viewPath,
  viewOfPeriod,
  viewQuery,
  type PreordersView,
} from "../app/presentation/preorders";
import type { PreorderCard, PreorderDay, PreorderListResponse, PreorderSearchResponse } from "../app/types/preorders";

const HOJE = "2026-09-28"; // segunda

function card(partial: Partial<PreorderCard> = {}): PreorderCard {
  return {
    ref: "NB-1",
    channel_display_id: "",
    customer_name: "Ana",
    channel_ref: "web",
    channel_label: "Loja online",
    fulfillment_type: "pickup",
    fulfillment_label: "Retirada",
    commitment_date: HOJE,
    commitment_date_display: "hoje",
    window_label: "9h às 10h",
    window_start: "09:00",
    status: "accepted",
    situation: "to_pay",
    situation_label: "A pagar",
    payment_state: "to_receive",
    total_q: 3600,
    total_display: "R$ 36,00",
    balance_q: 3600,
    balance_display: "R$ 36,00",
    items_summary: "2x Pão",
    items_count: 2,
    ticket_printed: false,
    ...partial,
  };
}

function day(partial: Partial<PreorderDay> = {}): PreorderDay {
  return {
    date: HOJE,
    date_display: "hoje",
    weekday_display: "seg",
    day_display: "28/09",
    is_today: true,
    orders_count: 0,
    to_receive_q: 0,
    to_receive_display: "R$ 0,00",
    total_q: 0,
    total_display: "R$ 0,00",
    orders: [],
    ...partial,
  };
}

function view(partial: Partial<PreordersView> = {}): PreordersView {
  return { mode: "week", date: HOJE, to: "", ...NO_FILTERS, q: "", completed: false, ...partial };
}

// ── O estado na URL ─────────────────────────────────────────────────────────

describe("o estado da tela mora na URL", () => {
  it("sem query: a semana de hoje, sem filtro e sem busca", () => {
    expect(DEFAULT_MODE).toBe("week");
    expect(parseView({}, HOJE)).toEqual(view());
  });

  it("lê modo, data, filtros, busca e 'incluir concluídas'", () => {
    expect(parseView({
      mode: "day", date: "2026-10-03", fulfillment: "delivery", pay: "to_receive", print: "pending",
      q: "ana", completed: "1",
    }, HOJE)).toEqual(view({
      mode: "day", date: "2026-10-03", fulfillment: "delivery", pay: "to_receive", print: "pending",
      q: "ana", completed: true,
    }));
  });

  it("valor ilegível cai no padrão, nunca em erro", () => {
    expect(parseView({ mode: "mes", date: "ontem", fulfillment: "drone", pay: "x", print: "sim" }, HOJE)).toEqual(view());
    expect(parsePaymentFilter(["paid"])).toBe("paid");
  });

  it("a URL leva só o que não é padrão (o favorito fica curto)", () => {
    expect(viewQuery(view(), HOJE)).toEqual({});
    expect(viewQuery(view({ mode: "day", date: "2026-10-01", print: "pending", q: " Ana " }), HOJE))
      .toEqual({ mode: "day", date: "2026-10-01", print: "pending", q: "Ana" });
    expect(viewPath(view({ pay: "to_receive" }), HOJE)).toBe("/preorders?pay=to_receive");
    expect(viewPath(view(), HOJE)).toBe("/preorders");
  });

  it("ida e volta: o que a URL escreve, a URL lê", () => {
    const state = view({ mode: "day", date: "2026-10-02", fulfillment: "pickup", pay: "paid", completed: true, q: "rua" });
    expect(parseView(viewQuery(state, HOJE), HOJE)).toEqual(state);
  });
});

// ── A semana ────────────────────────────────────────────────────────────────

describe("a semana começa na SEGUNDA (decisão do dono, 28/09)", () => {
  it("a segunda de qualquer dia, inclusive do domingo", () => {
    expect(mondayOf("2026-09-28")).toBe("2026-09-28");
    expect(mondayOf("2026-10-01")).toBe("2026-09-28");
    expect(mondayOf("2026-10-04")).toBe("2026-09-28"); // domingo é o FIM da semana
    expect(mondayOf("2026-10-05")).toBe("2026-10-05");
  });

  it("a semana ISO que o servidor lê, inclusive na virada do ano", () => {
    expect(isoWeek("2026-09-28")).toBe("2026-W40");
    expect(isoWeek("2026-10-04")).toBe("2026-W40");
    expect(isoWeek("2027-01-01")).toBe("2026-W53"); // sexta: ainda a última de 2026
    expect(isoWeek("2027-01-04")).toBe("2027-W01");
    expect(isoWeek("2025-12-29")).toBe("2026-W01");
  });

  it("o período pedido ao servidor: o dia pelas datas, a semana pela semana ISO", () => {
    expect(periodParams({ mode: "day", date: "2026-10-01", to: "" })).toEqual({ date_from: "2026-10-01", date_to: "2026-10-01" });
    expect(periodParams({ mode: "week", date: "2026-10-01", to: "" })).toEqual({ week: "2026-W40" });
  });
});

// ── O Período universal do kit ──────────────────────────────────────────────

describe("o Período das Encomendas olha para a frente (e para trás, quando pedido)", () => {
  it("o servidor recebe as datas de cada modo, dentro do teto", () => {
    expect(periodParams({ mode: "next7d", date: HOJE, to: "" })).toEqual({ date_from: HOJE, date_to: "2026-10-04" });
    expect(periodParams({ mode: "next28d", date: "2026-10-20", to: "" })).toEqual({ date_from: "2026-10-20", date_to: "2026-11-16" });
    expect(periodParams({ mode: "7d", date: HOJE, to: "" })).toEqual({ date_from: "2026-09-22", date_to: HOJE });
    expect(periodParams({ mode: "month", date: "2026-10-15", to: "" })).toEqual({ date_from: "2026-10-01", date_to: "2026-10-31" });
    expect(periodParams({ mode: "custom", date: "2026-10-01", to: "2026-10-20", })).toEqual({ date_from: "2026-10-01", date_to: "2026-10-20" });
  });

  it("a URL guarda o modo, a data e, no personalizado, o fim", () => {
    const custom = view({ mode: "custom", date: "2026-10-01", to: "2026-10-20" });
    expect(viewQuery(custom, HOJE)).toEqual({ mode: "custom", date: "2026-10-01", to: "2026-10-20" });
    expect(parseView(viewQuery(custom, HOJE), HOJE)).toEqual(custom);
    const ahead = view({ mode: "next7d" });
    expect(viewQuery(ahead, HOJE)).toEqual({ mode: "next7d" });
    expect(parseView(viewQuery(ahead, HOJE), HOJE)).toEqual(ahead);
    // Personalizado sem o fim não é intervalo.
    expect(parseView({ mode: "custom", date: "2026-10-01" }, HOJE)).toEqual(view({ date: "2026-10-01" }));
    // O fim só vale no personalizado.
    expect(parseView({ mode: "day", to: "2026-10-20" }, HOJE)).toEqual(view({ mode: "day" }));
  });

  it("a ponte com o controle vai e volta, e hoje é âncora vazia", () => {
    expect(periodSelectionOf(view(), HOJE)).toEqual({ preset: "week", from: "", to: "" });
    expect(periodSelectionOf(view({ date: "2026-10-01" }), HOJE)).toEqual({ preset: "week", from: "", to: "" });
    expect(periodSelectionOf(view({ date: "2026-10-07" }), HOJE)).toEqual({ preset: "week", from: "2026-10-07", to: "" });
    expect(periodSelectionOf(view({ mode: "next7d" }), HOJE)).toEqual({ preset: "next7d", from: "", to: "" });
    expect(periodSelectionOf(view({ mode: "7d", date: "2026-09-20" }), HOJE)).toEqual({ preset: "7d", from: "", to: "2026-09-20" });
    for (const state of [
      view({ mode: "day", date: "2026-10-02" }),
      view({ mode: "week", date: "2026-10-07" }),
      view({ mode: "month", date: "2026-11-03" }),
      view({ mode: "next14d", date: "2026-10-12" }),
      view({ mode: "28d", date: "2026-09-01" }),
      view({ mode: "custom", date: "2026-10-01", to: "2026-10-20" }),
    ]) {
      const back = viewOfPeriod(periodSelectionOf(state, HOJE), HOJE);
      expect({ ...state, ...back }).toEqual(state);
    }
  });

  it("as frases dizem o período, qualquer que seja", () => {
    expect(periodEmptyMessage("month")).toBe("Nenhuma encomenda neste mês.");
    expect(periodEmptyMessage("next7d")).toBe("Nenhuma encomenda neste período.");
    expect(filterEmptyMessage("custom")).toBe("Nenhuma encomenda com estes filtros neste período.");
    expect(periodSummaryLabel("month")).toBe("No mês");
    expect(periodSummaryLabel("next28d")).toBe("No período");
  });
});

// ── Contagens e frases ──────────────────────────────────────────────────────

describe("contagens — zero é frase, nunca '0'", () => {
  it("encomenda no singular e no plural", () => {
    expect(preorderCountLabel(0)).toBe("nenhuma encomenda");
    expect(preorderCountLabel(1)).toBe("1 encomenda");
    expect(preorderCountLabel(4)).toBe("4 encomendas");
  });

  it("o resumo some quando não há nada", () => {
    expect(listSummary(0, "R$ 0,00")).toBe("");
    expect(listSummary(3, "R$ 120,00")).toBe("3 encomendas · R$ 120,00");
  });

  it("a coluna de hoje diz que é hoje SEM perder o dia da semana", () => {
    expect(dayColumnTitle(day())).toBe("Hoje, seg 28/09");
    expect(dayColumnTitle(day({ is_today: false, weekday_display: "ter", day_display: "29/09" }))).toBe("Ter 29/09");
  });

  it("período vazio por extenso", () => {
    expect(periodEmptyMessage("day")).toBe("Nenhuma encomenda neste dia.");
    expect(periodEmptyMessage("week")).toBe("Nenhuma encomenda nesta semana.");
  });

  it("A receber: a mesma frase no período e no dia, e zero é frase", () => {
    expect(toReceiveLine(6200, "R$ 62,00")).toBe("A receber R$ 62,00");
    expect(toReceiveLine(0, "R$ 0,00")).toBe("Nada a receber");
    expect(dayToReceiveLine(day({ to_receive_q: 1200, to_receive_display: "R$ 12,00" }))).toBe("A receber R$ 12,00");
    expect(dayToReceiveLine(day())).toBe("");
  });
});

describe("a linha de dinheiro — saldo primeiro, 'não sei' nunca vira 'pago'", () => {
  it("nada pago: o total inteiro a receber", () => {
    expect(moneyLine(card())).toBe("A receber R$ 36,00");
  });

  it("parte paga: quanto falta e de quanto", () => {
    expect(moneyLine(card({ balance_q: 1100, balance_display: "R$ 11,00" }))).toBe("A receber R$ 11,00 de R$ 36,00");
  });

  it("pago · na conta da casa · a conferir", () => {
    expect(moneyLine(card({ balance_q: 0, situation: "paid" }))).toBe("R$ 36,00 pago");
    expect(moneyLine(card({ balance_q: 0, situation: "on_account" }))).toBe("R$ 36,00 na conta da casa");
    expect(moneyLine(card({ balance_q: null, situation: "check_payment" }))).toBe("R$ 36,00 · pagamento a conferir");
  });

  it("o saldo ganha destaque só quando é para cobrar", () => {
    expect(balanceStandsOut(card())).toBe(true);
    expect(balanceStandsOut(card({ payment_state: "paid", balance_q: 0 }))).toBe(false);
    expect(balanceStandsOut(card({ payment_state: "check", balance_q: null }))).toBe(false);
  });
});

describe("o tom da situação — amarelo só para o que pede gesto", () => {
  it("cobrar e conferir pedem gesto; pronto é verde; o resto é neutro", () => {
    expect(situationTone("to_pay")).toBe("warning");
    expect(situationTone("check_payment")).toBe("warning");
    expect(situationTone("ready")).toBe("success");
    expect(situationTone("out_for_delivery")).toBe("info");
    expect(situationTone("paid")).toBe("neutral");
    expect(situationTone("delivered")).toBe("neutral");
  });
});

describe("agrupamento por janela (o modo Dia)", () => {
  it("preserva a ordem do servidor e junta a mesma janela", () => {
    const groups = groupByWindow([
      card({ ref: "A" }),
      card({ ref: "B" }),
      card({ ref: "C", window_label: "14h às 15h", window_start: "14:00" }),
      card({ ref: "D", window_label: "", window_start: "" }),
    ]);
    expect(groups.map((g) => [g.label, g.orders.map((o) => o.ref)])).toEqual([
      ["9h às 10h", ["A", "B"]],
      ["14h às 15h", ["C"]],
      [NO_WINDOW_LABEL, ["D"]],
    ]);
  });

  it("o número do iFood aparece só quando o ref não o carrega", () => {
    expect(customerLine(card())).toBe("Ana");
    expect(customerLine(card({ channel_display_id: "4994" }))).toBe("Ana · iFood #4994");
    expect(customerLine(card({ customer_name: "" }))).toBe("NB-1");
  });
});

// ── Os filtros ──────────────────────────────────────────────────────────────

describe("filtros combináveis, com a contagem de cada chip", () => {
  const cards = [
    card({ ref: "A", payment_state: "to_receive" }),
    card({ ref: "B", payment_state: "to_receive", fulfillment_type: "delivery", ticket_printed: true }),
    card({ ref: "C", payment_state: "paid", balance_q: 0, fulfillment_type: "delivery" }),
    card({ ref: "D", payment_state: "on_account", balance_q: 0, ticket_printed: true }),
    card({ ref: "E", payment_state: "check", balance_q: null }),
  ];
  const refs = (list: PreorderCard[]) => list.map((c) => c.ref);

  it("sem filtro, tudo; e os três eixos combinam", () => {
    expect(hasFilters(NO_FILTERS)).toBe(false);
    expect(refs(cards.filter((c) => matchesFilters(c, NO_FILTERS)))).toEqual(["A", "B", "C", "D", "E"]);
    expect(refs(cards.filter((c) => matchesFilters(c, { fulfillment: "delivery", pay: "to_receive", print: "all" })))).toEqual(["B"]);
    expect(refs(cards.filter((c) => matchesFilters(c, { fulfillment: "pickup", pay: "all", print: "pending" })))).toEqual(["A", "E"]);
  });

  it("a contagem de cada chip é a do que ele mostraria com os OUTROS filtros como estão", () => {
    const chips = filterChips(cards, { fulfillment: "delivery", pay: "all", print: "all" });
    expect(chips.pay.map((c) => [c.label, c.count])).toEqual([["Todas", 2], ["A receber", 1], ["Pagas", 1]]);
    expect(chips.fulfillment.map((c) => [c.label, c.count])).toEqual([["Todas", 5], ["Retiradas", 3], ["Entregas", 2]]);
    expect(chips.print.map((c) => [c.label, c.count])).toEqual([["Todas", 2], ["Falta imprimir", 1]]);
  });

  it("conta da casa NUNCA é paga nem a receber; ganha chip próprio só quando existe", () => {
    expect(filterChips(cards, NO_FILTERS).pay.map((c) => [c.label, c.count])).toEqual([
      ["Todas", 5], ["A receber", 2], ["Pagas", 1], ["Na conta da casa", 1],
    ]);
    const semConta = filterChips(cards.filter((c) => c.payment_state !== "on_account"), NO_FILTERS);
    expect(semConta.pay.map((c) => c.label)).toEqual(["Todas", "A receber", "Pagas"]);
  });

  it("pagamento a conferir não é chip — é aviso próprio, que some quando não há", () => {
    expect(filterChips(cards, NO_FILTERS).pay.some((c) => c.key === "check")).toBe(false);
    expect(checkCount(cards, NO_FILTERS)).toBe(1);
    expect(checkCount(cards, { ...NO_FILTERS, fulfillment: "delivery" })).toBe(0);
    expect(checkPaymentNotice(0)).toBe("");
    expect(checkPaymentNotice(2)).toContain("não entram em A receber nem em Pagas");
  });

  it("filtra os dias, e a conta de cada dia continua a do dia inteiro", () => {
    const days = [day({ orders: cards, orders_count: 5, total_q: 18000, total_display: "R$ 180,00" })];
    const filtered = filterDays(days, { ...NO_FILTERS, print: "pending" });
    expect(refs(filtered[0]!.orders)).toEqual(["A", "C", "E"]);
    expect(filtered[0]!.total_display).toBe("R$ 180,00");
  });

  it("na barra de uma linha: sem 'Todas' (filtro ausente É todas), com a mesma contagem", () => {
    const dimensions = filterDimensions(cards, { fulfillment: "delivery", pay: "all", print: "all" });
    expect(dimensions.map((d) => [d.id, d.label, d.type])).toEqual([
      ["fulfillment", "Recebimento", "single-select"],
      ["pay", "Pagamento", "single-select"],
      ["print", "Via Pedido", "single-select"],
    ]);
    expect(dimensions[0]!.options.map((o) => [o.label, o.count])).toEqual([["Retiradas", 3], ["Entregas", 2]]);
    expect(dimensions[1]!.options.map((o) => [o.label, o.count])).toEqual([["A receber", 1], ["Pagas", 1]]);
    expect(dimensions[2]!.options.map((o) => [o.label, o.count])).toEqual([["Falta imprimir", 1]]);
  });

  it("'A conferir' só vira opção quando já está escolhida, para o chip dizer o que filtra", () => {
    expect(filterDimensions(cards, NO_FILTERS)[1]!.options.some((o) => o.value === "check")).toBe(false);
    const checking = filterDimensions(cards, { ...NO_FILTERS, pay: "check" })[1]!;
    expect(checking.options.at(-1)).toEqual({ value: "check", label: "A conferir", count: 1 });
  });

  it("traduz o estado da tela e o da barra, nos dois sentidos, sem perder nada", () => {
    expect(toActiveFilters(NO_FILTERS)).toEqual({});
    const view = { fulfillment: "pickup", pay: "to_receive", print: "pending" } as const;
    expect(toActiveFilters(view)).toEqual({ fulfillment: ["pickup"], pay: ["to_receive"], print: ["pending"] });
    expect(fromActiveFilters(toActiveFilters(view))).toEqual(view);
    expect(fromActiveFilters({})).toEqual(NO_FILTERS);
    expect(fromActiveFilters({ pay: ["inventado"] })).toEqual(NO_FILTERS);
  });

  it("o filtro que esvazia a lista diz o que não há", () => {
    expect(filterEmptyMessage("day")).toBe("Nenhuma encomenda com estes filtros neste dia.");
    expect(filterEmptyMessage("week")).toBe("Nenhuma encomenda com estes filtros nesta semana.");
  });
});

// ── O lote: as vias que faltam ──────────────────────────────────────────────

describe("o lote: as vias que faltam, do que está visível", () => {
  it("o período da resposta e só os refs que os filtros deixaram, na ordem da tela", () => {
    const list = { date_from: "2026-09-28", date_to: "2026-10-04" } as PreorderListResponse;
    const visible = filterDays([
      day({ orders: [card({ ref: "A" }), card({ ref: "B", ticket_printed: true })] }),
      day({ date: "2026-09-29", is_today: false, orders: [card({ ref: "C" })] }),
    ], { ...NO_FILTERS, print: "pending" });
    expect(printPlan(list, visible)).toEqual({ date_from: "2026-09-28", date_to: "2026-10-04", refs: ["A", "C"] });
    expect(flattenDays(visible).length).toBe(2);
  });

  it("P2: sem recorte, a via que já saiu fica de fora do lote (reimprimir é no detalhe)", () => {
    const list = { date_from: "2026-09-28", date_to: "2026-10-04" } as PreorderListResponse;
    const visible = filterDays([
      day({ orders: [card({ ref: "A" }), card({ ref: "B", ticket_printed: true })] }),
      day({ date: "2026-09-29", is_today: false, orders: [card({ ref: "C" })] }),
    ], NO_FILTERS);
    expect(flattenDays(visible).length).toBe(3);
    expect(printPlan(list, visible).refs).toEqual(["A", "C"]);
  });
});

// ── Cliente veio buscar ─────────────────────────────────────────────────────

describe("a busca", () => {
  function search(partial: Partial<PreorderSearchResponse> = {}): PreorderSearchResponse {
    return {
      ok: true, query: "ana", today: HOJE, include_completed: false, completed_days: 30,
      open_count: 0, open: [], completed_count: 0, completed: [], ...partial,
    };
  }

  it("pede pelo menos dois caracteres", () => {
    expect(canSearch("a")).toBe(false);
    expect(canSearch(" an ")).toBe(true);
  });

  it("em aberto vazio oferece as concluídas; nada em lugar nenhum diz o próximo passo", () => {
    expect(searchOpenEmptyMessage(" Ana ")).toBe("Nenhuma encomenda em aberto para “Ana”.");
    expect(searchEmptyMessage("Ana", 30)).toContain("nem nas concluídas dos últimos 30 dias");
    expect(searchEmptyMessage("Ana", 30)).toContain("procure pelo telefone");
  });

  it("os cabeçalhos das duas seções", () => {
    expect(searchOpenHeading(1)).toBe("1 encomenda em aberto");
    expect(searchOpenHeading(3)).toBe("3 encomendas em aberto");
    expect(searchCompletedHeading(0, 30)).toBe("Nenhuma concluída nos últimos 30 dias");
    expect(searchCompletedHeading(2, 30)).toBe("2 concluídas nos últimos 30 dias");
  });

  it("o teto do servidor é dito, com o que fazer", () => {
    expect(searchLimitNote(50, 50)).toBe("");
    expect(searchLimitNote(50, 73)).toBe("Mostrando as 50 primeiras de 73. Refine a busca para achar as outras.");
  });

  it("um resultado só (somando as duas seções) é o que o Enter abre", () => {
    expect(singleResult(search({ open_count: 1, open: [card({ ref: "A" })] }))?.ref).toBe("A");
    expect(singleResult(search({ include_completed: true, completed_count: 1, completed: [card({ ref: "Z" })] }))?.ref).toBe("Z");
    expect(singleResult(search({ open_count: 2, open: [card(), card({ ref: "B" })] }))).toBeNull();
    expect(singleResult(null)).toBeNull();
  });
});

// ── O selo da barra lateral ─────────────────────────────────────────────────

describe("o selo da barra lateral", () => {
  function list(orders: PreorderCard[]): PreorderListResponse {
    return {
      ok: true, date_from: HOJE, date_to: "2026-10-04", today: HOJE, count: orders.length,
      total_q: 0, total_display: "R$ 0,00", to_receive_q: 0, to_receive_display: "R$ 0,00", max_batch: 200,
      days: [day({ orders }), day({ is_today: false, date: "2026-09-29", orders: [card({ ref: "AMANHA" })] })],
    };
  }

  it("conta as de HOJE ainda não entregues ('Saiu para entrega' conta)", () => {
    const today = [card({ ref: "1" }), card({ ref: "2", situation: "out_for_delivery" }), card({ ref: "3", situation: "delivered" })];
    expect(todayPendingCount(list(today).days)).toBe(2);
    expect(railBadge(list(today))).toBe("2");
  });

  it("zero não é selo; sem resposta (403, carregando) também não", () => {
    expect(railBadge(list([card({ situation: "delivered" })]))).toBeUndefined();
    expect(railBadge(null)).toBeUndefined();
  });
});

// ── Os recortes de um toque (P1 do dono, 02/10) ─────────────────────────────

describe("os recortes de todo dia viram botões de um toque", () => {
  const cards = [
    card({ ref: "A" }),
    card({ ref: "B", fulfillment_type: "delivery", payment_state: "paid", balance_q: 0, ticket_printed: true }),
    card({ ref: "C", payment_state: "on_account", balance_q: 0 }),
  ];

  it("A receber, Sem Via Pedido, Retiradas, Entregas, com a contagem do que cada um mostraria", () => {
    expect(shortcutChips(cards, NO_FILTERS).map((c) => [c.label, c.count, c.pressed])).toEqual([
      ["A receber", 1, false],
      ["Sem Via Pedido", 2, false],
      ["Retiradas", 2, false],
      ["Entregas", 1, false],
    ]);
  });

  it("botão que não mostraria nada some (zero não é código), a menos que esteja apertado", () => {
    const deliveries = { ...NO_FILTERS, fulfillment: "delivery" as const };
    const chips = shortcutChips(cards, deliveries);
    // Entre as entregas, nenhuma a receber e nenhuma sem Via: os dois botões somem.
    expect(chips.map((c) => [c.label, c.pressed])).toEqual([["Retiradas", false], ["Entregas", true]]);
  });

  it("apertar liga o recorte; apertar de novo volta a 'Todas' naquela dimensão", () => {
    const on = toggleShortcut(NO_FILTERS, { dimension: "pay", value: "to_receive" });
    expect(on).toEqual({ ...NO_FILTERS, pay: "to_receive" });
    expect(toggleShortcut(on, { dimension: "pay", value: "to_receive" })).toEqual(NO_FILTERS);
    // Retiradas e Entregas são a mesma dimensão: uma troca a outra.
    const pickup = toggleShortcut(NO_FILTERS, { dimension: "fulfillment", value: "pickup" });
    expect(toggleShortcut(pickup, { dimension: "fulfillment", value: "delivery" }).fulfillment).toBe("delivery");
  });

  it("o 'Filtrar' fica para o resto: nem opção nem chip do que já tem botão", () => {
    const dims = barDimensions(cards, NO_FILTERS);
    expect(dims.map((d) => [d.id, d.options.map((o) => o.value)])).toEqual([["pay", ["paid", "on_account"]]]);
    expect(toBarFilters({ fulfillment: "delivery", pay: "to_receive", print: "pending" })).toEqual({});
    expect(toBarFilters({ ...NO_FILTERS, pay: "paid" })).toEqual({ pay: ["paid"] });
  });

  it("o que a barra devolve não apaga o botão apertado de outra dimensão", () => {
    const current = { fulfillment: "delivery" as const, pay: "paid" as const, print: "pending" as const };
    // X do chip "Pagamento: Pagas": só o Pagamento volta a "Todas".
    expect(fromBarFilters(current, {})).toEqual({ fulfillment: "delivery", pay: "all", print: "pending" });
    // Escolher "Na conta da casa" no Filtrar troca o Pagamento, e o resto fica.
    expect(fromBarFilters(current, { pay: ["on_account"] })).toEqual({ fulfillment: "delivery", pay: "on_account", print: "pending" });
    // Com "A receber" apertado, escolher "Pagas" no Filtrar troca o recorte (mesma dimensão).
    expect(fromBarFilters({ ...NO_FILTERS, pay: "to_receive" }, { pay: ["paid"] }).pay).toBe("paid");
    expect(fromBarFilters({ ...NO_FILTERS, pay: "to_receive" }, {}).pay).toBe("to_receive");
  });
});

// ── A linha "Hoje" ──────────────────────────────────────────────────────────

describe("a linha 'Hoje': o que falta para o dia, sem leitura nova", () => {
  function list(days: PreorderDay[]): PreorderListResponse {
    return {
      ok: true, date_from: HOJE, date_to: "2026-10-04", today: HOJE, count: 0,
      total_q: 0, total_display: "R$ 0,00", to_receive_q: 0, to_receive_display: "R$ 0,00", max_batch: 200, days,
    };
  }

  it("o dia de hoje vem do período quando ele o contém; senão, da leitura do selo da barra", () => {
    const other = list([day({ is_today: false, date: "2026-10-05" })]);
    const ahead = list([day({ orders: [card()] })]);
    expect(todayOf(other, ahead)?.orders).toHaveLength(1);
    expect(todayOf(list([day({ orders: [card({ ref: "P" })] })]), ahead)?.orders[0]?.ref).toBe("P");
    expect(todayOf(other, null)).toBeNull();
    expect(todayFacts(null)).toEqual([]);
  });

  it("para entregar, a receber, Vias que faltam e, só quando há, o pagamento a conferir", () => {
    const today = day({
      to_receive_q: 3600, to_receive_display: "R$ 36,00",
      orders: [
        card({ ref: "1" }),
        card({ ref: "2", payment_state: "paid", balance_q: 0, ticket_printed: true }),
        card({ ref: "3", payment_state: "check", balance_q: null, situation: "check_payment" }),
        // A entregue já saiu: não conta nem como "para entregar" nem como Via que falta.
        card({ ref: "4", situation: "delivered", ticket_printed: false }),
      ],
    });
    expect(todayFacts(today).map((f) => [f.key, f.text, f.urgent])).toEqual([
      ["leaving", "3 para entregar", false],
      ["to_receive", "A receber R$ 36,00", true],
      ["tickets", "2 sem Via Pedido", true],
      ["check", "1 com pagamento a conferir", true],
    ]);
  });

  it("zero é frase: nada a receber, todas as vias impressas, todas entregues, nenhuma encomenda", () => {
    const settled = day({ orders: [card({ payment_state: "paid", balance_q: 0, ticket_printed: true })] });
    expect(todayFacts(settled).map((f) => f.text)).toEqual(["1 para entregar", "Nada a receber", "Todas as vias impressas"]);
    expect(todayFacts(day({ orders: [card({ situation: "delivered" })] })).map((f) => f.text)).toEqual(["Todas entregues"]);
    expect(todayFacts(day()).map((f) => f.text)).toEqual(["Nenhuma encomenda"]);
  });

  it("o resumo do período sai quando o período é só hoje (repetiria a linha 'Hoje')", () => {
    expect(periodIsToday({ mode: "day", date: HOJE }, HOJE)).toBe(true);
    expect(periodIsToday({ mode: "week", date: HOJE }, HOJE)).toBe(false);
    expect(periodIsToday({ mode: "day", date: "2026-09-29" }, HOJE)).toBe(false);
    expect(periodSummaryLabel("week")).toBe("Na semana");
    expect(periodSummaryLabel("day")).toBe("No dia");
  });
});

// ── A linha da encomenda ────────────────────────────────────────────────────

describe("a linha da encomenda: uma forma só", () => {
  it("a janela primeiro; sem janela, 'A combinar'", () => {
    expect(rowWindow(card())).toBe("09:00");
    expect(rowWindow(card({ window_start: "" }))).toBe("A combinar");
  });

  it("a segunda linha: número, canal, recebimento, a data só na busca, e item é unidade", () => {
    expect(rowDetailLine(card(), false)).toBe("NB-1 · Loja online · Retirada · 2 itens");
    expect(rowDetailLine(card({ items_count: 1 }), true)).toBe("NB-1 · Loja online · Retirada · hoje · 1 item");
    expect(itemsCountLabel(3)).toBe("3 itens");
    expect(rowDetailLine(card({ items_count: 0 }), false)).toBe("NB-1 · Loja online · Retirada");
  });

  it("o valor nunca se parte entre o 'R$' e o número", () => {
    expect(moneyPieces("A receber R$ 12,00 de R$ 1.036,00")).toEqual([
      { text: "A receber ", amount: false },
      { text: "R$ 12,00", amount: true },
      { text: " de ", amount: false },
      { text: "R$ 1.036,00", amount: true },
    ]);
    expect(moneyPieces("R$ 24,00 pago").map((p) => p.text).join("")).toBe("R$ 24,00 pago");
  });

  it("o selo só quando diz o que o dinheiro não diz", () => {
    expect(rowShowsSituation("to_pay")).toBe(false);
    expect(rowShowsSituation("paid")).toBe(false);
    expect(rowShowsSituation("on_account")).toBe(false);
    expect(rowShowsSituation("check_payment")).toBe(false);
    expect(rowShowsSituation("ready")).toBe(true);
    expect(rowShowsSituation("out_for_delivery")).toBe(true);
    expect(rowShowsSituation("delivered")).toBe(true);
  });
});

describe("OBS0310-D: grade ou lista, e mudar de dia", () => {
  it("a arrumação guardada no dispositivo: só 'list' vira lista; o resto é a grade", () => {
    expect(parseLayout("list")).toBe("list");
    expect(parseLayout("grid")).toBe("grid");
    expect(parseLayout(null)).toBe("grid");
    expect(parseLayout("tabela")).toBe("grid");
    expect(LAYOUT_OPTIONS.map((option) => option.label)).toEqual(["Ver em grade", "Ver em lista"]);
  });

  it("os recortes de um toque em blocos, um por pergunta, na ordem dos botões", () => {
    const cards = [
      { fulfillment_type: "pickup", payment_state: "to_receive" as const, ticket_printed: false },
      { fulfillment_type: "delivery", payment_state: "paid" as const, ticket_printed: true },
    ];
    const blocks = shortcutBlocks(shortcutChips(cards, NO_FILTERS));
    expect(blocks.map((block) => [block.label, block.chips.map((chip) => chip.label)])).toEqual([
      ["Pagamento", ["A receber"]],
      ["Via Pedido", ["Sem Via Pedido"]],
      ["Recebimento", ["Retiradas", "Entregas"]],
    ]);
  });

  it("pega-se o que ainda pode mudar de data; o pronto, o que saiu e o entregue não", () => {
    expect(canMoveCard({ situation: "to_pay" })).toBe(true);
    expect(canMoveCard({ situation: "paid" })).toBe(true);
    expect(canMoveCard({ situation: "check_payment" })).toBe(true);
    expect(canMoveCard({ situation: "ready" })).toBe(false);
    expect(canMoveCard({ situation: "out_for_delivery" })).toBe(false);
    expect(canMoveCard({ situation: "delivered" })).toBe(false);
  });

  it("solta-se em outro dia, de hoje em diante; o próprio dia e o passado não aceitam", () => {
    const card = { commitment_date: "2026-10-05", situation: "to_pay" as const };
    expect(canDropOn("2026-10-06", card, "2026-10-03")).toBe(true);
    expect(canDropOn("2026-10-03", card, "2026-10-03")).toBe(true);
    expect(canDropOn("2026-10-05", card, "2026-10-03")).toBe(false);
    expect(canDropOn("2026-10-02", card, "2026-10-03")).toBe(false);
    expect(canDropOn("2026-10-06", { ...card, situation: "ready" }, "2026-10-03")).toBe(false);
  });

  it("o menu do card oferece os mesmos dias que o arrasto aceita", () => {
    const days = ["2026-09-28", "2026-09-29", "2026-09-30", "2026-10-01"].map((date, index) => ({
      date, is_today: index === 1, weekday_display: ["seg", "ter", "qua", "qui"][index]!, day_display: `${date.slice(8)}/${date.slice(5, 7)}`,
    }));
    const targets = moveTargets(days, { commitment_date: "2026-09-30", situation: "to_pay" }, "2026-09-29");
    expect(targets).toEqual([
      { date: "2026-09-29", label: "Hoje, ter 29/09" },
      { date: "2026-10-01", label: "Qui 01/10" },
    ]);
  });

  it("a pergunta diz quem, para quando, e que o cliente será avisado", () => {
    expect(moveQuestion("Maria", "qui, 09/10")).toBe("Mudar a encomenda de Maria para qui, 09/10?");
    expect(moveQuestion("Maria", "Amanhã")).toBe("Mudar a encomenda de Maria para amanhã?");
    expect(moveQuestion("  ", "Hoje")).toBe("Mudar a encomenda para hoje?");
    expect(moveDescription("A partir das 9h")).toBe("O cliente será avisado da nova data. O horário combinado continua: a partir das 9h.");
    expect(moveDescription("")).toBe("O cliente será avisado da nova data.");
    expect(moveConfirmLabel("qui, 09/10")).toBe("Mudar para qui, 09/10");
    expect(moveConfirmLabel("Amanhã")).toBe("Mudar para amanhã");
  });
});
