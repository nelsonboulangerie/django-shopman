import { describe, expect, it } from "vitest";
import type { Material, MaterialConversion, ReceiptLine } from "~/types/purchase";
import {
  receiptConferenceTally,
  receiptDefaultConversionId,
  receiptExceptionView,
  receiptLineInBaseUnit,
  receiptLineMatchesInvoice,
  receiptLinePreview,
  receiptSettledSummary,
} from "~/presentation/purchase";

// UX-C1b: os dois defeitos que o #1409 mostrou rodando de verdade.
// 1. Nota já na unidade-base recebia a embalagem padrão por cima.
// 2. "3 de 3 conferidos" com os três itens ainda pendentes de validade.

const creme: Material = {
  sku: "CREME-FR",
  name: "Creme de leite fresco",
  unit: "g",
  shelfLifeDays: 10,
  isActive: true,
  category: "Frescos",
  stockOnHand: 0,
  dailyUse: 0,
  minStock: 0,
  recipes: [],
};

const farinha: Material = {
  sku: "FAR-T65",
  name: "Farinha T65",
  unit: "kg",
  shelfLifeDays: null,
  isActive: true,
  category: "Farinhas",
  stockOnHand: 0,
  dailyUse: 0,
  minStock: 0,
  recipes: [],
};

const litros: MaterialConversion = {
  id: "litros",
  materialSku: "CREME-FR",
  supplierRef: "deleite",
  label: "litros",
  toBaseFactor: 1010,
  kind: "conventional",
  isActive: true,
};
const saco: MaterialConversion = {
  id: "saco",
  materialSku: "FAR-T65",
  supplierRef: "deleite",
  label: "saco 25 kg",
  toBaseFactor: 25,
  kind: "conventional",
  isActive: true,
};

// Como o leitor de NF-e devolve "5 KG" de creme de leite para um insumo em g:
// quantidade já na base, sem conversão e sem pedir uma.
function cremeEmKg(patch: Partial<ReceiptLine> = {}): ReceiptLine {
  return {
    id: "nfe-1",
    materialSku: "CREME-FR",
    conversionId: null,
    requiresConversion: false,
    purchaseQty: 5000,
    invoicePurchaseQty: 5000,
    invoiceQty: 5,
    invoiceUnit: "KG",
    costInput: "160,00",
    invoiceTotal: "160,00",
    expiryDate: "",
    lineNote: "",
    checked: false,
    ...patch,
  };
}

// "2 SC" de farinha: a nota fala embalagem, o servidor não converte e trava.
function farinhaEmSaco(patch: Partial<ReceiptLine> = {}): ReceiptLine {
  return {
    id: "nfe-2",
    materialSku: "FAR-T65",
    conversionId: null,
    requiresConversion: true,
    purchaseQty: 2,
    invoicePurchaseQty: 2,
    invoiceQty: 2,
    invoiceUnit: "SC",
    costInput: "360,00",
    invoiceTotal: "360,00",
    expiryDate: "",
    lineNote: "",
    checked: false,
    ...patch,
  };
}

function preview(line: ReceiptLine) {
  return receiptLinePreview(line, "invoice", [creme, farinha], [litros, saco])!;
}

describe("conversão: nota já na unidade-base não recebe embalagem por cima", () => {
  it("nota em KG para insumo em g, sem conversão: nenhuma conversão padrão", () => {
    const line = cremeEmKg();
    expect(receiptLineInBaseUnit(line)).toBe(true);
    expect(receiptDefaultConversionId(line, [litros])).toBeNull();
  });

  it("o resumo diz os 5.000 g da nota, e não 5.050.000 g", () => {
    const summary = receiptSettledSummary(preview(cremeEmKg()));
    expect(summary).toContain("5.000 × g");
    expect(summary).not.toContain("litros");
    expect(summary).not.toContain("5.050.000");
  });

  it("nota em embalagem (SC) sem conversão: aplica a padrão do insumo", () => {
    const line = farinhaEmSaco();
    expect(receiptLineInBaseUnit(line)).toBe(false);
    expect(receiptDefaultConversionId(line, [saco])).toBe("saco");
    const summary = receiptSettledSummary(preview({ ...line, conversionId: "saco" }));
    expect(summary).toContain("2 × saco 25 kg = 50 kg");
  });

  it("linha lançada à mão (sem unidade da nota) continua recebendo a padrão", () => {
    const manual = cremeEmKg({ invoiceUnit: undefined, requiresConversion: undefined });
    expect(receiptDefaultConversionId(manual, [litros])).toBe("litros");
  });

  it("embalagem escolhida por cima de nota em peso não bate com a nota (o servidor recusa igual)", () => {
    const comLitros = cremeEmKg({ conversionId: "litros", expiryDate: "2026-10-13" });
    expect(receiptLineMatchesInvoice(preview(comLitros), "invoice")).toBe(false);
    expect(receiptLineMatchesInvoice(preview(cremeEmKg({ expiryDate: "2026-10-13" })), "invoice")).toBe(true);
  });
});

describe("contagem de conferidos diz a verdade", () => {
  const bacon = (patch: Partial<ReceiptLine> = {}) =>
    cremeEmKg({ id: "nfe-3", purchaseQty: 3000, invoicePurchaseQty: 3000, invoiceQty: 3, costInput: "174,00", invoiceTotal: "174,00", ...patch });
  const cebola = (patch: Partial<ReceiptLine> = {}) =>
    cremeEmKg({ id: "nfe-4", purchaseQty: 10000, invoicePurchaseQty: 10000, invoiceQty: 10, costInput: "75,00", invoiceTotal: "75,00", ...patch });

  function tally(lines: ReceiptLine[], counted: number | null) {
    const previews = lines.map(preview);
    const view = receiptExceptionView(previews, "invoice", 4, counted);
    const matchedIds = new Set(view.matched.map((item) => item.line.id));
    return receiptConferenceTally(previews, matchedIds, view.countOk);
  }

  it("volumes contados com a validade pendente: nenhum pronto, e diz o que falta", () => {
    const result = tally([cremeEmKg(), bacon(), cebola()], 4);
    expect(result.ready).toBe(0);
    expect(result.missingExpiry).toBe(3);
    expect(result.label).toBe("0 de 3 prontos para entrar · falta a validade de 3");
  });

  it("com a validade de um: um pronto, falta a de dois", () => {
    const result = tally([cremeEmKg({ expiryDate: "2026-10-13" }), bacon(), cebola()], 4);
    expect(result.label).toBe("1 de 3 prontos para entrar · falta a validade de 2");
  });

  it("tudo com validade e volumes contados: todos prontos", () => {
    const result = tally(
      [cremeEmKg({ expiryDate: "2026-10-13" }), bacon({ expiryDate: "2026-10-13" }), cebola({ expiryDate: "2026-10-13" })],
      4,
    );
    expect(result.ready).toBe(3);
    expect(result.label).toBe("3 de 3 prontos para entrar");
  });

  it("validade preenchida mas volumes não contados: bater com a nota ainda não assina", () => {
    const result = tally(
      [cremeEmKg({ expiryDate: "2026-10-13" }), bacon({ expiryDate: "2026-10-13" }), cebola({ expiryDate: "2026-10-13" })],
      null,
    );
    expect(result.ready).toBe(0);
    expect(result.label).toBe("0 de 3 prontos para entrar");
  });

  it("ok da linha com bloqueio não conta como pronto", () => {
    const result = tally([cremeEmKg({ checked: true })], null);
    expect(result.ready).toBe(0);
    expect(result.label).toBe("0 de 1 prontos para entrar · falta a validade de 1");
  });

  it("sem itens", () => {
    expect(receiptConferenceTally([], new Set(), false).label).toBe("Nenhum item ainda");
  });
});
