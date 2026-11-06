import { describe, expect, it } from "vitest";
import type { Material, ReceiptLine, Supplier, SupplierMaterialCost } from "~/types/purchase";
import {
  basePricedOptionLabel,
  costPerReadingUnitQ,
  quotePreview,
  readingUnit,
  receiptLinePreview,
  reorderRows,
  resaleCopy,
} from "~/presentation/purchase";

// Beta 05/11, CMP-07 (decisão do dono, 06/11): custo de insumo em g ou ml se guarda
// e se lê por kg ou litro. 1200 g por R$ 110 = R$ 91,67/kg; reposição de 300 g =
// R$ 27,50. Por grama, o centavo inteiro arredondava para R$ 0,09 e a reposição
// saía R$ 27,00.
const tonica: Material = {
  sku: "TONICA-ANTARCTICA",
  name: "Água tônica",
  unit: "g",
  shelfLifeDays: null,
  isActive: true,
  category: "Bebidas",
  stockOnHand: 0,
  dailyUse: 10,
  minStock: 0,
  recipes: [],
  suggestedQty: 300,
};
const supplier = { ref: "ambev", displayName: "Ambev", isActive: true } as unknown as Supplier;

describe("custo de insumo em g é por kg (CMP-07)", () => {
  it("a unidade de leitura de g e mg é kg; de ml é l; o resto fica", () => {
    expect(readingUnit("g")).toEqual({ scale: 1000, label: "kg" });
    expect(readingUnit("mg")).toEqual({ scale: 1_000_000, label: "kg" });
    expect(readingUnit("ml")).toEqual({ scale: 1000, label: "l" });
    expect(readingUnit("un")).toEqual({ scale: 1, label: "un" });
    expect(basePricedOptionLabel("g")).toBe("Por kg (insumo em g)");
    expect(basePricedOptionLabel("un")).toBe("Unidade-base (un)");
  });

  it("o recebimento de 1200 g por R$ 110 mostra R$ 91,67 o kg", () => {
    const line: ReceiptLine = {
      id: "line-1",
      materialSku: "TONICA-ANTARCTICA",
      conversionId: "",
      purchaseQty: 1200,
      costInput: "110,00",
      expiryDate: "",
      checked: true,
    };
    const preview = receiptLinePreview(line, "manual", [tonica], []);
    expect(preview?.readingCostQ).toBe(9167);
    expect(preview?.readingUnitLabel).toBe("kg");
  });

  it("o custo guardado por kg estima a reposição de 300 g em R$ 27,50", () => {
    const cost: SupplierMaterialCost = {
      id: "c1",
      materialSku: "TONICA-ANTARCTICA",
      supplierRef: "ambev",
      conversionId: null,
      costQ: 9167,
      isPreferred: true,
      updatedAt: "2026-11-06",
    };
    expect(costPerReadingUnitQ(cost, tonica, [])).toBe(9167);
    const [row] = reorderRows([tonica], [supplier], [cost], []);
    expect(row?.estimatedCostQ).toBe(2750);
  });

  it("o custo avulso sem embalagem é digitado por kg", () => {
    expect(quotePreview("91,67", tonica, null)).toMatchObject({
      costQ: 9167,
      pricedUnitLabel: "kg",
      readingCostQ: 9167,
    });
  });

  it("item contado em g não se coloca à venda", () => {
    expect(resaleCopy("g", "").blocked).toContain("perde os centavos");
    expect(resaleCopy("un", "").blocked).toBe("");
    expect(resaleCopy("kg", "").blocked).toBe("");
  });
});

describe("pergunta do custo preferencial fala por kg (CMP-06 com CMP-07)", () => {
  it("1200 g por R$ 110 contra preferencial de R$ 80/kg mostra R$ 91,67 / kg", async () => {
    const { receiptPreferredCostChanges } = await import("~/presentation/purchase");
    const line: ReceiptLine = {
      id: "line-1",
      materialSku: "TONICA-ANTARCTICA",
      conversionId: "",
      purchaseQty: 1200,
      costInput: "110,00",
      expiryDate: "",
      checked: true,
    };
    const preview = receiptLinePreview(line, "manual", [tonica], [])!;
    const cost: SupplierMaterialCost = {
      id: "c1", materialSku: "TONICA-ANTARCTICA", supplierRef: "ambev", conversionId: null,
      costQ: 8000, isPreferred: true, updatedAt: "2026-11-06",
    };
    const [change] = receiptPreferredCostChanges([preview], [cost], "ambev", []);
    expect(change).toMatchObject({ unitLabel: "kg", currentQ: 8000, incomingQ: 9167 });
    expect(receiptPreferredCostChanges([preview], [{ ...cost, costQ: 9167 }], "ambev", [])).toEqual([]);
  });
});
