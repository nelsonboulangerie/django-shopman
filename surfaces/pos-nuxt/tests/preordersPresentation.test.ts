// A tela única das Encomendas: o estado na URL, a semana de segunda a domingo,
// os filtros combináveis, o "Imprimir N vias" do visível, a busca e as frases
// que o balcão lê. O corte é do servidor; aqui se prende o FORMATO.
import { describe, expect, it } from "vitest";

import {
  DEFAULT_MODE,
  NO_FILTERS,
  NO_WINDOW_LABEL,
  balanceStandsOut,
  canSearch,
  checkCount,
  checkPaymentNotice,
  compactMoneyLine,
  customerLine,
  dayColumnTitle,
  dayToReceiveLine,
  filterChips,
  filterDays,
  filterEmptyMessage,
  flattenDays,
  groupByWindow,
  hasFilters,
  isoWeek,
  listSummary,
  matchesFilters,
  modeSections,
  mondayOf,
  moneyLine,
  parsePaymentFilter,
  parseView,
  periodEmptyMessage,
  periodParams,
  periodTitle,
  preorderCountLabel,
  printPlan,
  railAriaLabel,
  railBadge,
  searchCompletedHeading,
  searchEmptyMessage,
  searchLimitNote,
  searchOpenEmptyMessage,
  searchOpenHeading,
  showsToday,
  singleResult,
  situationTone,
  stepDate,
  stepLabels,
  toReceiveLine,
  todayPendingCount,
  viewPath,
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
  return { mode: "week", date: HOJE, ...NO_FILTERS, q: "", completed: false, ...partial };
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

  it("as abas Dia | Semana levam a data e os filtros, e deixam a busca", () => {
    const sections = modeSections(view({ date: "2026-10-02", print: "pending", q: "ana" }), HOJE);
    expect(sections.map((s) => [s.label, s.to])).toEqual([
      ["Dia", "/preorders?mode=day&date=2026-10-02&print=pending"],
      ["Semana", "/preorders?date=2026-10-02&print=pending"],
    ]);
  });

  it("sem estado (o detalhe), as abas levam a hoje", () => {
    expect(modeSections(null, HOJE).map((s) => s.to)).toEqual(["/preorders?mode=day", "/preorders"]);
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
    expect(periodParams({ mode: "day", date: "2026-10-01" })).toEqual({ date_from: "2026-10-01", date_to: "2026-10-01" });
    expect(periodParams({ mode: "week", date: "2026-10-01" })).toEqual({ week: "2026-W40" });
  });

  it("‹ › anda um dia no Dia e uma semana na Semana", () => {
    expect(stepDate({ mode: "day", date: HOJE }, 1)).toBe("2026-09-29");
    expect(stepDate({ mode: "day", date: HOJE }, -1)).toBe("2026-09-27");
    expect(stepDate({ mode: "week", date: HOJE }, 1)).toBe("2026-10-05");
    expect(stepDate({ mode: "week", date: HOJE }, -1)).toBe("2026-09-21");
    expect(stepLabels("week")).toEqual({ prev: "Semana anterior", next: "Próxima semana" });
  });

  it("'Voltar para hoje' só quando o período não contém hoje", () => {
    expect(showsToday({ mode: "day", date: HOJE }, HOJE)).toBe(true);
    expect(showsToday({ mode: "day", date: "2026-09-29" }, HOJE)).toBe(false);
    expect(showsToday({ mode: "week", date: "2026-10-04" }, HOJE)).toBe(true);
    expect(showsToday({ mode: "week", date: "2026-10-05" }, HOJE)).toBe(false);
  });

  it("o período em palavras", () => {
    expect(periodTitle({ mode: "day", date: HOJE }, HOJE)).toBe("Hoje, 28/09");
    expect(periodTitle({ mode: "day", date: "2026-09-29" }, HOJE)).toBe("Amanhã, 29/09");
    expect(periodTitle({ mode: "day", date: "2026-10-01" }, HOJE)).toBe("qui, 01/10");
    expect(periodTitle({ mode: "week", date: "2026-10-01" }, HOJE)).toBe("Esta semana: 28/09 a 04/10");
    expect(periodTitle({ mode: "week", date: "2026-10-07" }, HOJE)).toBe("Semana de 05/10 a 11/10");
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

  it("a coluna de hoje diz que é hoje", () => {
    expect(dayColumnTitle(day())).toBe("Hoje 28/09");
    expect(dayColumnTitle(day({ is_today: false, weekday_display: "ter", day_display: "29/09" }))).toBe("ter 29/09");
  });

  it("período vazio por extenso", () => {
    expect(periodEmptyMessage("day")).toBe("Nenhuma encomenda neste dia.");
    expect(periodEmptyMessage("week")).toBe("Nenhuma encomenda nesta semana.");
  });

  it("A receber: valor por extenso, e zero é frase", () => {
    expect(toReceiveLine(6200, "R$ 62,00")).toBe("A receber: R$ 62,00");
    expect(toReceiveLine(0, "R$ 0,00")).toBe("Nada a receber");
    expect(dayToReceiveLine(day({ to_receive_q: 1200, to_receive_display: "R$ 12,00" }))).toBe("A receber R$ 12,00");
    expect(dayToReceiveLine(day())).toBe("");
  });
});

describe("a linha de dinheiro — saldo primeiro, 'não sei' nunca vira 'pago'", () => {
  it("nada pago: o total inteiro a receber", () => {
    expect(moneyLine(card())).toBe("R$ 36,00 a receber");
  });

  it("parte paga: quanto falta e de quanto", () => {
    expect(moneyLine(card({ balance_q: 1100, balance_display: "R$ 11,00" }))).toBe("Falta receber R$ 11,00 de R$ 36,00");
  });

  it("pago · na conta da casa · a conferir", () => {
    expect(moneyLine(card({ balance_q: 0, situation: "paid" }))).toBe("R$ 36,00 pago");
    expect(moneyLine(card({ balance_q: 0, situation: "on_account" }))).toBe("R$ 36,00 na conta da casa");
    expect(moneyLine(card({ balance_q: null, situation: "check_payment" }))).toBe("R$ 36,00 · pagamento a conferir");
  });

  it("no card estreito da grade: o saldo em destaque, ou só a palavra", () => {
    expect(compactMoneyLine(card())).toBe("R$ 36,00 a receber");
    expect(compactMoneyLine(card({ balance_q: 0, payment_state: "paid" }))).toBe("pago");
    expect(compactMoneyLine(card({ balance_q: 0, payment_state: "on_account" }))).toBe("na conta da casa");
    expect(compactMoneyLine(card({ balance_q: null, payment_state: "check" }))).toBe("conferir pagamento");
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

  it("o filtro que esvazia a lista diz o que não há", () => {
    expect(filterEmptyMessage("day")).toBe("Nenhuma encomenda com estes filtros neste dia.");
    expect(filterEmptyMessage("week")).toBe("Nenhuma encomenda com estes filtros nesta semana.");
  });
});

// ── Imprimir N vias ─────────────────────────────────────────────────────────

describe("Imprimir N vias — o que está visível", () => {
  it("o período da resposta e só os refs que os filtros deixaram, na ordem da tela", () => {
    const list = { date_from: "2026-09-28", date_to: "2026-10-04" } as PreorderListResponse;
    const visible = filterDays([
      day({ orders: [card({ ref: "A" }), card({ ref: "B", ticket_printed: true })] }),
      day({ date: "2026-09-29", is_today: false, orders: [card({ ref: "C" })] }),
    ], { ...NO_FILTERS, print: "pending" });
    expect(printPlan(list, visible)).toEqual({ date_from: "2026-09-28", date_to: "2026-10-04", refs: ["A", "C"] });
    expect(flattenDays(visible).length).toBe(2);
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
    expect(railAriaLabel("2")).toBe("Encomendas — 2 para entregar hoje");
  });

  it("zero não é selo; sem resposta (403, carregando) também não", () => {
    expect(railBadge(list([card({ situation: "delivered" })]))).toBeUndefined();
    expect(railBadge(null)).toBeUndefined();
    expect(railAriaLabel(undefined)).toBe("Encomendas");
  });
});
