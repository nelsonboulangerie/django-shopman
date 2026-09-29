/**
 * A nota traz o código de barras do pote que a casa já vende: a linha sugere o
 * item do Compras com o MESMO SKU — e diz que foi pelo código, não pelo nome.
 * Continua sugestão: o operador confirma ("É este") e o recebimento aprende.
 */
import { describe, expect, it } from "vitest";
import type { Material, ReceiptLine } from "~/types/purchase";
import { receiptLinePreview } from "~/presentation/purchase";

const geleia: Material = {
  sku: "GELEIA-FIGO-STDALFOUR-284",
  name: "Geleia Figo St. Dalfour 284g",
  unit: "un",
  shelfLifeDays: null,
  isActive: true,
  category: "Revenda",
  stockOnHand: 0,
  dailyUse: 0,
  minStock: 0,
  recipes: [],
};

const linha: ReceiptLine = {
  id: "nfe-1",
  materialSku: "",
  suggestedMaterialSku: geleia.sku,
  suggestionScore: 100,
  suggestionSource: "gtin",
  conversionId: null,
  purchaseQty: 6,
  costInput: "150,00",
  expiryDate: "",
  lineNote: "",
  invoiceDescription: "DOCE FIGO ST DALFOUR 284G",
  checked: false,
};

describe("sugestão pelo código de barras", () => {
  it("sugere o item do mesmo SKU e diz que foi pelo código", () => {
    const preview = receiptLinePreview(linha, "invoice", [geleia], []);

    expect(preview?.suggestion).toEqual({ sku: geleia.sku, name: geleia.name, scorePercent: 100, byBarcode: true });
    // Sugestão não é escolha: a linha só libera quando o operador confirma.
    expect(preview?.warnings.map((warning) => warning.key)).toContain("confirm-suggestion");
  });

  it("sugestão pelo nome continua dizendo o quanto parece", () => {
    const preview = receiptLinePreview({ ...linha, suggestionSource: "name", suggestionScore: 88 }, "invoice", [geleia], []);

    expect(preview?.suggestion?.byBarcode).toBe(false);
    expect(preview?.suggestion?.scorePercent).toBe(88);
  });
});
