import { describe, expect, it } from "vitest";
import type { Material, MaterialConversion, ReceiptLine, Supplier, SupplierMaterialCost } from "~/types/purchase";
import {
  PURCHASE_API_ENDPOINTS,
  PURCHASE_API_BASE,
} from "~/composables/usePurchaseApi";
import {
  costPerBaseUnitQ,
  materialIssues,
  parseInvoiceAccessKey,
  quotePreview,
  receiptLinePreview,
  receiptLineSuggestion,
  supplierCostRows,
} from "~/presentation/purchase";

const farinha: Material = {
  sku: "FARINHA-T65",
  name: "Farinha T65",
  unit: "kg",
  shelfLifeDays: 180,
  isActive: true,
  category: "Farinhas",
  stockOnHand: 80,
  dailyUse: 20,
  minStock: 60,
  recipes: ["Baguete"],
};

const ovos: Material = {
  sku: "OVOS",
  name: "Ovos",
  unit: "kg",
  shelfLifeDays: 21,
  isActive: true,
  category: "Frescos",
  stockOnHand: 16,
  dailyUse: 4,
  minStock: 12,
  recipes: ["Brioche"],
};

const suppliers: Supplier[] = [
  {
    ref: "SUP-MOINHO",
    name: "Moinho SP",
    document: "",
    contact: "",
    leadTimeDays: 2,
    reliabilityPercent: 96,
    isActive: true,
    lastDeliveryAt: "2026-08-22",
    paymentTerm: "14 dias",
  },
  {
    ref: "SUP-COOP",
    name: "Cooperativa",
    document: "",
    contact: "",
    leadTimeDays: 3,
    reliabilityPercent: 91,
    isActive: true,
    lastDeliveryAt: "2026-08-20",
    paymentTerm: "7 dias",
  },
];

const conversions: MaterialConversion[] = [
  {
    id: "saco-25",
    materialSku: "FARINHA-T65",
    supplierRef: "SUP-MOINHO",
    label: "saco 25 kg",
    toBaseFactor: 25,
    kind: "conventional",
    isActive: true,
  },
  {
    id: "saco-20",
    materialSku: "FARINHA-T65",
    supplierRef: "SUP-COOP",
    label: "saco 20 kg",
    toBaseFactor: 20,
    kind: "conventional",
    isActive: true,
  },
];

describe("purchase presentation", () => {
  it("deriva custo por unidade-base a partir da unidade de compra", () => {
    const cost: SupplierMaterialCost = {
      id: "cost-1",
      materialSku: "FARINHA-T65",
      supplierRef: "SUP-MOINHO",
      conversionId: "saco-25",
      costQ: 18000,
      isPreferred: true,
      updatedAt: "2026-08-22",
    };

    expect(costPerBaseUnitQ(cost, conversions)).toBe(720);
    expect(quotePreview("180,00", farinha, conversions[0])).toMatchObject({
      costQ: 18000,
      purchaseUnitLabel: "saco 25 kg",
      baseFactor: 25,
      baseCostQ: 720,
      approximate: false,
    });
  });

  it("ordena fornecedores por custo-base e preserva delta contra o preferencial", () => {
    const costs: SupplierMaterialCost[] = [
      {
        id: "moinho",
        materialSku: "FARINHA-T65",
        supplierRef: "SUP-MOINHO",
        conversionId: "saco-25",
        costQ: 18000,
        isPreferred: true,
        updatedAt: "2026-08-22",
      },
      {
        id: "coop",
        materialSku: "FARINHA-T65",
        supplierRef: "SUP-COOP",
        conversionId: "saco-20",
        costQ: 15200,
        isPreferred: false,
        updatedAt: "2026-08-20",
      },
    ];

    const rows = supplierCostRows(farinha, costs, suppliers, conversions);

    expect(rows.map((row) => row.supplier.ref)).toEqual(["SUP-MOINHO", "SUP-COOP"]);
    expect(rows[1].baseCostQ).toBe(760);
    expect(rows[1].deltaQ).toBe(40);
    expect(rows[1].deltaPercent).toBe(5.6);
  });

  it("marca insumo sem custo preferencial como pendencia de cadastro", () => {
    const issues = materialIssues(farinha, [], conversions);

    expect(issues.map((issue) => issue.key)).toContain("missing-preferred");
  });

  it("usa o limiar de reposicao do servidor (prazo do fornecedor) em vez de horizonte fixo", () => {
    // 80 em estoque a 20/dia = 4 dias de cobertura: acima do fallback de 3 dias,
    // mas dentro do limiar de 6 dias que o servidor calculou para este fornecedor.
    const slowSupplier = { ...farinha, stockOnHand: 80, dailyUse: 20, minStock: 0, replenishAtDays: 6 };
    const fastSupplier = { ...farinha, stockOnHand: 80, dailyUse: 20, minStock: 0, replenishAtDays: 2 };

    expect(materialIssues(slowSupplier, [], conversions).map((issue) => issue.key)).toContain("low-stock");
    expect(materialIssues(fastSupplier, [], conversions).map((issue) => issue.key)).not.toContain("low-stock");
  });

  it("extrai a chave de acesso da NF a partir de QR code, codigo de barras ou texto colado", () => {
    const key = "41260812345678000190550010000012341000123459";

    expect(parseInvoiceAccessKey(`https://www.fazenda.pr.gov.br/nfce/qrcode?p=${key}|2|1|1|ABC`)).toBe(key);
    expect(parseInvoiceAccessKey(key)).toBe(key);
    expect(parseInvoiceAccessKey(`NF ${key}`)).toBe(key);
  });

  it("converte recebimento para unidade-base e sinaliza conversao aproximada", () => {
    const receiptConversions: MaterialConversion[] = [
      {
        id: "cartela",
        materialSku: "OVOS",
        supplierRef: null,
        label: "cartela",
        toBaseFactor: 1.5,
        kind: "approximate",
        isActive: true,
      },
    ];
    const line: ReceiptLine = {
      id: "line-1",
      materialSku: "OVOS",
      conversionId: "cartela",
      purchaseQty: 2,
      costInput: "48,00",
      expiryDate: "2026-09-08",
      checked: false,
    };

    const preview = receiptLinePreview(line, "manual", [ovos], receiptConversions);

    expect(preview).toMatchObject({
      baseQty: 3,
      totalCostQ: 4800,
      baseCostQ: 1600,
      approximate: true,
    });
    expect(preview?.warnings.map((warning) => warning.key)).toEqual(
      expect.arrayContaining(["approximate-conversion", "manual-source"]),
    );
  });

  it("mantem item importado sem insumo visivel e bloqueado", () => {
    const line: ReceiptLine = {
      id: "nfe-1",
      materialSku: "",
      conversionId: null,
      requiresConversion: true,
      purchaseQty: 2,
      costInput: "360,00",
      expiryDate: "",
      lineNote: "Definir insumo. NF: QUEIJO ARTESANAL; unidade PC.",
      invoiceProductCode: "QJO-ART",
      invoiceEan: "7891234567895",
      checked: false,
    };

    const preview = receiptLinePreview(line, "invoice", [farinha], conversions);

    expect(preview).toMatchObject({
      material: {
        sku: "",
        name: "Definir insumo",
        category: "Importado da NF",
      },
      totalCostQ: 36000,
    });
    // O confirm devolve a linha como veio do scan: o código da NF e o EAN
    // precisam sobreviver à camada de apresentação para o Django aprender o
    // mapeamento do fornecedor.
    expect(preview?.line.invoiceProductCode).toBe("QJO-ART");
    expect(preview?.line.invoiceEan).toBe("7891234567895");
    expect(preview?.warnings).toContainEqual({
      key: "missing-material",
      label: "Definir insumo",
      tone: "block",
    });
    expect(preview?.suggestion).toBeNull();
  });

  it("mostra sugestão fuzzy como sugestão e segue bloqueando até o operador decidir", () => {
    const line: ReceiptLine = {
      id: "nfe-1",
      materialSku: "",
      suggestedMaterialSku: "FARINHA-T65",
      suggestionScore: 90,
      conversionId: null,
      requiresConversion: true,
      purchaseQty: 2,
      costInput: "360,00",
      expiryDate: "",
      lineNote: "Definir insumo. NF: FARINHA DE TRIGO T65 SACO 25KG.",
      checked: false,
    };

    const preview = receiptLinePreview(line, "invoice", [farinha], conversions);

    expect(preview?.line.materialSku).toBe("");
    expect(preview?.suggestion).toEqual({
      sku: "FARINHA-T65",
      name: "Farinha T65",
      scorePercent: 90,
    });
    expect(preview?.warnings).toContainEqual({
      key: "confirm-suggestion",
      label: "Confirmar sugestão de insumo",
      tone: "block",
    });
    expect(preview?.warnings.map((warning) => warning.key)).not.toContain("missing-material");
  });

  it("some com a sugestão e libera o bloqueio quando o operador aceita ou troca o insumo", () => {
    const accepted: ReceiptLine = {
      id: "nfe-1",
      materialSku: "FARINHA-T65",
      suggestedMaterialSku: "FARINHA-T65",
      suggestionScore: 90,
      conversionId: "saco-25",
      purchaseQty: 2,
      costInput: "360,00",
      expiryDate: "2027-02-25",
      lineNote: "",
      checked: false,
    };

    expect(receiptLineSuggestion(accepted, [farinha])).toBeNull();

    const preview = receiptLinePreview(accepted, "invoice", [farinha], conversions);
    expect(preview?.suggestion).toBeNull();
    expect(preview?.warnings.map((warning) => warning.key)).not.toContain("confirm-suggestion");
    expect(preview?.warnings.map((warning) => warning.key)).not.toContain("missing-material");
  });

  it("bloqueia linha importada que ainda precisa de conversao", () => {
    const line: ReceiptLine = {
      id: "nfe-2",
      materialSku: "FARINHA-T65",
      conversionId: null,
      requiresConversion: true,
      purchaseQty: 2,
      costInput: "360,00",
      expiryDate: "2027-02-25",
      lineNote: "Definir conversao antes de confirmar. NF: FARINHA T65 25KG.",
      checked: true,
    };

    const preview = receiptLinePreview(line, "invoice", [farinha], conversions);

    expect(preview?.warnings).toContainEqual({
      key: "missing-conversion",
      label: "Definir conversão",
      tone: "block",
    });
  });

  it("bloqueia recebimento de perecivel sem validade", () => {
    const line: ReceiptLine = {
      id: "line-2",
      materialSku: "OVOS",
      conversionId: null,
      purchaseQty: 1,
      costInput: "24,00",
      expiryDate: "",
      checked: true,
    };

    const preview = receiptLinePreview(line, "invoice", [ovos], []);

    expect(preview?.warnings).toContainEqual({
      key: "missing-expiry",
      label: "Informar validade",
      tone: "block",
    });
  });

  it("declara paths BFF estaveis para wiring com Buyman", () => {
    expect(PURCHASE_API_BASE).toBe("/api/v1/backstage/purchase/");
    expect(PURCHASE_API_ENDPOINTS.projection).toBe("/api/v1/backstage/purchase/");
    expect(PURCHASE_API_ENDPOINTS.confirmReceipt).toBe("/api/v1/backstage/purchase/receipts/confirm/");
    expect(PURCHASE_API_ENDPOINTS.requestApprove("FARINHA T65")).toBe(
      "/api/v1/backstage/purchase/requests/FARINHA%20T65/approve/",
    );
  });
});
