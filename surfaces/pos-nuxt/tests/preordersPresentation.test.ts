// A seção Encomendas: os intervalos de cada tela, o agrupamento por janela e as
// frases que o balcão lê. O corte é do servidor; aqui se prende o FORMATO.
import { describe, expect, it } from "vitest";

import {
  NO_WINDOW_LABEL,
  PREORDER_SECTIONS,
  canSearch,
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
  todayCount,
  todayRange,
  weekRange,
} from "../app/presentation/preorders";
import type { PreorderCard, PreorderDay } from "../app/types/preorders";

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

  it("a contagem de hoje sai do dia marcado como hoje", () => {
    expect(todayCount([day({ orders_count: 2 }), day({ is_today: false, orders_count: 5 })])).toBe(2);
    expect(todayCount([])).toBe(0);
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
