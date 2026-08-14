import { describe, expect, it } from "vitest";

import {
  allQuantitiesFilled,
  buildQuantitiesPayload,
  closingBadge,
  pendingStatusDisplay,
  productionRows,
  sanitizeQtyInput,
} from "../app/presentation/closing";
import type { ClosingItemProjection, ClosingPendingProduction } from "../app/types/closing";

const item = (sku: string, classification = "neutral"): ClosingItemProjection => ({
  sku,
  name: sku,
  qty_available: 1,
  classification,
});

describe("presentation/closing — fechamento do dia (contagem cega)", () => {
  it("deriva a badge de classification — o LOTE decide (C4), sem jargão D-1", () => {
    expect(closingBadge("expired").label).toBe("Vira perda");
    expect(closingBadge("mixed").label).toBe("Parte vence");
    expect(closingBadge("keep").label).toBe("Fica");
    expect(closingBadge("unknown").label).toBe("Fica");
    expect(closingBadge("expired").label).not.toContain("D-1");
  });

  it("mapeia production_summary em linhas ordenadas por SKU, com defaults", () => {
    const rows = productionRows({
      croissant: { recipe_ref: "croissant", output_sku: "CROIS", planned: 10, finished: 8, loss: 2 },
      baguete: { recipe_ref: "baguete", output_sku: "BAG", planned: 5, finished: 5 },
    });
    expect(rows).toEqual([
      { sku: "BAG", planned: 5, finished: 5, loss: 0 },
      { sku: "CROIS", planned: 10, finished: 8, loss: 2 },
    ]);
    expect(productionRows(null)).toEqual([]);
  });

  it("marca produção pendente atrasada como o Admin fazia", () => {
    const row = { status_label: "Planejada", is_overdue: true } as ClosingPendingProduction;
    expect(pendingStatusDisplay(row)).toBe("Planejada (atrasada)");
    expect(pendingStatusDisplay({ ...row, is_overdue: false })).toBe("Planejada");
  });

  it("sanitiza a contagem para dígitos", () => {
    expect(sanitizeQtyInput("12a")).toBe("12");
    expect(sanitizeQtyInput("-3")).toBe("3");
    expect(sanitizeQtyInput("")).toBe("");
  });

  it("só libera o envio quando toda linha tem contagem explícita", () => {
    const items = [item("PAO"), item("CROIS")];
    expect(allQuantitiesFilled(items, {})).toBe(false);
    expect(allQuantitiesFilled(items, { PAO: "2" })).toBe(false);
    expect(allQuantitiesFilled(items, { PAO: "2", CROIS: "" })).toBe(false);
    expect(allQuantitiesFilled(items, { PAO: "2", CROIS: "0" })).toBe(true);
    expect(allQuantitiesFilled([], {})).toBe(false);
  });

  it("monta o payload sku→qty normalizado", () => {
    const items = [item("PAO"), item("CROIS")];
    expect(buildQuantitiesPayload(items, { PAO: "02", CROIS: "0" })).toEqual({ PAO: "2", CROIS: "0" });
  });
});
