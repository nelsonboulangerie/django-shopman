/**
 * A NF-e de compra confere o cadastro fiscal do produto que a linha abastece.
 * A divergência é AVISO (âmbar), nunca bloqueio — e vale só para o item que a
 * linha aponta agora: trocar o item cala a conferência do anterior.
 */
import { describe, expect, it } from "vitest";
import type { Material, ReceiptLine } from "~/types/purchase";
import { receiptLinePreview, receiptLineStatus } from "~/presentation/purchase";

const cha: Material = {
  sku: "INTU_P50",
  name: "Intuição Chai — Pouch 50g",
  unit: "un",
  shelfLifeDays: null,
  isActive: true,
  category: "Revenda",
  stockOnHand: 0,
  dailyUse: 0,
  minStock: 0,
  recipes: [],
};

const outro: Material = { ...cha, sku: "OUTRO", name: "Outro item" };

const linha: ReceiptLine = {
  id: "nfe-1",
  materialSku: cha.sku,
  suggestedMaterialSku: "",
  suggestionScore: 0,
  conversionId: null,
  purchaseQty: 2,
  costInput: "84,80",
  expiryDate: "",
  lineNote: "",
  invoiceNcm: "21069090",
  fiscalDivergences: [
    {
      sku: cha.sku,
      field: "ncm",
      catalogValue: "09024000",
      invoiceValue: "21069090",
      message: "NCM diverge: o cadastro diz 09024000, a nota diz 21069090.",
    },
  ],
  checked: false,
};

describe("NF-e diverge do cadastro fiscal", () => {
  it("vira aviso de atenção, sem bloquear a entrada", () => {
    const preview = receiptLinePreview(linha, "invoice", [cha, outro], []);

    expect(preview?.warnings).toContainEqual({
      key: "fiscal-divergence",
      label: "NF diverge do cadastro fiscal",
      tone: "watch",
    });
    expect(preview?.fiscalDivergences.map((divergence) => divergence.message)).toEqual([
      "NCM diverge: o cadastro diz 09024000, a nota diz 21069090.",
    ]);
    expect(receiptLineStatus(preview!)).toBe("attention");
  });

  it("some quando a linha passa a apontar para outro item", () => {
    const preview = receiptLinePreview({ ...linha, materialSku: outro.sku }, "invoice", [cha, outro], []);

    expect(preview?.fiscalDivergences).toEqual([]);
    expect(preview?.warnings.map((warning) => warning.key)).not.toContain("fiscal-divergence");
  });

  it("nota que concorda com o cadastro não avisa nada", () => {
    const preview = receiptLinePreview({ ...linha, fiscalDivergences: [] }, "invoice", [cha], []);

    expect(preview?.warnings.map((warning) => warning.key)).not.toContain("fiscal-divergence");
  });
});
