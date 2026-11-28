// FRETE GRÁTIS NO BALCÃO (P2-21): a revisão diz qual regra da loja renunciou à
// taxa, e a tela diz isso ao operador, curto e sem ambiguidade.
import { describe, expect, it } from "vitest";

import {
  deliveryFeeWaivedInFull,
  deliveryFeeWaiverNote,
  deliveryFeeWaiverShort,
} from "~/presentation/deliveryFeeWaiver";
import type { POSDeliveryFeeWaiverProjection } from "~/types/pos";

const promotion: POSDeliveryFeeWaiverProjection = {
  reason: "promotion", promotion_name: "Frete de verão", threshold_q: 0, base_fee_q: 800,
};
const threshold: POSDeliveryFeeWaiverProjection = {
  reason: "threshold", promotion_name: "", threshold_q: 12000, base_fee_q: 800,
};
const group: POSDeliveryFeeWaiverProjection = {
  reason: "group", promotion_name: "", threshold_q: 0, base_fee_q: 800, group_name: "Aliança Francesa",
};
const nbsp = (text: string) => text.replace(/\u00a0/g, " ");

describe("frete grátis no balcão", () => {
  it("sem renúncia, nada a dizer", () => {
    expect(deliveryFeeWaiverNote(null, 800)).toBe("");
    expect(deliveryFeeWaiverShort(undefined)).toBe("");
    expect(deliveryFeeWaivedInFull(null, 0)).toBe(false);
  });

  it("promoção que leva a taxa inteira: diz qual e quanto seria", () => {
    expect(deliveryFeeWaivedInFull(promotion, 0)).toBe(true);
    expect(nbsp(deliveryFeeWaiverNote(promotion, 0))).toBe(
      "Frete grátis pela promoção Frete de verão (a taxa seria R$ 8,00).",
    );
    expect(deliveryFeeWaiverShort(promotion)).toBe("Promoção Frete de verão");
  });

  it("promoção com teto: não diz grátis, diz quanto abate", () => {
    expect(deliveryFeeWaivedInFull(promotion, 300)).toBe(false);
    expect(nbsp(deliveryFeeWaiverNote(promotion, 300))).toBe(
      "A promoção Frete de verão abate R$ 5,00 da taxa (a taxa seria R$ 8,00).",
    );
  });

  it("limiar da loja: diz o valor mínimo da compra", () => {
    expect(nbsp(deliveryFeeWaiverNote(threshold, 0))).toBe(
      "Frete grátis nas compras a partir de R$ 120,00 (a taxa seria R$ 8,00).",
    );
    expect(nbsp(deliveryFeeWaiverShort(threshold))).toBe("Compras a partir de R$ 120,00");
  });

  it("frete grátis do grupo: diz o grupo e, com mínimo, a partir de quanto", () => {
    expect(nbsp(deliveryFeeWaiverNote(group, 0))).toBe(
      "Frete grátis por ser Aliança Francesa (a taxa seria R$ 8,00).",
    );
    expect(nbsp(deliveryFeeWaiverNote({ ...group, threshold_q: 5000 }, 0))).toBe(
      "Frete grátis por ser Aliança Francesa nas compras a partir de R$ 50,00 (a taxa seria R$ 8,00).",
    );
    expect(deliveryFeeWaiverShort(group)).toBe("Grupo Aliança Francesa");
    expect(deliveryFeeWaiverShort({ ...group, group_name: " " })).toBe("Grupo do cliente");
    expect(nbsp(deliveryFeeWaiverNote({ ...group, group_name: "" }, 0))).toBe(
      "Frete grátis do grupo do cliente (a taxa seria R$ 8,00).",
    );
  });

  it("promoção sem nome não vira frase quebrada", () => {
    const unnamed = { ...promotion, promotion_name: "  " };
    expect(nbsp(deliveryFeeWaiverNote(unnamed, 0))).toBe("Frete grátis pela promoção da loja (a taxa seria R$ 8,00).");
    expect(deliveryFeeWaiverShort(unnamed)).toBe("Promoção da loja");
  });

  it("copy sem travessão", () => {
    for (const text of [
      deliveryFeeWaiverNote(promotion, 0), deliveryFeeWaiverNote(promotion, 300),
      deliveryFeeWaiverNote(threshold, 0), deliveryFeeWaiverShort(promotion), deliveryFeeWaiverShort(threshold),
    ]) expect(text).not.toMatch(/[—–]/);
  });
});
