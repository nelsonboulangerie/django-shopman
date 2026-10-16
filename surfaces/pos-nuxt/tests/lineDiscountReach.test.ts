// Desconto em R$ na linha é POR UNIDADE (regra do kernel, `DiscountModifier._calc_manual`).
// A tela diz isso por extenso quando a linha tem mais de uma unidade, e em % diz
// também o valor na linha (decisão do dono, 14/10/2026).
import { describe, expect, it } from "vitest";

import {
  discountReachText,
  draftDiscountReach,
  lineDiscountDetail,
  lineDiscountFact,
  lineDiscountReach,
} from "~/presentation/lineDiscounts";
import type { POSCartItem } from "~/types/pos";
import { formatBRL } from "~/utils/posIntent";

function item(overrides: Partial<POSCartItem> = {}): POSCartItem {
  return { line_id: "L1", sku: "PAO", name: "Pão", price_q: 690, qty: 3, notes: "", ...overrides };
}

const R = (q: number) => formatBRL(q);

describe("alcance do desconto da linha", () => {
  it("R$ numa linha de 3: por unidade e na linha, nunca colado ao preço", () => {
    const line = item({
      list_price_q: 690,
      charged_price_q: 590,
      discount: { type: "fixed", value: 1, reason: "cortesia" },
    });
    expect(lineDiscountFact(line)).toBe(`−${R(100)} por unidade · −${R(300)} na linha`);
    expect(lineDiscountDetail(line, [{ ref: "cortesia", label: "Cortesia" }])).toBe(
      `Cortesia −${R(100)} por unidade · −${R(300)} na linha`,
    );
    expect(lineDiscountFact(line)).not.toContain(R(690));
  });

  it("R$ numa linha de 1: o valor basta", () => {
    const line = item({ qty: 1, list_price_q: 690, charged_price_q: 590, discount: { type: "fixed", value: 1, reason: "cortesia" } });
    expect(lineDiscountFact(line)).toBe(`−${R(100)}`);
  });

  it("% mostra também o valor na linha", () => {
    const line = item({ list_price_q: 690, charged_price_q: 621, discount: { type: "percent", value: 10, reason: "cortesia" } });
    expect(lineDiscountFact(line)).toBe(`−10% · −${R(207)} na linha`);
    const single = item({ qty: 1, list_price_q: 690, charged_price_q: 621, discount: { type: "percent", value: 10, reason: "cortesia" } });
    expect(lineDiscountFact(single)).toBe(`−10% · −${R(69)} na linha`);
  });

  it("o automático que venceu fala com o percentual dele e o valor na linha", () => {
    const line = item({
      list_price_q: 1300,
      charged_price_q: 1105,
      pricing_discount: { type: "promotion", label: "Liquidação", amount_q: 195, percent: 15 },
    });
    expect(lineDiscountFact(line)).toBe(`−15% · −${R(585)} na linha`);
    expect(lineDiscountDetail(line)).toBe(`Liquidação −15% · −${R(585)} na linha`);
  });

  it("sem desconto, nada", () => {
    expect(lineDiscountReach(item())).toBeNull();
    expect(lineDiscountFact(item())).toBe("");
  });

  it("sem o eco do servidor, a conta do kernel sobre a etiqueta", () => {
    const line = item({ price_q: 690, discount: { type: "fixed", value: 1.5, reason: "cortesia" } });
    expect(lineDiscountFact(line)).toBe(`−${R(150)} por unidade · −${R(450)} na linha`);
  });

  it("o rascunho do editor: R$ por unidade × quantidade, teto na etiqueta", () => {
    const line = item({ list_price_q: 690 });
    const fixed = draftDiscountReach(line, "fixed", 1)!;
    expect(discountReachText(fixed)).toBe(`${R(100)} por unidade · ${R(300)} na linha`);
    const capped = draftDiscountReach(line, "fixed", 10)!;
    expect(capped.perUnitQ).toBe(690);
    expect(capped.lineQ).toBe(2070);
    const pct = draftDiscountReach(line, "percent", 10)!;
    expect(discountReachText(pct)).toBe(`10% · ${R(207)} na linha`);
    expect(draftDiscountReach(line, "fixed", 0)).toBeNull();
  });

  it("peça pesada: o valor na linha segue o peso, sem 'por unidade'", () => {
    const line = item({ qty: 0.5, list_price_q: 4000, weighed: { weight_g: 500 } as POSCartItem["weighed"] });
    const pct = draftDiscountReach(line, "percent", 10)!;
    expect(pct.multiUnit).toBe(false);
    expect(discountReachText(pct)).toBe(`10% · ${R(200)} na linha`);
  });
});
