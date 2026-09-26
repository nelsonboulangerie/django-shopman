// A seção Encomendas: os intervalos de cada tela, o agrupamento por janela e as
// frases que o balcão lê. O corte é do servidor; aqui se prende o FORMATO.
import { describe, expect, it } from "vitest";

import {
  NO_WINDOW_LABEL,
  PREORDER_SECTIONS,
  PREORDER_TILE_ROUTES,
  balanceStandsOut,
  canSearch,
  checkPaymentNotice,
  dayToReceiveLine,
  filterByPayment,
  filterEmptyMessage,
  filterDaysByPayment,
  homeSummary,
  parsePaymentFilter,
  paymentCounts,
  paymentFilterChips,
  preorderHomeTiles,
  railAriaLabel,
  railBadge,
  toReceiveLine,
  todayPendingCount,
  customerLine,
  dayColumnTitle,
  flattenDays,
  groupByWindow,
  listSummary,
  moneyLine,
  preorderCountLabel,
  rangeTitle,
  searchEmptyMessage,
  searchRange,
  situationTone,
  todayRange,
  weekRange,
} from "../app/presentation/preorders";
import type { PreorderCard, PreorderDay, PreorderListResponse } from "../app/types/preorders";

const HOJE = "2026-09-26"; // sábado

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
    ...partial,
  };
}

function day(partial: Partial<PreorderDay> = {}): PreorderDay {
  return {
    date: HOJE,
    date_display: "hoje",
    weekday_display: "sáb",
    day_display: "26/09",
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

describe("os intervalos", () => {
  it("Hoje é um dia só", () => {
    expect(todayRange(HOJE)).toEqual({ date_from: HOJE, date_to: HOJE });
  });

  it("a semana começa HOJE e tem sete dias", () => {
    expect(weekRange(HOJE)).toEqual({ date_from: HOJE, date_to: "2026-10-02" });
  });

  it("a semana anda de sete em sete, para a frente e para trás", () => {
    expect(weekRange(HOJE, 1)).toEqual({ date_from: "2026-10-03", date_to: "2026-10-09" });
    expect(weekRange(HOJE, -1)).toEqual({ date_from: "2026-09-19", date_to: "2026-09-25" });
  });

  it("a busca olha uma semana para trás — a encomenda de ontem que ninguém buscou", () => {
    expect(searchRange(HOJE)).toEqual({ date_from: "2026-09-19", date_to: "2026-10-26" });
  });

  it("a busca pede pelo menos dois caracteres", () => {
    expect(canSearch("a")).toBe(false);
    expect(canSearch(" a ")).toBe(false);
    expect(canSearch("an")).toBe(true);
  });

  it("o intervalo em palavras", () => {
    expect(rangeTitle(weekRange(HOJE), HOJE)).toBe("Hoje até sex, 02/10");
    expect(rangeTitle(todayRange(HOJE), HOJE)).toBe("Hoje");
  });
});

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
    expect(dayColumnTitle(day())).toBe("Hoje 26/09");
    expect(dayColumnTitle(day({ is_today: false, weekday_display: "dom", day_display: "27/09" }))).toBe("dom 27/09");
  });
});

describe("a linha de dinheiro — saldo primeiro, 'não sei' nunca vira 'pago'", () => {
  it("nada pago: o total inteiro a receber", () => {
    expect(moneyLine(card())).toBe("R$ 36,00 a receber");
  });

  it("parte paga: quanto falta e de quanto", () => {
    expect(moneyLine(card({ balance_q: 1100, balance_display: "R$ 11,00" }))).toBe("Falta receber R$ 11,00 de R$ 36,00");
  });

  it("pago", () => {
    expect(moneyLine(card({ balance_q: 0, balance_display: "R$ 0,00", situation: "paid" }))).toBe("R$ 36,00 pago");
  });

  it("na conta da casa não é 'pago'", () => {
    expect(moneyLine(card({ balance_q: 0, situation: "on_account" }))).toBe("R$ 36,00 na conta da casa");
  });

  it("sem leitura do pagamento a linha manda conferir", () => {
    expect(moneyLine(card({ balance_q: null, balance_display: "", situation: "check_payment" }))).toBe("R$ 36,00 · pagamento a conferir");
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

describe("agrupamento por janela", () => {
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

  it("achata os dias para o resultado da busca", () => {
    expect(flattenDays([day({ orders: [card({ ref: "A" })] }), day({ orders: [card({ ref: "B" })] })]).map((c) => c.ref))
      .toEqual(["A", "B"]);
  });
});

describe("frases", () => {
  it("a busca vazia diz o intervalo e o próximo passo", () => {
    const msg = searchEmptyMessage(" Ana ", searchRange(HOJE), HOJE);
    expect(msg).toContain("“Ana”");
    expect(msg).toContain("sáb, 19/09");
    expect(msg).toContain("procure pelo telefone");
  });

  it("o número do iFood aparece só quando o ref não o carrega", () => {
    expect(customerLine(card())).toBe("Ana");
    expect(customerLine(card({ channel_display_id: "4994" }))).toBe("Ana · iFood #4994");
    expect(customerLine(card({ customer_name: "" }))).toBe("NB-1");
  });

  it("as seções da barra são as quatro portas, com rota em inglês", () => {
    expect(PREORDER_SECTIONS.map((s) => [s.label, s.to])).toEqual([
      ["Cliente veio buscar", "/preorders"],
      ["Hoje", "/preorders/today"],
      ["Semana", "/preorders/week"],
      ["Via Pedido – painel", "/preorders/panel"],
    ]);
  });
});

// O que falta receber × o que já está pago — prioridade do dono (26/09).
describe("filtros de dinheiro — Todas · A receber · Pagas", () => {
  const cards = [
    card({ ref: "A", payment_state: "to_receive" }),
    card({ ref: "B", payment_state: "to_receive", situation: "ready", situation_label: "Pronto" }),
    card({ ref: "C", payment_state: "paid", balance_q: 0 }),
    card({ ref: "D", payment_state: "on_account", balance_q: 0 }),
    card({ ref: "E", payment_state: "check", balance_q: null }),
  ];

  it("contagem em cada filtro, pelo DINHEIRO e não pela situação ('Pronto' com saldo é a receber)", () => {
    expect(paymentCounts(cards)).toEqual({ all: 5, to_receive: 2, paid: 1, on_account: 1, check: 1 });
    expect(filterByPayment(cards, "to_receive").map((c) => c.ref)).toEqual(["A", "B"]);
    expect(filterByPayment(cards, "all").map((c) => c.ref)).toEqual(["A", "B", "C", "D", "E"]);
  });

  it("conta da casa NUNCA é paga nem a receber; ganha chip próprio só quando existe", () => {
    expect(filterByPayment(cards, "paid").map((c) => c.ref)).toEqual(["C"]);
    expect(paymentFilterChips(paymentCounts(cards)).map((c) => [c.label, c.count])).toEqual([
      ["Todas", 5], ["A receber", 2], ["Pagas", 1], ["Na conta da casa", 1],
    ]);
    const semConta = paymentFilterChips(paymentCounts(cards.filter((c) => c.payment_state !== "on_account")));
    expect(semConta.map((c) => c.label)).toEqual(["Todas", "A receber", "Pagas"]);
  });

  it("pagamento a conferir não é chip — é aviso próprio, que some quando não há", () => {
    expect(paymentFilterChips(paymentCounts(cards)).some((c) => c.key === "check")).toBe(false);
    expect(checkPaymentNotice(0)).toBe("");
    expect(checkPaymentNotice(1)).toContain("1 encomenda está com o pagamento a conferir");
    expect(checkPaymentNotice(2)).toContain("não entram em A receber nem em Pagas");
  });

  it("o filtro filtra os dias, e a conta de cada dia continua a do dia inteiro", () => {
    const days = [day({ orders: cards, orders_count: 5, total_q: 18000, total_display: "R$ 180,00" })];
    const filtered = filterDaysByPayment(days, "paid");
    expect(filtered[0]!.orders.map((c) => c.ref)).toEqual(["C"]);
    expect(filtered[0]!.total_display).toBe("R$ 180,00");
  });

  it("o filtro que esvazia a lista diz o que não há", () => {
    expect(filterEmptyMessage("to_receive")).toBe("Nenhuma encomenda a receber neste período.");
    expect(filterEmptyMessage("paid")).toBe("Nenhuma encomenda paga neste período.");
    expect(filterEmptyMessage("all")).toBe("");
  });

  it("o filtro da URL: valor conhecido vale, o resto é Todas", () => {
    expect(parsePaymentFilter("to_receive")).toBe("to_receive");
    expect(parsePaymentFilter(["paid"])).toBe("paid");
    expect(parsePaymentFilter("qualquer")).toBe("all");
    expect(parsePaymentFilter(undefined)).toBe("all");
  });

  it("A receber: valor por extenso, e zero é frase", () => {
    expect(toReceiveLine(6200, "R$ 62,00")).toBe("A receber: R$ 62,00");
    expect(toReceiveLine(0, "R$ 0,00")).toBe("Nada a receber");
    expect(dayToReceiveLine(day({ to_receive_q: 1200, to_receive_display: "R$ 12,00" }))).toBe("A receber R$ 12,00");
    expect(dayToReceiveLine(day())).toBe("");
  });

  it("o saldo ganha destaque só quando é para cobrar", () => {
    expect(balanceStandsOut(card())).toBe(true);
    expect(balanceStandsOut(card({ payment_state: "paid", balance_q: 0 }))).toBe(false);
    expect(balanceStandsOut(card({ payment_state: "check", balance_q: null }))).toBe(false);
  });
});

describe("a casa das Encomendas e o selo da barra lateral", () => {
  function list(orders: PreorderCard[], extra: Partial<PreorderListResponse> = {}): PreorderListResponse {
    return {
      ok: true, date_from: HOJE, date_to: "2026-10-02", today: HOJE, query: "",
      count: orders.length + 3, total_q: 0, total_display: "R$ 0,00",
      to_receive_q: 9900, to_receive_display: "R$ 99,00",
      days: [
        day({ orders, orders_count: orders.length, to_receive_q: 3600, to_receive_display: "R$ 36,00" }),
        day({ is_today: false, date: "2026-09-27", orders: [card({ ref: "AMANHA", payment_state: "check", balance_q: null })] }),
      ],
      ...extra,
    };
  }

  it("o selo conta as de HOJE ainda não entregues ('Saiu para entrega' conta)", () => {
    const today = [
      card({ ref: "1" }),
      card({ ref: "2", situation: "out_for_delivery" }),
      card({ ref: "3", situation: "delivered" }),
    ];
    expect(todayPendingCount(list(today).days)).toBe(2);
    expect(railBadge(list(today))).toBe("2");
    expect(railAriaLabel("2")).toBe("Encomendas — 2 para entregar hoje");
  });

  it("zero não é selo; sem resposta (403, carregando) também não", () => {
    expect(railBadge(list([card({ situation: "delivered" })]))).toBeUndefined();
    expect(railBadge(null)).toBeUndefined();
    expect(railAriaLabel(undefined)).toBe("Encomendas");
  });

  it("o resumo da casa: pendentes de hoje, a semana, o a receber de hoje e da semana, e os a conferir", () => {
    const summary = homeSummary(list([card({ ref: "1" }), card({ ref: "2", situation: "delivered" })]));
    expect(summary).toEqual({
      todayPending: 1,
      weekCount: 5,
      todayToReceiveQ: 3600,
      todayToReceiveDisplay: "R$ 36,00",
      weekToReceiveQ: 9900,
      weekToReceiveDisplay: "R$ 99,00",
      checkCount: 1,
    });
  });

  it("os cards da casa: Hoje, Semana e Via Pedido – painel, cada um com a sua rota", () => {
    const tiles = preorderHomeTiles(homeSummary(list([card({ ref: "1" })])));
    expect(tiles.map((t) => t.label)).toEqual(["Hoje", "Semana", "Via Pedido – painel"]);
    expect(tiles.map((t) => PREORDER_TILE_ROUTES[t.key])).toEqual(["/preorders/today", "/preorders/week", "/preorders/panel"]);
    expect(tiles[0]!.badge).toBe("1");
  });

  it("⚠️ zero não é selo nos cards: a descrição diz por extenso", () => {
    const tiles = preorderHomeTiles(homeSummary(list([], { count: 0 })));
    expect(tiles[0]!.badge).toBeUndefined();
    expect(tiles[0]!.description).toBe("Nenhuma encomenda para entregar hoje");
    expect(tiles[1]!.badge).toBeUndefined();
    expect(tiles[1]!.description).toBe("Nenhuma encomenda nos próximos 7 dias");
  });

  it("a palavra 'ficha' não volta para a tela", () => {
    const text = preorderHomeTiles(homeSummary(list([card()]))).map((t) => `${t.label} ${t.description}`).join(" ");
    expect(text.toLowerCase()).not.toContain("ficha");
  });
});
