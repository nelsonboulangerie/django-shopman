// Desconto do GRUPO do cliente na venda sem comanda (decisão do dono, 14/10/2026).
//
// A revisão do servidor devolve, por linha, o que ela cobra e o desconto
// automático que a venceu ("Aliança Francesa −10%"). A tela grava isso na linha
// (`applyLinePrices`) e o selo aparece; e a chave que decide pedir outra revisão
// ignora esses campos, senão gravar o eco pediria outra revisão sem fim.
import { describe, expect, it } from "vitest";

import { applyLinePrices, lineDiscountBadge, lineListTotalQ, lineTotalQ, linesWithoutServerPrices } from "~/presentation/lineDiscounts";
import type { POSCartItem } from "~/types/pos";

function cafe(overrides: Partial<POSCartItem> = {}): POSCartItem {
  return { line_id: "L1", sku: "CAFE", name: "Café", price_q: 800, qty: 2, notes: "", ...overrides };
}

const GRUPO = {
  charged_price_q: 720,
  list_price_q: 800,
  pricing_discount: { type: "promotion", label: "Aliança Francesa", amount_q: 80, percent: 10 },
};

describe("desconto do grupo na venda sem comanda", () => {
  it("o eco da revisão põe o selo, a etiqueta riscada e o total da linha", () => {
    const items = [cafe()];

    applyLinePrices(items, { L1: GRUPO });

    expect(lineDiscountBadge(items[0]!)).toBe("Aliança Francesa −10%");
    expect(lineTotalQ(items[0]!)).toBe(1440);
    expect(lineListTotalQ(items[0]!)).toBe(1600);
  });

  it("sem o cliente, o eco seguinte tira o selo", () => {
    const items = [cafe(GRUPO)];

    applyLinePrices(items, { L1: { charged_price_q: 800, list_price_q: 800, pricing_discount: null } });

    expect(lineDiscountBadge(items[0]!)).toBe("");
    expect(lineTotalQ(items[0]!)).toBe(1600);
  });

  it("gravar o eco não muda a chave que pede outra revisão", () => {
    const items = [cafe()];
    const before = JSON.stringify(linesWithoutServerPrices(items));

    applyLinePrices(items, { L1: GRUPO });

    expect(JSON.stringify(linesWithoutServerPrices(items))).toBe(before);
  });

  it("mudar a quantidade muda a chave", () => {
    const items = [cafe(GRUPO)];
    const before = JSON.stringify(linesWithoutServerPrices(items));

    items[0]!.qty = 3;

    expect(JSON.stringify(linesWithoutServerPrices(items))).not.toBe(before);
  });
});
