import type {
  EnrichedMaterial,
  Material,
  MaterialConversion,
  MaterialIssue,
  MaterialTone,
  ReceiptConversionSuggestion,
  ReceiptLine,
  ReceiptLinePreview,
  ReceiptLineSuggestion,
  ReceiptMode,
  ReceiptWarning,
  QuotePreview,
  Supplier,
  SupplierCostRow,
  SupplierMaterialCost,
} from "~/types/purchase";

const moneyFormatter = new Intl.NumberFormat("pt-BR", {
  style: "currency",
  currency: "BRL",
  minimumFractionDigits: 2,
});

const quantityFormatter = new Intl.NumberFormat("pt-BR", {
  minimumFractionDigits: 0,
  maximumFractionDigits: 2,
});

export function formatMoney(cents: number | null | undefined): string {
  if (cents === null || cents === undefined || Number.isNaN(cents)) return "—";
  return moneyFormatter.format(cents / 100);
}

export function parseMoneyInput(value: string): number {
  const normalized = value
    .trim()
    .replace(/[R$\s]/g, "")
    .replace(/\./g, "")
    .replace(",", ".");
  const parsed = Number(normalized);
  if (!Number.isFinite(parsed) || parsed <= 0) return 0;
  return Math.round(parsed * 100);
}

export function formatQty(value: number, unit: string): string {
  if (!Number.isFinite(value)) return "—";
  return `${quantityFormatter.format(value)} ${unit}`;
}

/**
 * O saldo do insumo, com o "≈" quando ele atravessou uma ponte aproximada.
 *
 * ADR-024, R3: "some o ≈, some a informação". Um saldo de 1,5 kg que veio de
 * "30 ovos ≈ 50 g cada" não é o mesmo número que 1,5 kg pesados na balança, e a
 * tela é o último lugar onde ainda dá para dizer isso.
 */
export function formatStockOnHand(material: Pick<Material, "stockOnHand" | "unit" | "stockIsApproximate">): string {
  const quantity = formatQty(material.stockOnHand, material.unit);
  return material.stockIsApproximate ? `≈ ${quantity}` : quantity;
}

export function formatFactor(value: number, unit: string, approximate = false): string {
  const prefix = approximate ? "≈ " : "";
  return `${prefix}${quantityFormatter.format(value)} ${unit}`;
}

export function coverageDays(material: Pick<Material, "stockOnHand" | "dailyUse">): number {
  if (material.dailyUse <= 0) return Number.POSITIVE_INFINITY;
  return material.stockOnHand / material.dailyUse;
}

// O limiar vem do servidor (prazo do fornecedor + revisão + segurança, política
// no Admin); 3 é só o fallback do modo demonstração, sem backend.
export function replenishAtDays(material: Pick<Material, "replenishAtDays">): number {
  const days = material.replenishAtDays ?? 0;
  return Number.isFinite(days) && days > 0 ? days : 3;
}

export function coverageLabel(days: number): string {
  if (!Number.isFinite(days)) return "sem consumo";
  if (days < 1) return "< 1 dia";
  return `${quantityFormatter.format(days)} dias`;
}

export function conversionFor(
  cost: SupplierMaterialCost,
  conversions: MaterialConversion[],
): MaterialConversion | null {
  if (!cost.conversionId) return null;
  return conversions.find((conversion) => conversion.id === cost.conversionId) ?? null;
}

export function purchaseUnitLabel(
  cost: SupplierMaterialCost,
  material: Material | undefined,
  conversions: MaterialConversion[],
): string {
  return conversionFor(cost, conversions)?.label ?? material?.unit ?? "";
}

export function baseFactor(cost: SupplierMaterialCost, conversions: MaterialConversion[]): number {
  return conversionFor(cost, conversions)?.toBaseFactor ?? 1;
}

export function isApproximateCost(cost: SupplierMaterialCost, conversions: MaterialConversion[]): boolean {
  return conversionFor(cost, conversions)?.kind === "approximate";
}

export function costPerBaseUnitQ(cost: SupplierMaterialCost, conversions: MaterialConversion[]): number {
  const factor = baseFactor(cost, conversions);
  return Math.round(cost.costQ / factor);
}

export function quotePreview(
  input: string,
  material: Material | undefined,
  conversion: MaterialConversion | null,
): QuotePreview | null {
  const costQ = parseMoneyInput(input);
  if (!material || costQ <= 0) return null;
  const factor = conversion?.toBaseFactor ?? 1;
  return {
    costQ,
    purchaseUnitLabel: conversion?.label ?? material.unit,
    baseFactor: factor,
    baseCostQ: Math.round(costQ / factor),
    approximate: conversion?.kind === "approximate",
  };
}

export function parseInvoiceAccessKey(raw: string): string | null {
  const compact = raw.replace(/\D/g, "");
  const match = compact.match(/\d{44}/);
  return match?.[0] ?? null;
}

export function invoiceProbe(raw: string) {
  const accessKey = parseInvoiceAccessKey(raw);
  return {
    raw,
    accessKey,
    valid: Boolean(accessKey),
  };
}

export function receiptBaseQty(line: ReceiptLine, conversion: MaterialConversion | null): number {
  const factor = conversion?.toBaseFactor ?? 1;
  return line.purchaseQty * factor;
}

export function receiptLineSuggestion(line: ReceiptLine, materials: Material[]): ReceiptLineSuggestion | null {
  const sku = line.suggestedMaterialSku ?? "";
  if (line.materialSku || !sku) return null;
  const material = materials.find((item) => item.sku === sku);
  return {
    sku,
    name: material?.name ?? sku,
    scorePercent: Math.round(line.suggestionScore ?? 0),
  };
}

export function receiptConversionSuggestion(line: ReceiptLine): ReceiptConversionSuggestion | null {
  const suggestion = line.conversionSuggestion;
  if (!suggestion?.label) return null;
  const factor = Number(suggestion.factor);
  return Number.isFinite(factor) && factor > 0 ? suggestion : null;
}

/**
 * A NF discorda da conversão que a linha já usa.
 *
 * Compara os FATORES em vez de confiar na simples presença da sugestão. O
 * servidor de fato cala a sugestão quando os dois batem — mas só no momento do
 * scan, e a linha muda depois disso: aceitar a conversão sugerida cria a
 * conversão e a seleciona sem um novo scan, e aí a sugestão continua na linha
 * concordando com ela. Sem a comparação, o gesto de aceitar terminava
 * acusando divergência consigo mesmo.
 *
 * É o alerta de ordem de grandeza da ADR-024: saco declarado de 25 kg com nota
 * dizendo 20 é erro de 20% no custo e no estoque, e passa liso se ninguém
 * perguntar.
 */
export function receiptConversionDiverges(
  line: ReceiptLine,
  conversion: MaterialConversion | null,
): boolean {
  const suggestion = receiptConversionSuggestion(line);
  if (!conversion || !suggestion) return false;
  const suggested = Number(suggestion.factor);
  const chosen = conversion.toBaseFactor;
  if (!Number.isFinite(chosen) || chosen <= 0) return false;
  // Mesma tolerância relativa do servidor: 0,5 e 0,500000 são o mesmo fator.
  return Math.abs(chosen - suggested) > Math.max(chosen, suggested) * 0.001;
}

export function receiptLineWarnings(
  line: ReceiptLine,
  mode: ReceiptMode,
  material: Material | undefined,
  conversion: MaterialConversion | null,
): ReceiptWarning[] {
  const warnings: ReceiptWarning[] = [];
  if (!material) {
    return line.suggestedMaterialSku ?
        [{ key: "confirm-suggestion", label: "Confirmar sugestão de insumo", tone: "block" }]
      : [{ key: "missing-material", label: "Definir insumo", tone: "block" }];
  }
  if (!Number.isFinite(line.purchaseQty) || line.purchaseQty <= 0) {
    warnings.push({ key: "invalid-qty", label: "Quantidade precisa ser maior que zero", tone: "block" });
  }
  if (line.requiresConversion && !conversion) {
    // A NF sabe o fator: a linha continua bloqueando, mas o bloqueio agora tem
    // um gesto do lado — aceitar o que a nota diz — em vez de só uma acusação.
    warnings.push(
      receiptConversionSuggestion(line) ?
        { key: "confirm-conversion", label: "Confirmar conversão da NF", tone: "block" }
      : { key: "missing-conversion", label: "Definir conversão", tone: "block" },
    );
  }
  if (receiptConversionDiverges(line, conversion)) {
    warnings.push({ key: "diverging-conversion", label: "NF diverge da conversão", tone: "watch" });
  }
  if (parseMoneyInput(line.costInput) <= 0) {
    warnings.push({ key: "missing-cost", label: "Conferir valor", tone: "watch" });
  }
  if (material.shelfLifeDays !== null && !line.expiryDate) {
    warnings.push({ key: "missing-expiry", label: "Informar validade", tone: "block" });
  }
  if (conversion?.kind === "approximate") {
    warnings.push({ key: "approximate-conversion", label: "Conversão estimada", tone: "watch" });
  }
  if (mode === "manual") {
    warnings.push({ key: "manual-source", label: "Sem documento fiscal", tone: "watch" });
  }
  return warnings;
}

export function receiptLinePreview(
  line: ReceiptLine,
  mode: ReceiptMode,
  materials: Material[],
  conversions: MaterialConversion[],
): ReceiptLinePreview | null {
  const matchedMaterial = materials.find((item) => item.sku === line.materialSku);
  const material = matchedMaterial ?? {
    sku: line.materialSku || "",
    name: line.materialSku || "Definir insumo",
    unit: "un",
    shelfLifeDays: null,
    isActive: false,
    category: "Importado da NF",
    stockOnHand: 0,
    dailyUse: 0,
    minStock: 0,
    recipes: [],
  } satisfies Material;
  const conversion = line.conversionId ?
    conversions.find((item) => item.id === line.conversionId) ?? null
  : null;
  const baseQty = receiptBaseQty(line, conversion);
  const baseQtyKnown = Boolean(conversion) || !line.requiresConversion;
  const totalCostQ = parseMoneyInput(line.costInput);
  return {
    line,
    material,
    conversion,
    purchaseUnitLabel: conversion?.label ?? material.unit,
    baseQty,
    baseQtyKnown,
    baseCostQ: baseQtyKnown && baseQty > 0 ? Math.round(totalCostQ / baseQty) : 0,
    totalCostQ,
    approximate: conversion?.kind === "approximate",
    suggestion: receiptLineSuggestion(line, materials),
    conversionSuggestion: receiptConversionSuggestion(line),
    conversionDiverges: receiptConversionDiverges(line, conversion),
    warnings: receiptLineWarnings(line, mode, matchedMaterial, conversion),
  };
}

export function materialTone(material: Material, issues: MaterialIssue[]): MaterialTone {
  if (!material.isActive) return "watch";
  if (issues.some((issue) => issue.tone === "urgent")) return "urgent";
  if (issues.length) return "watch";
  return "ok";
}

export function materialIssues(
  material: Material,
  costs: SupplierMaterialCost[],
  conversions: MaterialConversion[],
): MaterialIssue[] {
  const materialCosts = costs.filter((cost) => cost.materialSku === material.sku);
  const preferred = materialCosts.find((cost) => cost.isPreferred) ?? null;
  const activeConversions = conversions.filter(
    (conversion) => conversion.materialSku === material.sku && conversion.isActive,
  );
  const days = coverageDays(material);
  const issues: MaterialIssue[] = [];

  if (!material.isActive) {
    issues.push({ key: "inactive-material", label: "Inativo", tone: "watch" });
  }
  if (days <= replenishAtDays(material) || material.stockOnHand < material.minStock) {
    issues.push({ key: "low-stock", label: "Reposição", tone: "urgent" });
  }
  if (!preferred) {
    issues.push({ key: "missing-preferred", label: "Sem custo preferencial", tone: "watch" });
  }
  if (preferred && isApproximateCost(preferred, conversions)) {
    issues.push({ key: "approximate-cost", label: "Custo estimado", tone: "watch" });
  }
  if (material.stockIsApproximate) {
    issues.push({ key: "approximate-stock", label: "Saldo estimado", tone: "watch" });
  }
  if (!activeConversions.length && materialCosts.some((cost) => cost.conversionId)) {
    issues.push({ key: "no-conversion", label: "Conversão inativa", tone: "watch" });
  }

  return issues;
}

export function enrichMaterial(
  material: Material,
  costs: SupplierMaterialCost[],
  conversions: MaterialConversion[],
): EnrichedMaterial {
  const materialCosts = costs.filter((cost) => cost.materialSku === material.sku);
  const preferredCost = materialCosts.find((cost) => cost.isPreferred) ?? null;
  const issues = materialIssues(material, costs, conversions);
  return {
    ...material,
    coverageDays: coverageDays(material),
    preferredCost,
    preferredBaseCostQ: preferredCost ? costPerBaseUnitQ(preferredCost, conversions) : null,
    supplierCount: new Set(materialCosts.map((cost) => cost.supplierRef)).size,
    conversionCount: conversions.filter((conversion) => conversion.materialSku === material.sku && conversion.isActive).length,
    tone: materialTone(material, issues),
    issues,
  };
}

export function supplierCostRows(
  material: Material,
  costs: SupplierMaterialCost[],
  suppliers: Supplier[],
  conversions: MaterialConversion[],
): SupplierCostRow[] {
  const materialCosts = costs.filter((cost) => cost.materialSku === material.sku);
  const preferredBaseCost =
    materialCosts.find((cost) => cost.isPreferred) ?
      costPerBaseUnitQ(materialCosts.find((cost) => cost.isPreferred) as SupplierMaterialCost, conversions)
    : Math.min(...materialCosts.map((cost) => costPerBaseUnitQ(cost, conversions)), Number.POSITIVE_INFINITY);

  return materialCosts
    .map((cost) => {
      const supplier = suppliers.find((item) => item.ref === cost.supplierRef);
      if (!supplier) return null;
      const baseCostQ = costPerBaseUnitQ(cost, conversions);
      const deltaQ = Number.isFinite(preferredBaseCost) ? baseCostQ - preferredBaseCost : 0;
      const deltaPercent = preferredBaseCost ? Math.round((deltaQ * 1000) / preferredBaseCost) / 10 : 0;
      return {
        cost,
        supplier,
        conversion: conversionFor(cost, conversions),
        purchaseUnitLabel: purchaseUnitLabel(cost, material, conversions),
        baseCostQ,
        approximate: isApproximateCost(cost, conversions),
        deltaQ,
        deltaPercent,
      };
    })
    .filter((row): row is SupplierCostRow => Boolean(row))
    .sort((a, b) => a.baseCostQ - b.baseCostQ);
}
