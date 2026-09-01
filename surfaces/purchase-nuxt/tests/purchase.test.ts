import { describe, expect, it } from "vitest";
import type { CountItem, Material, MaterialConversion, ReceiptLine, Supplier, SupplierMaterialCost } from "~/types/purchase";
import {
  PURCHASE_API_ENDPOINTS,
  PURCHASE_API_BASE,
} from "~/composables/usePurchaseApi";
import {
  costPerBaseUnitQ,
  countConfirmPayload,
  countRow,
  countRows,
  countSummary,
  formatMoney,
  formatQtyDiff,
  costBatchLineErrors,
  costBatchPayload,
  formatShortDate,
  formatStockOnHand,
  reorderBlockers,
  reorderRows,
  receiptFirstBlocker,
  receiptIsBlank,
  receiptOutcomeSummary,
  receiptPendingItems,
  receiptSettledSummary,
  materialIssues,
  parseInvoiceAccessKey,
  parseMoneyInput,
  parseQtyInput,
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

// Insumo pesado em kg e comprado em pacote: e nesse par que os dois eixos da
// NF-e brigam, e onde 10 unidades viravam 10 kg.
const fermento: Material = {
  sku: "FERMENTO-BIO",
  name: "Fermento biológico",
  unit: "kg",
  shelfLifeDays: null,
  isActive: true,
  category: "Fermentos",
  stockOnHand: 3,
  dailyUse: 0.6,
  minStock: 2,
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
      label: "Escolha o insumo desta linha",
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
      label: "Confirme o insumo sugerido",
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
      label: "Cadastre a conversão da embalagem",
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
      label: "Informe a validade",
      tone: "block",
    });
  });

  it("trata a conversao da NF como sugestao: bloqueia ate o operador decidir", () => {
    // O caso do dono: 10 UNIDADES de fermento com base kg. A linha vem com a
    // quantidade comercial e o fator que a NF declarou, e NAO se confirma
    // sozinha — mas agora o bloqueio vem com o gesto do lado.
    const line: ReceiptLine = {
      id: "nfe-1",
      materialSku: "FERMENTO-BIO",
      conversionId: null,
      requiresConversion: true,
      conversionSuggestion: {
        label: "un 500 g",
        factor: "0.5",
        kind: "conventional",
        source: "invoice-tax-pair",
        note: "A NF diz 10 UN = 5 KG, então 1 UN = 0,5 kg.",
      },
      purchaseQty: 10,
      costInput: "60,00",
      expiryDate: "",
      lineNote: "Confirmar a conversao sugerida (un 500 g). NF: FERM BIOL FRESCO MAURI 500G.",
      invoiceUnit: "UN",
      checked: true,
    };

    const preview = receiptLinePreview(line, "invoice", [fermento], []);

    expect(preview?.conversionSuggestion?.label).toBe("un 500 g");
    expect(preview?.conversionDiverges).toBe(false);
    // O total na unidade-base NAO e conhecido ainda: imprimir "10 kg" ao lado do
    // bloqueio seria repetir na tela exatamente o numero que o dono reportou.
    expect(preview?.baseQtyKnown).toBe(false);
    expect(preview?.baseCostQ).toBe(0);
    expect(preview?.warnings).toContainEqual({
      key: "confirm-conversion",
      label: "Confirme a conversão que a NF sugere",
      tone: "block",
    });
    expect(preview?.warnings.map((warning) => warning.key)).not.toContain("missing-conversion");
  });

  it("libera a linha assim que a conversao declarada entra", () => {
    const declared: MaterialConversion = {
      id: "pacote-500",
      materialSku: "FERMENTO-BIO",
      supplierRef: "SUP-MOINHO",
      label: "un 500 g",
      toBaseFactor: 0.5,
      kind: "conventional",
      isActive: true,
    };
    const line: ReceiptLine = {
      id: "nfe-1",
      materialSku: "FERMENTO-BIO",
      conversionId: "pacote-500",
      requiresConversion: false,
      purchaseQty: 10,
      costInput: "60,00",
      expiryDate: "",
      lineNote: "",
      checked: true,
    };

    const preview = receiptLinePreview(line, "invoice", [fermento], [declared]);

    // 10 pacotes viram 5 kg — o numero que o dono viu errado como "10 kg".
    expect(preview?.baseQty).toBe(5);
    expect(preview?.baseQtyKnown).toBe(true);
    expect(preview?.purchaseUnitLabel).toBe("un 500 g");
    expect(preview?.warnings.map((warning) => warning.key)).not.toContain("confirm-conversion");
    expect(preview?.warnings.map((warning) => warning.key)).not.toContain("missing-conversion");
  });

  it("avisa quando a NF discorda da conversao ja escolhida, sem travar a entrada", () => {
    const line: ReceiptLine = {
      id: "nfe-1",
      materialSku: "FARINHA-T65",
      conversionId: "saco-25",
      requiresConversion: false,
      conversionSuggestion: {
        label: "saco 20 kg",
        factor: "20",
        kind: "conventional",
        source: "invoice-tax-pair",
        note: "A NF diz 2 SC = 40 KG, então 1 SC = 20 kg.",
      },
      purchaseQty: 2,
      costInput: "360,00",
      expiryDate: "2027-02-25",
      lineNote: "",
      checked: true,
    };

    const preview = receiptLinePreview(line, "invoice", [farinha], conversions);

    expect(preview?.conversionDiverges).toBe(true);
    expect(preview?.warnings).toContainEqual({
      key: "diverging-conversion",
      label: "NF diverge da conversão",
      tone: "watch",
    });
    expect(preview?.warnings.filter((warning) => warning.tone === "block")).toHaveLength(0);
  });

  it("aceitar a conversao sugerida nao vira acusacao de divergencia contra ela mesma", () => {
    // Aceitar cria a conversao e a seleciona SEM novo scan, entao a sugestao
    // continua na linha — concordando. Comparar os fatores é o que impede o
    // gesto de terminar acusando divergencia consigo mesmo.
    const declared: MaterialConversion = {
      id: "un-500",
      materialSku: "FERMENTO-BIO",
      supplierRef: "SUP-MOINHO",
      label: "un 500 g",
      toBaseFactor: 0.5,
      kind: "conventional",
      isActive: true,
    };
    const line: ReceiptLine = {
      id: "nfe-1",
      materialSku: "FERMENTO-BIO",
      conversionId: "un-500",
      requiresConversion: false,
      conversionSuggestion: {
        label: "un 500 g",
        factor: "0.500000",
        kind: "conventional",
        source: "invoice-tax-pair",
        note: "A NF diz 10 UN = 5 KG, então 1 UN = 0,5 kg.",
      },
      purchaseQty: 10,
      costInput: "60,00",
      expiryDate: "",
      lineNote: "",
      checked: true,
    };

    const preview = receiptLinePreview(line, "invoice", [fermento], [declared]);

    expect(preview?.conversionDiverges).toBe(false);
    expect(preview?.baseQty).toBe(5);
    expect(preview?.warnings.map((warning) => warning.key)).not.toContain("diverging-conversion");
  });

  it("ignora sugestao de conversao com fator invalido", () => {
    const line: ReceiptLine = {
      id: "nfe-1",
      materialSku: "FERMENTO-BIO",
      conversionId: null,
      requiresConversion: true,
      conversionSuggestion: {
        label: "un",
        factor: "0",
        kind: "conventional",
        source: "invoice-tax-pair",
        note: "",
      },
      purchaseQty: 10,
      costInput: "60,00",
      expiryDate: "",
      lineNote: "",
      checked: true,
    };

    const preview = receiptLinePreview(line, "invoice", [fermento], []);

    expect(preview?.conversionSuggestion).toBeNull();
    expect(preview?.warnings).toContainEqual({
      key: "missing-conversion",
      label: "Cadastre a conversão da embalagem",
      tone: "block",
    });
  });

  it("saldo que atravessou ponte aproximada carrega o ≈ ate a tela", () => {
    // R3 da ADR-024: 1,5 kg vindos de "30 ovos ≈ 50 g" nao sao o mesmo numero
    // que 1,5 kg pesados, e a tela e o ultimo lugar onde da para dizer isso.
    const estimado = { ...ovos, stockIsApproximate: true };

    expect(formatStockOnHand(estimado)).toBe("≈ 16 kg");
    expect(materialIssues(estimado, [], [])).toContainEqual({
      key: "approximate-stock",
      label: "Saldo estimado",
      tone: "watch",
    });
  });

  it("numero exato nao ganha enfeite", () => {
    expect(formatStockOnHand(farinha)).toBe("80 kg");
    expect(materialIssues(farinha, [], []).map((issue) => issue.key)).not.toContain("approximate-stock");
  });

  it("a quantidade sempre diz de QUE unidade se trata — '4 o que?'", () => {
    const semInsumo: ReceiptLine = {
      id: "nfe-1",
      materialSku: "",
      suggestedMaterialSku: "FARINHA-T65",
      suggestionScore: 100,
      conversionId: null,
      requiresConversion: true,
      purchaseQty: 4,
      costInput: "730,00",
      expiryDate: "",
      lineNote: "",
      invoiceDescription: "FARINHA TRIGO T65 ESPECIAL SC 25KG",
      invoiceQty: 4,
      invoiceUnit: "SC",
      invoiceTaxQty: 100,
      invoiceTaxUnit: "KG",
      checked: false,
    };

    // Sem insumo ainda: a NOTA responde. Nunca "kg" — 4 sacos nao sao 4 kg.
    expect(receiptLinePreview(semInsumo, "invoice", [farinha], [])?.purchaseUnitLabel).toBe("SC");

    // Insumo aceito, conversao ainda pendente: continua sendo a unidade da nota.
    const comInsumo = { ...semInsumo, materialSku: "FARINHA-T65" };
    expect(receiptLinePreview(comInsumo, "invoice", [farinha], [])?.purchaseUnitLabel).toBe("SC");

    // Conversao escolhida: passa a valer o vocabulario em que o operador conta.
    const resolvido = { ...comInsumo, conversionId: "saco-25", requiresConversion: false };
    expect(receiptLinePreview(resolvido, "invoice", [farinha], conversions)?.purchaseUnitLabel).toBe("saco 25 kg");
  });

  it("a linha carrega o que a NF diz, para o operador saber qual item e", () => {
    const line: ReceiptLine = {
      id: "nfe-1",
      materialSku: "",
      conversionId: null,
      requiresConversion: true,
      purchaseQty: 4,
      costInput: "730,00",
      expiryDate: "",
      lineNote: "",
      invoiceDescription: "FARINHA TRIGO T65 ESPECIAL SC 25KG",
      invoiceQty: 4,
      invoiceUnit: "SC",
      invoiceTaxQty: 100,
      invoiceTaxUnit: "KG",
      invoiceProductCode: "7891",
      checked: false,
    };

    const preview = receiptLinePreview(line, "invoice", [farinha], []);

    expect(preview?.invoiceSummary).toBe("4 SC · 100 KG na NF · cód 7891");
    // Uma instrucao por linha, na propria linha: o painel listava dez pilulas
    // iguais sem dizer de qual item.
    expect(preview?.nextStep).toBe("Escolha o insumo desta linha");
    // A ocorrencia e do operador e nasce vazia.
    expect(preview?.line.lineNote).toBe("");
  });

  it("a linha conferida cabe numa frase, para poder recolher", () => {
    // Numa nota de dez itens, formulario aberto de quem ja decidiu so atrapalha
    // quem procura o que falta. O resumo tem de bastar para a conferencia de olho.
    const line: ReceiptLine = {
      id: "nfe-1",
      materialSku: "FARINHA-T65",
      conversionId: "saco-25",
      requiresConversion: false,
      purchaseQty: 4,
      costInput: "730,00",
      expiryDate: "2027-02-25",
      lineNote: "",
      invoiceDescription: "FARINHA TRIGO T65 ESPECIAL SC 25KG",
      invoiceQty: 4,
      invoiceUnit: "SC",
      checked: true,
    };

    const preview = receiptLinePreview(line, "invoice", [farinha], conversions);

    // `formatMoney` para montar a expectativa: o Intl usa espaco NAO-QUEBRAVEL
    // entre "R$" e o numero, e comparar com um espaco comum falha exibindo duas
    // strings visualmente identicas — meia hora de caca ao fantasma.
    expect(receiptSettledSummary(preview!)).toBe(`4 × saco 25 kg = 100 kg · ${formatMoney(73000)}`);
  });

  it("entrada na propria unidade-base nao repete a unidade no resumo", () => {
    const line: ReceiptLine = {
      id: "line-sal",
      materialSku: "FARINHA-T65",
      conversionId: null,
      requiresConversion: false,
      purchaseQty: 12,
      costInput: "",
      expiryDate: "",
      lineNote: "",
      checked: true,
    };

    const preview = receiptLinePreview(line, "manual", [farinha], []);

    // Sem conversao e sem valor, o resumo e so a quantidade — nada de "= 12 kg"
    // repetindo o que ja foi dito, nem um "R$ 0,00" que ninguem digitou.
    expect(receiptSettledSummary(preview!)).toBe("12 × kg");
  });

  it("declara paths BFF estaveis para wiring com Buyman", () => {
    expect(PURCHASE_API_BASE).toBe("/api/v1/backstage/purchase/");
    expect(PURCHASE_API_ENDPOINTS.projection).toBe("/api/v1/backstage/purchase/");
    expect(PURCHASE_API_ENDPOINTS.confirmReceipt).toBe("/api/v1/backstage/purchase/receipts/confirm/");
    expect(PURCHASE_API_ENDPOINTS.declareConversion).toBe("/api/v1/backstage/purchase/conversions/");
    expect(PURCHASE_API_ENDPOINTS.requestApprove("FARINHA T65")).toBe(
      "/api/v1/backstage/purchase/requests/FARINHA%20T65/approve/",
    );
    expect(PURCHASE_API_ENDPOINTS.count).toBe("/api/v1/backstage/purchase/count/");
    expect(PURCHASE_API_ENDPOINTS.countConfirm).toBe("/api/v1/backstage/purchase/count/confirm/");
  });
});

describe("avisos do recebimento", () => {
  function lineOf(patch: Partial<ReceiptLine> = {}): ReceiptLine {
    return {
      id: "line-1",
      materialSku: "OVOS",
      conversionId: null,
      purchaseQty: 2,
      costInput: "24,00",
      expiryDate: "2026-10-01",
      lineNote: "",
      invoiceDescription: "OVOS BRANCOS CX 30",
      checked: true,
      ...patch,
    };
  }

  it("a pendencia sabe em QUE campo ela mora, para a tela poder levar ate la", () => {
    const preview = receiptLinePreview(lineOf({ expiryDate: "", checked: false }), "invoice", [ovos], []);

    expect(preview?.nextStep).toBe("Informe a validade");
    expect(preview?.nextStepField).toBe("expiry");
    expect(receiptPendingItems([preview!])).toEqual([
      { id: "line-1", label: "OVOS BRANCOS CX 30", step: "Informe a validade", field: "expiry", tone: "block" },
    ]);
  });

  it("cada bloqueio aponta o campo dele, e nao o topo do card", () => {
    const semInsumo = receiptLinePreview(lineOf({ materialSku: "" }), "invoice", [ovos], []);
    const semQuantidade = receiptLinePreview(lineOf({ purchaseQty: 0 }), "invoice", [ovos], []);
    const semConversao = receiptLinePreview(
      lineOf({ requiresConversion: true }),
      "invoice",
      [ovos],
      [],
    );

    expect(semInsumo?.nextStepField).toBe("material");
    expect(semQuantidade?.nextStepField).toBe("qty");
    expect(semConversao?.nextStepField).toBe("conversion");
  });

  // O buraco mais silencioso da tela: a linha estava inteira, o botao ficava
  // cinza, e NADA na pagina dizia que faltava conferir.
  it("linha pronta que ninguem conferiu tambem e pendencia — era invisivel", () => {
    const preview = receiptLinePreview(lineOf({ checked: false }), "invoice", [ovos], []);

    expect(preview?.nextStep).toBe("");
    expect(receiptPendingItems([preview!])).toEqual([
      { id: "line-1", label: "OVOS BRANCOS CX 30", step: "Marcar como conferido", field: "check", tone: "watch" },
    ]);
  });

  it("linha conferida e sem bloqueio nao pendura nada", () => {
    const preview = receiptLinePreview(lineOf(), "invoice", [ovos], []);

    expect(receiptPendingItems([preview!])).toEqual([]);
  });

  // Confirmar zera o rascunho, e o rascunho zerado disparava os mesmos
  // bloqueios de sempre: vermelho de "escaneie a NF" logo ACIMA do verde de
  // "entrada confirmada". Rascunho em branco e convite, nao erro.
  it("rascunho em branco nao e erro", () => {
    expect(receiptIsBlank([], "", "")).toBe(true);
    expect(receiptIsBlank([], "  ", "\n")).toBe(true);
    expect(receiptIsBlank([lineOf()], "", "")).toBe(false);
    expect(receiptIsBlank([], "35190812...", "")).toBe(false);
    expect(receiptIsBlank([], "", "Romaneio em papel")).toBe(false);
  });

  it("o primeiro bloqueio segue a ordem em que a tela pede as coisas", () => {
    const pending = receiptPendingItems([receiptLinePreview(lineOf({ expiryDate: "" }), "invoice", [ovos], [])!]);

    expect(receiptFirstBlocker(["Ler QR, código de barras ou chave da NF"], ["Definir fornecedor"], pending, true)).toEqual({
      scope: "document",
      step: "Ler QR, código de barras ou chave da NF",
      label: "",
      lineId: "",
      field: null,
      anchor: "invoice",
    });
    expect(receiptFirstBlocker([], ["Definir fornecedor"], pending, true)?.anchor).toBe("supplier");
    expect(receiptFirstBlocker([], [], pending, true)).toEqual({
      scope: "line",
      step: "Informe a validade",
      label: "OVOS BRANCOS CX 30",
      lineId: "line-1",
      field: "expiry",
      anchor: null,
    });
  });

  it("sem nada lancado, o bloqueio e ter algo a lancar — nao um botao mudo", () => {
    expect(receiptFirstBlocker([], [], [], false)?.step).toBe("Lance ao menos um item para dar entrada");
  });

  it("pronto para confirmar nao inventa bloqueio", () => {
    expect(receiptFirstBlocker([], [], [], true)).toBeNull();
  });

  it("o aviso de sucesso diz o que entrou, e nao so que deu certo", () => {
    expect(
      receiptOutcomeSummary({
        kind: "confirmed",
        at: "2026-08-29",
        mode: "invoice",
        lineCount: 7,
        totalCostQ: 148000,
        supplierName: "Moinho SP",
      }),
      // `formatMoney` para montar a expectativa: o Intl usa espaco NAO-QUEBRAVEL
    // entre "R$" e o numero (a mesma armadilha do resumo da linha, acima).
    ).toBe(`7 itens · ${formatMoney(148000)} · Moinho SP`);
    expect(
      receiptOutcomeSummary({ kind: "confirmed", at: "2026-08-29", mode: "manual", lineCount: 1, totalCostQ: 0, supplierName: "" }),
    ).toBe("1 item");
  });
});

describe("parseMoneyInput — a tela e o servidor lendo o mesmo número", () => {
  // ⚠️ Havia DOIS parsers de dinheiro com regras diferentes. Este removia TODOS os
  // pontos antes de olhar a vírgula; o do servidor trata ponto como milhar só se
  // houver vírgula. O operador digita no campo livre (`inputmode="decimal"`) e os
  // dois lados divergiam em até 100×, sem nenhum deles avisar:
  //
  //     "12.50"  tela: R$ 1.250,00   servidor: R$ 12,50
  //
  // Havia 30 testes neste arquivo e ZERO sobre dinheiro digitado.
  it("lê o teclado da casa (vírgula decimal)", () => {
    expect(parseMoneyInput("12,50")).toBe(1250);
    expect(parseMoneyInput("1.250,00")).toBe(125000);
    expect(parseMoneyInput("R$ 360,00")).toBe(36000);
  });

  it("lê o teclado do sistema (ponto decimal) — era aqui que divergia 100×", () => {
    expect(parseMoneyInput("12.50")).toBe(1250);
    expect(parseMoneyInput("12.5")).toBe(1250);
    expect(parseMoneyInput("360.00")).toBe(36000);
  });

  it("vírgula presente decide a notação — a mesma regra do parseQtyInput", () => {
    // Com vírgula, o ponto é milhar.
    expect(parseMoneyInput("1.250,50")).toBe(125050);
    // Sem vírgula, o ponto é decimal.
    expect(parseMoneyInput("1250.50")).toBe(125050);
  });

  it("vazio é zero, e lixo não vira número", () => {
    expect(parseMoneyInput("")).toBe(0);
    expect(parseMoneyInput("   ")).toBe(0);
    expect(parseMoneyInput("abc")).toBe(0);
  });
});

describe("contagem de insumos", () => {
  const farinhaCount: CountItem = {
    sku: "FARINHA-T65",
    name: "Farinha T65",
    unit: "kg",
    category: "Farinhas",
    isActive: true,
    systemQty: 12,
  };

  const ovosCount: CountItem = {
    sku: "OVOS",
    name: "Ovos",
    unit: "kg",
    category: "Frescos",
    isActive: true,
    systemQty: 16,
  };

  it("aceita o teclado da casa e o do sistema no contado", () => {
    expect(parseQtyInput("12,5")).toBe(12.5);
    expect(parseQtyInput("1.250,5")).toBe(1250.5);
    expect(parseQtyInput("12.5")).toBe(12.5);
    expect(parseQtyInput("12")).toBe(12);
    expect(parseQtyInput("")).toBeNull();
    expect(parseQtyInput("abc")).toBeNull();
    expect(parseQtyInput("-3")).toBeNull();
  });

  it("linha sem contado nao diverge; divergencia sem motivo fica marcada", () => {
    expect(countRow(farinhaCount, "", "").divergent).toBe(false);
    expect(countRow(farinhaCount, "12", "").divergent).toBe(false);

    const shortage = countRow(farinhaCount, "10,5", "");
    expect(shortage.diff).toBe(-1.5);
    expect(shortage.divergent).toBe(true);
    expect(shortage.missingReason).toBe(true);

    const justified = countRow(farinhaCount, "10,5", "Quebra na produção");
    expect(justified.missingReason).toBe(false);
  });

  it("resumo so libera com algo contado e toda divergencia justificada", () => {
    const empty = countSummary(countRows([farinhaCount, ovosCount], {}, {}));
    expect(empty.ready).toBe(false);

    const pendingReason = countSummary(
      countRows([farinhaCount, ovosCount], { "FARINHA-T65": "10" }, {}),
    );
    expect(pendingReason).toEqual({ filled: 1, divergent: 1, missingReason: 1, ready: false });

    const ready = countSummary(
      countRows(
        [farinhaCount, ovosCount],
        { "FARINHA-T65": "10", OVOS: "16" },
        { "FARINHA-T65": "Quebra na produção" },
      ),
    );
    expect(ready).toEqual({ filled: 2, divergent: 1, missingReason: 0, ready: true });
  });

  it("payload leva so as linhas contadas, com quantidade numerica", () => {
    const rows = countRows(
      [farinhaCount, ovosCount],
      { "FARINHA-T65": "10,5" },
      { "FARINHA-T65": "  Quebra na produção  " },
    );
    expect(countConfirmPayload(rows)).toEqual({
      counts: [{ materialSku: "FARINHA-T65", countedQty: 10.5, reason: "Quebra na produção" }],
    });
  });

  it("formata a diferenca com sinal e unidade", () => {
    expect(formatQtyDiff(-1.5, "kg")).toBe("−1,5 kg");
    expect(formatQtyDiff(2, "un")).toBe("+2 un");
    expect(formatQtyDiff(0, "kg")).toBe("—");
  });
});

// ---------------------------------------------------------------------------
// formatShortDate — a data que faltava derrubava a tela
// ---------------------------------------------------------------------------
// 14 dos 15 fornecedores cadastrados nunca entregaram, e a projeção manda
// `lastDeliveryAt: ""` para todos eles (`last_delivery.get(supplier.ref, "")`
// em `_supplier_projection`). O formatador antigo montava a data por
// interpolação de string, que para "" vira Invalid Date — e
// `Intl.DateTimeFormat.format(Invalid Date)` NÃO devolve "—": ele lança
// `RangeError: Invalid time value` no meio do render, derrubando a árvore de
// componentes. Era o "não clica, não abre" da aba Fornecedores.
describe("formatShortDate", () => {
  it("formata a data que existe", () => {
    expect(formatShortDate("2026-08-27")).toBe("27/08");
  });

  it("não estoura com fornecedor que nunca entregou (string vazia)", () => {
    expect(() => formatShortDate("")).not.toThrow();
    expect(formatShortDate("")).toBe("—");
  });

  it("não estoura com campo ausente vindo da API", () => {
    expect(() => formatShortDate(undefined)).not.toThrow();
    expect(() => formatShortDate(null)).not.toThrow();
    expect(formatShortDate(undefined)).toBe("—");
    expect(formatShortDate(null)).toBe("—");
  });

  it("não estoura com data impossível de ler", () => {
    expect(() => formatShortDate("sem data")).not.toThrow();
    expect(formatShortDate("sem data")).toBe("—");
    expect(formatShortDate("2026-13-45")).toBe("—");
  });
});

// ---------------------------------------------------------------------------
// reorderRows — o painel e a tela respondem à MESMA pergunta
// ---------------------------------------------------------------------------
// O painel dizia "Comprar 8 · R$ 4.293,97" e a tela Comprar mostrava 0 pedidos
// e R$ 0,00, com os mesmos dados. Eram dois cálculos diferentes: o servidor
// respondia `suggestedQty` (política de reposição: prazo + revisão + segurança,
// limitada pela validade) e a tela ignorava esse número e refazia a conta com
// uma heurística própria — `ceil(max(minStock*2, dailyUse*7) - stockOnHand)`
// sobre um filtro próprio. Duas respostas para "o que comprar" é uma a mais.
// A resposta é do servidor; a tela mostra, não recalcula.
const semConsumo: Material = {
  sku: "MANTEIGA-TOURAGE",
  name: "Manteiga de tourage",
  unit: "kg",
  shelfLifeDays: 45,
  isActive: true,
  category: "Laticínios",
  stockOnHand: 22,
  dailyUse: 0,
  minStock: 30,
  recipes: ["Croissant"],
  suggestedQty: 0,
};

describe("reorderRows", () => {
  it("não inventa compra que o servidor não sugeriu", () => {
    // Estoque (22) abaixo do mínimo (30) faria a heurística antiga sugerir
    // compra; o servidor diz 0 porque não há consumo medido. Vale o servidor.
    expect(reorderRows([semConsumo], [], [], [])).toEqual([]);
  });

  it("mostra a quantidade que o servidor sugeriu, sem recalcular", () => {
    const material: Material = { ...semConsumo, dailyUse: 9, suggestedQty: 12 };
    const rows = reorderRows([material], [], [], []);
    expect(rows).toHaveLength(1);
    expect(rows[0]!.suggestedQty).toBe(12);
  });

  it("estima o custo pelo preferencial, e deixa nulo quando não há", () => {
    const material: Material = { ...semConsumo, dailyUse: 9, suggestedQty: 10 };
    const semCusto = reorderRows([material], [], [], []);
    expect(semCusto[0]!.estimatedCostQ).toBeNull();

    const supplier: Supplier = {
      ref: "SUP-LAT",
      name: "Laticínio",
      document: "",
      contact: "",
      leadTimeDays: 2,
      reliabilityPercent: 100,
      isActive: true,
      lastDeliveryAt: "",
      paymentTerm: "A combinar",
    };
    const cost: SupplierMaterialCost = {
      id: "c1",
      materialSku: "MANTEIGA-TOURAGE",
      supplierRef: "SUP-LAT",
      conversionId: null,
      costQ: 5000,
      isPreferred: true,
      updatedAt: "2026-08-01",
    };
    const comCusto = reorderRows([material], [supplier], [cost], []);
    expect(comCusto[0]!.supplier?.ref).toBe("SUP-LAT");
    expect(comCusto[0]!.estimatedCostQ).toBe(50000);
  });

  it("sem insumo nenhum, não há fila de compra", () => {
    expect(reorderRows([], [], [], [])).toEqual([]);
  });
});

// ---------------------------------------------------------------------------
// reorderBlockers — zero explicado, com o caminho
// ---------------------------------------------------------------------------
// Mostrar zero sem dizer por quê é o pecado da tela: o operador não distingue
// "não precisa comprar nada" de "o app não consegue calcular". São situações
// opostas e a segunda tem conserto. Cada motivo vem com o gesto que o resolve.
describe("reorderBlockers", () => {
  it("cala a boca quando há compra a fazer", () => {
    const material: Material = { ...semConsumo, dailyUse: 9, suggestedQty: 12 };
    expect(reorderBlockers([material], [])).toEqual([]);
  });

  it("diz quando a base está vazia", () => {
    const blockers = reorderBlockers([], []);
    expect(blockers).toHaveLength(1);
    expect(blockers[0]!.key).toBe("no-materials");
  });

  it("aponta o consumo não medido como causa da lista vazia", () => {
    const blockers = reorderBlockers([semConsumo], []);
    const consumo = blockers.find((item) => item.key === "no-consumption");
    expect(consumo).toBeDefined();
    // O número tem de ser o que a tela mostra, não um vago "alguns".
    expect(consumo!.count).toBe(1);
    expect(consumo!.action).not.toBeNull();
  });

  it("conta os insumos sem custo preferencial e manda para Custos", () => {
    const comConsumo: Material = { ...semConsumo, sku: "FARINHA-T45", dailyUse: 9, suggestedQty: 0 };
    const blockers = reorderBlockers([semConsumo, comConsumo], []);
    const custo = blockers.find((item) => item.key === "no-preferred-cost");
    expect(custo).toBeDefined();
    expect(custo!.count).toBe(2);
    expect(custo!.action?.baseView).toBe("costs");
  });

  it("não acusa falta de custo no insumo que já tem preferencial", () => {
    const cost: SupplierMaterialCost = {
      id: "c1",
      materialSku: "MANTEIGA-TOURAGE",
      supplierRef: "SUP-LAT",
      conversionId: null,
      costQ: 5000,
      isPreferred: true,
      updatedAt: "2026-08-01",
    };
    const blockers = reorderBlockers([semConsumo], [cost]);
    expect(blockers.find((item) => item.key === "no-preferred-cost")).toBeUndefined();
  });

  it("ignora insumo inativo na contagem", () => {
    const inativo: Material = { ...semConsumo, sku: "VELHO", isActive: false };
    const blockers = reorderBlockers([inativo], []);
    expect(blockers.find((item) => item.key === "no-materials")).toBeDefined();
  });
});

// ---------------------------------------------------------------------------
// costBatchPayload — a tabela de preços do fornecedor vira um POST
// ---------------------------------------------------------------------------
describe("costBatchPayload", () => {
  it("manda só as linhas preenchidas", () => {
    const payload = costBatchPayload(
      "SUP-TAMURA",
      { "CAFE-GRAO": "45,00", "FARINHA-T45": "", ACUCAR: "   " },
      {},
    );
    expect(payload).toEqual({
      supplierRef: "SUP-TAMURA",
      makePreferred: true,
      costs: [{ materialSku: "CAFE-GRAO", costInput: "45,00", conversionId: null }],
    });
  });

  it("leva a unidade de compra escolhida na linha", () => {
    const payload = costBatchPayload("SUP-TAMURA", { "CAFE-GRAO": "45,00" }, { "CAFE-GRAO": "7" });
    expect(payload.costs[0]!.conversionId).toBe("7");
  });

  it("ignora conversão de linha que não foi preenchida", () => {
    const payload = costBatchPayload("SUP-TAMURA", { "CAFE-GRAO": "" }, { "CAFE-GRAO": "7" });
    expect(payload.costs).toEqual([]);
  });

  it("apara o espaço em volta do valor digitado", () => {
    const payload = costBatchPayload("SUP-TAMURA", { "CAFE-GRAO": "  45,00 " }, {});
    expect(payload.costs[0]!.costInput).toBe("45,00");
  });
});

describe("costBatchLineErrors", () => {
  it("aponta a linha culpada pelo SKU", () => {
    const data = {
      detail: "Corrija as linhas indicadas para lançar o lote.",
      error: {
        code: "cost_batch_invalid",
        lines: [
          { index: 1, materialSku: "NAO-EXISTE", field: "materialSku", detail: "Insumo não encontrado." },
          { index: 4, materialSku: "SAL", field: "costInput", detail: "Informe um valor maior que zero." },
        ],
      },
    };
    expect(costBatchLineErrors(data)).toEqual({
      "NAO-EXISTE": "Insumo não encontrado.",
      SAL: "Informe um valor maior que zero.",
    });
  });

  it("não estoura com recusa que não fala de linha", () => {
    expect(costBatchLineErrors({ detail: "Sessão expirada", error: { code: "not_authenticated" } })).toEqual({});
    expect(costBatchLineErrors(null)).toEqual({});
    expect(costBatchLineErrors(undefined)).toEqual({});
    expect(costBatchLineErrors("erro")).toEqual({});
  });

  it("descarta linha malformada em vez de virar undefined na tela", () => {
    const data = { error: { lines: [{ index: 0 }, { materialSku: "SAL", detail: "Valor inválido." }] } };
    expect(costBatchLineErrors(data)).toEqual({ SAL: "Valor inválido." });
  });
});
