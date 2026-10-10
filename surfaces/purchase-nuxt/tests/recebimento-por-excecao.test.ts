import { describe, expect, it } from "vitest";
import type { Material, MaterialConversion, ReceiptLine } from "~/types/purchase";
import {
  receiptDifferenceConsequence,
  receiptExceptionView,
  receiptExpectedVolumes,
  receiptExpiryShortcuts,
  receiptFirstBlocker,
  receiptLineDifference,
  receiptLineMatchesInvoice,
  receiptLinePreview,
  receiptLineRows,
  receiptPendingItems,
  receiptVolumesStep,
} from "~/presentation/purchase";

// Recebimento por exceção (UX-C1): o espelho na tela das regras do servidor
// (`services/purchase.py::_receipt_attestation`). A tela promete o que o
// servidor aceita.

const farinha: Material = {
  sku: "FAR-T65",
  name: "Farinha T65",
  unit: "kg",
  shelfLifeDays: null,
  isActive: true,
  category: "Farinhas",
  stockOnHand: 80,
  dailyUse: 20,
  minStock: 60,
  recipes: [],
};

const manteiga: Material = {
  sku: "MANT-SS",
  name: "Manteiga sem sal",
  unit: "kg",
  shelfLifeDays: 7,
  isActive: true,
  category: "Frescos",
  stockOnHand: 4,
  dailyUse: 2,
  minStock: 6,
  recipes: [],
  lastDeliveryExpiry: "2026-10-12",
};

const conversions: MaterialConversion[] = [
  { id: "saco", materialSku: "FAR-T65", supplierRef: "moinho", label: "saco 25 kg", toBaseFactor: 25, kind: "conventional", isActive: true },
  { id: "caixa", materialSku: "MANT-SS", supplierRef: "moinho", label: "caixa 5 kg", toBaseFactor: 5, kind: "conventional", isActive: true },
];

function line(patch: Partial<ReceiptLine> = {}): ReceiptLine {
  return {
    id: "l1",
    materialSku: "FAR-T65",
    conversionId: "saco",
    purchaseQty: 2,
    invoicePurchaseQty: 2,
    invoiceUnit: "SC",
    costInput: "360,00",
    invoiceTotal: "360,00",
    expiryDate: "",
    lineNote: "",
    checked: false,
    ...patch,
  };
}

const manteigaLine = (patch: Partial<ReceiptLine> = {}) =>
  line({ id: "l2", materialSku: "MANT-SS", conversionId: "caixa", purchaseQty: 4, invoicePurchaseQty: 4, invoiceUnit: "CX", costInput: "880,00", invoiceTotal: "880,00", ...patch });

function previews(lines: ReceiptLine[], mode: "invoice" | "manual" = "invoice") {
  return lines.map((item) => receiptLinePreview(item, mode, [farinha, manteiga], conversions)!);
}

describe("bate com a nota", () => {
  it("quantidade, valor e embalagem da nota: bate, mesmo sem validade ainda", () => {
    const [far, mant] = previews([line(), manteigaLine()]);
    expect(receiptLineMatchesInvoice(far!, "invoice")).toBe(true);
    expect(receiptLineMatchesInvoice(mant!, "invoice")).toBe(true);
  });

  it("valor diferente, ocorrência, embalagem divergente ou sem nota: não bate", () => {
    expect(receiptLineMatchesInvoice(previews([line({ costInput: "300,00" })])[0]!, "invoice")).toBe(false);
    expect(receiptLineMatchesInvoice(previews([line({ lineNote: "Avariado" })])[0]!, "invoice")).toBe(false);
    expect(
      receiptLineMatchesInvoice(
        previews([line({ conversionSuggestion: { label: "saco 20 kg", factor: "20", kind: "conventional", source: "", note: "" } })])[0]!,
        "invoice",
      ),
    ).toBe(false);
    expect(receiptLineMatchesInvoice(previews([line({ invoicePurchaseQty: null })])[0]!, "invoice")).toBe(false);
    expect(receiptLineMatchesInvoice(previews([line()], "manual")[0]!, "manual")).toBe(false);
  });
});

describe("volumes", () => {
  it("sem volumes declarados, soma as embalagens; a falta de uma linha de embalagem desconta", () => {
    expect(receiptExpectedVolumes(previews([line(), manteigaLine()]), 0)).toBe(6);
    expect(receiptExpectedVolumes(previews([line(), manteigaLine({ purchaseQty: 3, lineNote: "Faltou" })]), 0)).toBe(5);
  });

  it("linha a granel (KG sem embalagem) só se conta com os volumes da nota", () => {
    const granel = manteigaLine({ conversionId: null, purchaseQty: 20, invoicePurchaseQty: 20, invoiceUnit: "KG" });
    expect(receiptExpectedVolumes(previews([line(), granel]), 0)).toBeNull();
    expect(receiptExpectedVolumes(previews([line(), granel]), 6)).toBe(6);
  });
});

describe("a conferência por exceção, passo a passo", () => {
  it("1 · tudo bate: o passo é contar; sem contar, a pendência é a contagem", () => {
    const all = previews([line(), manteigaLine()]);
    const view = receiptExceptionView(all, "invoice", 0, null);
    expect(view.available).toBe(true);
    expect(view.step).toBe("count");
    expect(view.exceptions).toEqual([]);
    expect(receiptVolumesStep(view)).toBe("Contar os volumes da entrega");

    const matched = new Set(view.matched.map((preview) => preview.line.id));
    // O que bate não pede "Marcar como conferido": a contagem responde por ele.
    expect(receiptPendingItems(all, matched).filter((item) => item.step === "Marcar como conferido")).toEqual([]);
    const blocker = receiptFirstBlocker([], [], receiptPendingItems(all, matched), true, receiptVolumesStep(view));
    expect(blocker).toMatchObject({ scope: "volumes", anchor: "volumes" });
    expect(receiptLineRows(all, matched).map((row) => row.status)).toEqual(["matched", "blocked"]);
  });

  it("2 · contou e fechou: falta só a validade do perecível, com o selo apontando para ela", () => {
    const all = previews([line(), manteigaLine()]);
    const view = receiptExceptionView(all, "invoice", 0, 6);
    expect(view.countOk).toBe(true);
    expect(view.step).toBe("expiry");
    expect(view.nextExpiry?.line.id).toBe("l2");
    expect(view.expiryDone).toBe(0);
    expect(view.perishables).toHaveLength(1);

    const matched = new Set(view.matched.map((preview) => preview.line.id));
    const blocker = receiptFirstBlocker([], [], receiptPendingItems(all, matched), true, receiptVolumesStep(view));
    expect(blocker).toMatchObject({ scope: "line", lineId: "l2", field: "expiry", step: "Informe a validade" });
  });

  it("3 · com validade: pronto, nenhuma pendência", () => {
    const all = previews([line(), manteigaLine({ expiryDate: "2026-10-12" })]);
    const view = receiptExceptionView(all, "invoice", 0, 6);
    expect(view.step).toBe("done");
    const matched = new Set(view.matched.map((preview) => preview.line.id));
    expect(receiptFirstBlocker([], [], receiptPendingItems(all, matched), true, receiptVolumesStep(view))).toBeNull();
  });

  it("contagem errada não passa: diz quanto contou e manda achar o item", () => {
    const view = receiptExceptionView(previews([line(), manteigaLine()]), "invoice", 0, 5);
    expect(view.countOk).toBe(false);
    expect(view.step).toBe("count");
    expect(receiptVolumesStep(view)).toBe("Contou 5 de 6: ache o item que não bate");
  });

  it("item que não bate: diferença sem motivo bloqueia; com motivo, pede o ok dele", () => {
    const semMotivo = previews([line(), manteigaLine({ purchaseQty: 3, costInput: "660,00", expiryDate: "2026-10-12" })]);
    const view = receiptExceptionView(semMotivo, "invoice", 0, 5);
    expect(view.exceptions.map((preview) => preview.line.id)).toEqual(["l2"]);
    expect(view.countOk).toBe(true);
    const matched = new Set(view.matched.map((preview) => preview.line.id));
    expect(receiptPendingItems(semMotivo, matched)).toEqual([
      { id: "l2", label: "Manteiga sem sal", step: "Escolha o motivo da diferença", field: "reason", tone: "block" },
    ]);

    const comMotivo = previews([line(), manteigaLine({ purchaseQty: 3, costInput: "660,00", expiryDate: "2026-10-12", lineNote: "Faltou" })]);
    expect(receiptPendingItems(comMotivo, matched)).toEqual([
      { id: "l2", label: "Manteiga sem sal", step: "Marcar como conferido", field: "check", tone: "watch" },
    ]);
  });

  it("entrada sem nota não tem atalho: cada item pede o ok", () => {
    const view = receiptExceptionView(previews([line()], "manual"), "manual", 0, null);
    expect(view.available).toBe(false);
    expect(receiptVolumesStep(view)).toBe("");
  });
});

describe("diferença", () => {
  it("nota × chegou × diferença, e a consequência escrita", () => {
    const preview = previews([manteigaLine({ purchaseQty: 3 })])[0]!;
    expect(receiptLineDifference(preview.line)).toEqual({ invoiceQty: 4, arrivedQty: 3, difference: -1 });
    expect(receiptDifferenceConsequence(preview)).toBe("Entra 3 × caixa 5 kg. A falta fica anotada na entrada para cobrar o fornecedor.");
    expect(receiptLineDifference(manteigaLine())).toBeNull();
  });
});

describe("atalhos de validade", () => {
  it("a da última entrega (enquanto vale) e a típica do insumo, com o dia da semana", () => {
    expect(receiptExpiryShortcuts(manteiga, "2026-10-03")).toEqual([
      { key: "last", label: "Mesma da última entrega", date: "2026-10-12", caption: "12/10 · seg" },
      { key: "typical", label: "Típica: +7 dias", date: "2026-10-10", caption: "10/10 · sáb" },
    ]);
  });

  it("sem histórico nem vida útil, não inventa atalho", () => {
    expect(receiptExpiryShortcuts({ ...manteiga, lastDeliveryExpiry: "", shelfLifeDays: null }, "2026-10-03")).toEqual([]);
    // Validade da última entrega já vencida não serve de atalho.
    expect(receiptExpiryShortcuts({ ...manteiga, lastDeliveryExpiry: "2026-10-01" }, "2026-10-03").map((item) => item.key)).toEqual(["typical"]);
  });
});
