// Desconto em R$ na linha é POR UNIDADE (regra do kernel, `DiscountModifier._calc_manual`).
// A tela diz isso por extenso quando a linha tem mais de uma unidade, e em % diz
// também o valor na linha (decisão do dono, 14/10/2026).
import { describe, expect, it } from "vitest";

import {
  discountReachText,
  draftDiscountOutcome,
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

  it("sem o eco do servidor a tela não faz a conta do motor: sem número", () => {
    const line = item({ price_q: 690, discount: { type: "fixed", value: 1.5, reason: "cortesia" } });
    expect(lineDiscountReach(line)).toBeNull();
    // E com o eco a caminho (desconto recém-aplicado), o número velho não fala.
    const pending = item({
      list_price_q: 690, charged_price_q: 590, price_pending: true,
      discount: { type: "fixed", value: 2, reason: "cortesia" },
    });
    expect(lineDiscountFact(pending)).toBe("");
  });

  it("o rascunho do editor fala o que a REVISÃO do servidor deu à linha", () => {
    const line = item({ list_price_q: 690 });
    const fixed = draftDiscountOutcome(line, "fixed", 1, { list_price_q: 690, charged_price_q: 590 });
    expect(fixed?.kind === "reach" && discountReachText(fixed.reach)).toBe(`${R(100)} por unidade · ${R(300)} na linha`);
    // O teto é do motor: R$ 10,00 numa linha de R$ 6,90 cobra zero, e a tela repete.
    const capped = draftDiscountOutcome(line, "fixed", 10, { list_price_q: 690, charged_price_q: 0 });
    expect(capped?.kind === "reach" && capped.reach.lineQ).toBe(2070);
    // O arredondamento é do motor (R$ 6,21 → 69 por unidade), não da tela.
    const pct = draftDiscountOutcome(line, "percent", 10, { list_price_q: 690, charged_price_q: 621 });
    expect(pct?.kind === "reach" && discountReachText(pct.reach)).toBe(`10% · ${R(207)} na linha`);
    expect(draftDiscountOutcome(line, "fixed", 0, { list_price_q: 690, charged_price_q: 690 })).toBeNull();
  });

  it("o rascunho que o motor descartaria diz quem venceu", () => {
    const line = item({ list_price_q: 600 });
    const outcome = draftDiscountOutcome(line, "percent", 10, {
      list_price_q: 600, charged_price_q: 510, manual_discount_discarded: true,
      pricing_discount: { type: "promotion", label: "Semana do Pão", amount_q: 90, percent: 15 },
    });
    expect(outcome).toEqual({ kind: "discarded", winner: "Semana do Pão" });
  });

  it("peça pesada: o valor na linha segue o peso, sem 'por unidade'", () => {
    const line = item({ qty: 0.5, list_price_q: 4000, weighed: { weight_g: 500 } as POSCartItem["weighed"] });
    const pct = draftDiscountOutcome(line, "percent", 10, { list_price_q: 4000, charged_price_q: 3600 });
    expect(pct?.kind === "reach" && pct.reach.multiUnit).toBe(false);
    expect(pct?.kind === "reach" && discountReachText(pct.reach)).toBe(`10% · ${R(200)} na linha`);
  });
});
