import { describe, expect, it } from "vitest";

import type { POSCartItem } from "~/types/pos";
import { buildPosSaleIntent } from "~/utils/posIntent";
import { lineTotalQ } from "~/presentation/lineDiscounts";
import { countUnits } from "~/presentation/selection";
import { cartQtyForSku } from "~/presentation/catalog";
import { receiptLineTotalQ } from "~/presentation/receipt";
import {
  editWeighedBuffer,
  gramsForLabel,
  bufferDisplay,
  productBlockedLabel,
  lineQtyLabel,
  parseKgToGrams,
  parseMoneyToQ,
  totalForGrams,
  weighedEntryFor,
  weighedPreview,
} from "~/presentation/weighed";

const PRECO_KG = 8990; // R$ 89,90/kg

function queijo(overrides: Partial<POSCartItem> = {}): POSCartItem {
  return {
    line_id: "L-queijo01",
    sku: "QUEIJO-VALEDOTESTO-POMERODE",
    name: "Queijo Vale do Testo",
    price_q: PRECO_KG,
    qty: 0.312,
    weighed: { entry: "label", label_q: 2805, weight_g: 312 },
    notes: "",
    ...overrides,
  };
}

describe("a conta da etiqueta — a mesma do servidor", () => {
  it("312 g a R$ 89,90/kg voltam R$ 28,05, e R$ 28,05 volta 312 g", () => {
    expect(totalForGrams(312, PRECO_KG)).toBe(2805);
    expect(gramsForLabel(2805, PRECO_KG)).toBe(312);
  });

  it("toda etiqueta da mesma balança bate no centavo (1 g a 3 kg)", () => {
    for (const price of [150, 999, 1000, 4590, 8990, 23900]) {
      for (let grams = 1; grams <= 3000; grams += 1) {
        const label = totalForGrams(grams, price);
        if (label <= 0) continue;
        expect(totalForGrams(gramsForLabel(label, price), price)).toBe(label);
      }
    }
  });

  it("valor sem grama exata fica abaixo da etiqueta, nunca acima", () => {
    const grams = gramsForLabel(2800, PRECO_KG);
    expect(grams).toBe(311);
    expect(totalForGrams(grams, PRECO_KG)).toBe(2796);
    expect(totalForGrams(grams + 1, PRECO_KG)).toBeGreaterThan(2800);
  });
});

describe("o campo do diálogo", () => {
  it("valor em reais: vírgula uma vez, duas casas", () => {
    let buffer = "";
    for (const key of ["2", "8", ",", "0", "5", "9", ","]) buffer = editWeighedBuffer(buffer, key, "money");
    expect(buffer).toBe("28,05");
    expect(parseMoneyToQ(buffer)).toBe(2805);
  });

  it("peso em quilos: vírgula no começo vira 0, três casas", () => {
    let buffer = "";
    for (const key of [",", "3", "1", "2", "7"]) buffer = editWeighedBuffer(buffer, key, "kg");
    expect(buffer).toBe("0,312");
    expect(parseKgToGrams(buffer)).toBe(312);
    expect(editWeighedBuffer(buffer, "Backspace", "kg")).toBe("0,31");
  });
});

describe("a prévia", () => {
  it("campo vazio ou zerado: nada a confirmar (o botão fica bloqueado)", () => {
    for (const buffer of ["", "0", "0,00"]) {
      expect(weighedPreview({ kind: "label", buffer, pricePerKgQ: PRECO_KG }).ok).toBe(false);
    }
    expect(bufferDisplay("", "money")).toBe("0,00");
    expect(bufferDisplay("", "kg")).toBe("0,000");
  });

  it("valor da etiqueta: deriva o peso e o valor", () => {
    const preview = weighedPreview({ kind: "label", buffer: "28,05", pricePerKgQ: PRECO_KG });
    expect(preview.ok).toBe(true);
    expect(preview.weightG).toBe(312);
    expect(preview.totalQ).toBe(2805);
    expect(preview.gapNote).toBe("");
    expect(weighedEntryFor("label", preview)).toEqual({ entry: "label", label_q: 2805, weight_g: 312 });
  });

  it("etiqueta de outro preço do quilo: cobra o que o peso vale e DIZ a diferença", () => {
    const preview = weighedPreview({ kind: "label", buffer: "28,00", pricePerKgQ: PRECO_KG });
    expect(preview.totalQ).toBe(2796);
    expect(preview.gapQ).toBe(4);
    expect(preview.gapNote).toContain("confira o preço do quilo");
  });

  it("peso (balança ligada): o valor sai do peso × preço do quilo", () => {
    const preview = weighedPreview({ kind: "weight", buffer: "1,25", pricePerKgQ: PRECO_KG });
    expect(preview.totalQ).toBe(11238);
    expect(weighedEntryFor("weight", preview)).toEqual({ entry: "weight", weight_g: 1250 });
  });

  it("sem preço do quilo não há o que confirmar", () => {
    const preview = weighedPreview({ kind: "label", buffer: "28,05", pricePerKgQ: 0 });
    expect(preview.ok).toBe(false);
    expect(preview.error).toContain("Sem preço do quilo");
  });

  it("peso absurdo é recusado na tela antes do servidor", () => {
    expect(weighedPreview({ kind: "weight", buffer: "31,2", pricePerKgQ: PRECO_KG }).ok).toBe(false);
  });
});

describe("preço zero não vende", () => {
  it("o tile sem preço fica inerte com o motivo", () => {
    expect(productBlockedLabel({ price_q: 0, sold_out: false })).toBe("Sem preço");
    expect(productBlockedLabel({ price_q: 1200, sold_out: true })).toBe("Esgotado");
    expect(productBlockedLabel({ price_q: 6000, sold_out: true, sold_out_reason: "Sem caixa" })).toBe("Sem caixa");
    expect(productBlockedLabel({ price_q: 1200, sold_out: false })).toBe("");
  });
});

describe("a linha pesada no resto do PDV", () => {
  it("o total da linha é peso × preço do quilo, sem fração de centavo", () => {
    expect(lineTotalQ(queijo())).toBe(2805);
  });

  it("a peça conta como UM item no carrinho e no selo do grid", () => {
    const pao: POSCartItem = { line_id: "L-pao00001", sku: "PAO", name: "Pão", price_q: 1200, qty: 2, notes: "" };
    const items = [queijo(), queijo({ line_id: "L-queijo02", qty: 0.5, weighed: { entry: "weight", weight_g: 500 } }), pao];
    expect(countUnits(items)).toBe(4);
    expect(cartQtyForSku(items, "QUEIJO-VALEDOTESTO-POMERODE")).toBe(2);
  });

  it("a quantidade se lê como na etiqueta", () => {
    expect(lineQtyLabel(queijo())).toBe("0,312 kg");
  });

  it("o intent manda o que o operador digitou, não o peso nem o preço", () => {
    const state = {
      tabRef: "", tabSessionKey: "", customerName: "", customerRef: "", customerPhone: "",
      customerTaxId: "", invoiceTaxId: "", customerEmail: "", customerMemoryAction: "",
      fulfillmentType: "pickup" as const, deliveryAddress: "",
      deliveryAddressStructured: null as never, deliveryComplement: "", deliveryInstructions: "",
      deliveryDate: "", deliveryTimeSlot: "", deliveryFeeOverrideQ: null, orderNotes: "",
      paymentMethod: "cash", paymentCollection: "terminal" as const, paymentTenders: [],
      tenderedQ: null, changeForQ: 0, receiptChannels: [],
      receiptEmail: "", manualDiscount: null, managerApproval: null,
      saveReceiptTaxIdConfirmed: false,
      clientRequestId: "pos:peso-1",
      items: [queijo()],
    };
    const payload = buildPosSaleIntent(state as never) as { items: Array<Record<string, unknown>> };
    expect(payload.items[0]!.weighed).toEqual({ entry: "label", label_q: 2805 });
  });

  it("o recibo do navegador soma a peça pelo peso", () => {
    expect(receiptLineTotalQ({ name: "Queijo", qty: 0.312, price_q: PRECO_KG, discountPct: 0, weightG: 312 })).toBe(2805);
  });
});
