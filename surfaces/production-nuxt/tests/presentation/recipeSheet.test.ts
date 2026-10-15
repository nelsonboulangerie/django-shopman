import { describe, expect, it } from "vitest";

import {
  addSheetItem,
  emptySheetDraft,
  emptySheetItem,
  itemFromProjection,
  massBalancePreview,
  moveSheetItem,
  removeSheetItem,
  sheetDraftError,
  sheetItemKg,
  sheetPayloadFromDraft,
  sheetQuery,
  sheetSlug,
  updateSheetItem,
} from "~/presentation/recipeSheet";

describe("recipeSheet: linhas da ficha", () => {
  it("edita a lista sem mutar a original", () => {
    const items = [emptySheetItem({ inputSku: "A", quantity: "1" }), emptySheetItem({ inputSku: "B" })];
    const updated = updateSheetItem(items, 0, { quantity: "2" });
    expect(updated[0]?.quantity).toBe("2");
    expect(items[0]?.quantity).toBe("1");
    expect(removeSheetItem(items, 0).map((item) => item.inputSku)).toEqual(["B"]);
    expect(addSheetItem(items)).toHaveLength(3);
    expect(items).toHaveLength(2);
  });

  it("move a linha e ignora índices fora da faixa", () => {
    const items = [emptySheetItem({ inputSku: "A" }), emptySheetItem({ inputSku: "B" }), emptySheetItem({ inputSku: "C" })];
    expect(moveSheetItem(items, 0, 2).map((item) => item.inputSku)).toEqual(["B", "C", "A"]);
    expect(moveSheetItem(items, 0, 9).map((item) => item.inputSku)).toEqual(["A", "B", "C"]);
  });

  it("lê a linha da projeção para o formulário", () => {
    const item = itemFromProjection({
      input_sku: "FARINHA",
      name: "Farinha",
      quantity: "1.5",
      unit: "kg",
      usable_factor: "0.84",
      gross_quantity: "1.786",
      correction_factor: "1.1905",
      sort_order: 0,
      is_optional: false,
      note: "peneirada",
    });
    expect(item).toEqual({ inputSku: "FARINHA", quantity: "1.5", unit: "kg", usableFactor: "0.84", isOptional: false, note: "peneirada" });
  });
});

describe("recipeSheet: prévia da massa", () => {
  it("converte as unidades de massa para quilos", () => {
    expect(sheetItemKg(emptySheetItem({ quantity: "1", unit: "kg" }))).toBe(1);
    expect(sheetItemKg(emptySheetItem({ quantity: "500", unit: "g" }))).toBe(0.5);
    expect(sheetItemKg(emptySheetItem({ quantity: "500000", unit: "mg" }))).toBe(0.5);
    expect(sheetItemKg(emptySheetItem({ quantity: "1", unit: "L" }))).toBeNull();
    expect(sheetItemKg(emptySheetItem({ quantity: "1", unit: "un" }))).toBeNull();
  });

  it("aprova quando o rendimento cabe, avisa quando passa", () => {
    const items = [emptySheetItem({ inputSku: "F", quantity: "1", unit: "kg" }), emptySheetItem({ inputSku: "A", quantity: "0.7", unit: "kg" })];
    expect(massBalancePreview(items, "1.7", "kg").status).toBe("ok");
    const over = massBalancePreview(items, "2", "kg");
    expect(over.status).toBe("exceeds");
    expect(over.tone).toBe("warning");
    expect(over.totalDisplay).toBe("1,7 kg");
  });

  it("ignora opcionais e não opina quando não dá para comparar", () => {
    const items = [emptySheetItem({ inputSku: "F", quantity: "1", unit: "kg" }), emptySheetItem({ inputSku: "O", quantity: "5", unit: "kg", isOptional: true })];
    expect(massBalancePreview(items, "1", "kg").status).toBe("ok");
    expect(massBalancePreview([emptySheetItem({ quantity: "1", unit: "L" })], "1", "kg").status).toBe("incomparable");
    expect(massBalancePreview(items, "1", "un").status).toBe("incomparable");
    expect(massBalancePreview([], "1", "kg").status).toBe("empty");
  });
});

describe("recipeSheet: corpo do cadastro", () => {
  it("exige nome, SKU, rendimento e linhas válidas", () => {
    const draft = emptySheetDraft();
    draft.name = "Pão";
    draft.outputSku = "PAO";
    draft.batchSize = "1";
    draft.items = [emptySheetItem({ inputSku: "F", quantity: "1", usableFactor: "1" })];
    expect(sheetDraftError(draft)).toBe("");
    expect(sheetDraftError({ ...draft, name: "" })).toContain("nome");
    expect(sheetDraftError({ ...draft, outputSku: "" })).toContain("SKU");
    expect(sheetDraftError({ ...draft, batchSize: "0" })).toContain("rendimento");
    expect(sheetDraftError({ ...draft, items: [emptySheetItem({ inputSku: "", quantity: "1" })] })).toContain("linha 1");
    expect(sheetDraftError({ ...draft, items: [emptySheetItem({ inputSku: "F", quantity: "1", usableFactor: "1.2" })] })).toContain("aproveitamento");
    expect(sheetDraftError({ ...draft, shelfLifeReviewed: true, shelfLifeDays: "" })).toContain("validade");
  });

  it("monta o corpo snake/camel e preserva as etapas de mesmo nome", () => {
    const draft = emptySheetDraft();
    draft.name = " Pão Tradição ";
    draft.ref = "pao-tradicao";
    draft.outputSku = "pao-tradicao";
    draft.batchSize = "1,7";
    draft.stepsText = "Mistura\nForno";
    draft.maxStartedMinutes = "90";
    draft.capacityPerDay = "120,5";
    draft.requiresBatchTracking = true;
    draft.shelfLifeDays = "3";
    draft.shelfLifeReviewed = true;
    draft.items = [emptySheetItem({ inputSku: " FARINHA ", quantity: "1,5", unit: "kg", usableFactor: "0,84" })];
    const payload = sheetPayloadFromDraft(draft, [{ name: "Mistura", instructions: "40 min" }]);
    expect(payload.name).toBe("Pão Tradição");
    expect(payload.output_sku).toBe("PAO-TRADICAO");
    expect(payload.batch_size).toBe("1.7");
    expect(payload.items[0]).toEqual({
      input_sku: "FARINHA",
      quantity: "1.5",
      unit: "kg",
      usable_factor: "0.84",
      sort_order: 0,
      is_optional: false,
      note: "",
    });
    expect(payload.steps?.[0]).toEqual({ name: "Mistura", instructions: "40 min" });
    expect(payload.maxStartedMinutes).toBe(90);
    expect(payload.capacityPerDay).toBe("120.5");
    expect(payload.shelfLifeDays).toBe(3);
    expect(payload.productionLifecycle).toBe("");
  });

  it("slugifica o nome como o servidor (sem acento, minúsculo, sem borda)", () => {
    expect(sheetSlug("Pão Tradição (cópia)")).toBe("pao-tradicao-copia");
    expect(sheetSlug("  ")).toBe("");
  });

  it("não envia filtros vazios nem a ordenação padrão", () => {
    expect(sheetQuery("", "", "updated", 1, 48)).toEqual({});
    expect(sheetQuery("pao", "1", "name", 2, 24)).toEqual({ q: "pao", active: "1", sort: "name", page: "2", page_size: "24" });
  });
});
