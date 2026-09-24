/**
 * A linha da nota que aponta para MERCADORIA DE REVENDA.
 *
 * O chá, a geleia e o queijo chegam na mesma nota dos insumos, mas moram no
 * catálogo: é o mesmo pote que o cliente leva. Na tela eles entram na MESMA
 * lista de escolha — o operador tem uma nota na mão, não duas —, e o que os
 * distingue é a dica ("revenda · Kãnfa"), não um segundo campo.
 */
import { describe, expect, it } from "vitest";
import type { ReceiptLine, ResaleProduct } from "~/types/purchase";
import { receiptLineLabel, receiptLinePreview } from "~/presentation/purchase";

const cha: ResaleProduct = {
  sku: "INTU_P50",
  name: "Intuição Chai Kãnfa — Pouch 50g",
  unit: "un",
  shelfLifeDays: null,
  isActive: true,
  brand: "Kãnfa",
  stockOnHand: 4,
};

function linha(extra: Partial<ReceiptLine> = {}): ReceiptLine {
  return {
    id: "nfe-1",
    materialSku: "",
    productSku: "INTU_P50",
    conversionId: null,
    purchaseQty: 2,
    costInput: "84,80",
    expiryDate: "",
    lineNote: "",
    checked: false,
    ...extra,
  };
}

describe("recebimento de mercadoria de revenda", () => {
  it("resolve a linha pelo produto, sem pedir insumo nenhum", () => {
    const preview = receiptLinePreview(linha(), "invoice", [], [], [cha]);

    expect(preview?.isResale).toBe(true);
    expect(preview?.material.name).toBe(cha.name);
    expect(preview?.material.unit).toBe("un");
    // Nada de "escolha o insumo": a linha já está resolvida.
    expect(preview?.warnings.map((warning) => warning.key)).not.toContain("missing-material");
  });

  it("conta na unidade de venda: revenda não passa por conversão", () => {
    const preview = receiptLinePreview(linha(), "invoice", [], [], [cha]);

    expect(preview?.baseQty).toBe(2);
    expect(preview?.baseQtyKnown).toBe(true);
    expect(preview?.conversion).toBeNull();
    expect(preview?.totalCostQ).toBe(8480);
  });

  it("o cabeçalho da linha diz o nome da mercadoria", () => {
    const preview = receiptLinePreview(linha(), "manual", [], [], [cha])!;

    expect(receiptLineLabel(preview)).toBe(cha.name);
  });

  it("produto que a tela não conhece volta a pedir escolha, em vez de inventar nome", () => {
    const preview = receiptLinePreview(linha({ productSku: "SUMIU" }), "invoice", [], [], [cha]);

    expect(preview?.isResale).toBe(false);
    expect(preview?.warnings.map((warning) => warning.key)).toContain("missing-material");
  });

  it("mercadoria com validade cobra a validade, igual ao insumo perecível", () => {
    const perecivel = { ...cha, shelfLifeDays: 180 };

    const preview = receiptLinePreview(linha(), "invoice", [], [], [perecivel]);

    expect(preview?.needsExpiry).toBe(true);
    expect(preview?.warnings.map((warning) => warning.key)).toContain("missing-expiry");
  });
});
