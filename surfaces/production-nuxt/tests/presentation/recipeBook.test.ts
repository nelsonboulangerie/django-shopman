import { describe, expect, it } from "vitest";

import {
  addItem,
  addPart,
  anchorLabel,
  anchorTotalOf,
  bookQuery,
  compareQuery,
  comparePath,
  downscaleTarget,
  emptyFormula,
  emptyItem,
  emptyPart,
  errorField,
  filterEntries,
  formatNumber,
  formulaFromDraft,
  formulaFromServed,
  formulaHasFlour,
  gramsLabel,
  itemFromCapture,
  itemGrams,
  kindLabel,
  moveItem,
  originLines,
  outputMediaType,
  parseVersionRef,
  partKindLabel,
  pctOf,
  removeItem,
  removePart,
  roleLabel,
  setAnchor,
  splitDataUrl,
  statusBadgeVariant,
  statusTone,
  stepsFromText,
  stepsToText,
  suggestedAnchor,
  toneChip,
  toneClass,
  totalMassOf,
  unmatchedItems,
  updateItem,
  updatePart,
  versionRefLabel,
} from "../../app/presentation/recipeBook";
import type {
  CaptureItemProjection,
  Formula,
  FormulaItemProjection,
  RecipeCaptureDraftProjection,
  RecipeEntryCardProjection,
} from "../../app/types/recipeBook";

// ── Fixtures ────────────────────────────────────────────────────────────────
function formula(over: Partial<Formula> = {}): Formula {
  return {
    anchor: { kind: "flour" },
    basis_g: null,
    standardized: false,
    items: [
      emptyItem({ sku: "FARINHA-T65", name: "Farinha T65", role: "flour", quantity: 900, unit: "g" }),
      emptyItem({ sku: "", name: "farinha de centeio", role: "flour", quantity: 100, unit: "g" }),
      emptyItem({ sku: "AGUA", name: "Água", role: "liquid", quantity: 0.7, unit: "kg" }),
      emptyItem({ sku: "SAL", name: "Sal", role: "salt", quantity: 20, unit: "g" }),
    ],
    parts: [],
    ...over,
  };
}

function card(over: Partial<RecipeEntryCardProjection> = {}): RecipeEntryCardProjection {
  return {
    ref: "pao-campanha",
    name: "Pão de campanha",
    kind: "bread",
    kind_label: "Pão",
    output_sku: "PAO-CAMP",
    output_name: "Pão de campanha 800 g",
    has_ficha: true,
    current_version_number: 2,
    version_count: 3,
    draft_count: 0,
    anchor_kind: "flour",
    hydration_display: "72%",
    updated_at_display: "hoje 08:10",
    is_archived: false,
    ...over,
  };
}

function captureItem(over: Partial<CaptureItemProjection> = {}): CaptureItemProjection {
  return {
    name: "Farinha T65",
    original_text: "farine T65",
    quantity: "1000",
    unit: "g",
    role: "flour",
    sku: "FARINHA-T65",
    match_confidence: "alta",
    candidates: [],
    ...over,
  };
}

function draft(over: Partial<RecipeCaptureDraftProjection> = {}): RecipeCaptureDraftProjection {
  return {
    name: "Pain de campagne",
    kind: "bread",
    language: "fr",
    yield_quantity: "2",
    yield_unit: "kg",
    items: [
      captureItem(),
      captureItem({ name: "Eau", original_text: "eau", quantity: "700", unit: "ml", role: "liquid", sku: "AGUA" }),
      captureItem({ name: "Sel", original_text: "sel", quantity: "20", role: "salt", sku: "" }),
    ],
    steps: ["Autolyse 40 min", "Pétrir"],
    notes: "",
    formula: {},
    ...over,
  };
}

function lensItem(over: Partial<FormulaItemProjection> = {}): FormulaItemProjection {
  return {
    sku: "FARINHA-T65",
    name: "Farinha T65",
    role: "flour",
    role_label: "Farinha",
    quantity_display: "1000 g",
    quantity_g: "1000",
    unit: "g",
    pct_display: "100%",
    is_anchor: true,
    matched: true,
    ...over,
  };
}

// ── Vocabulário e tom ───────────────────────────────────────────────────────
describe("labels", () => {
  it("translates roles, kinds, part kinds and anchors; unknown falls to a calm default", () => {
    expect(roleLabel("flour")).toBe("Farinha");
    expect(roleLabel("liquid")).toBe("Líquido");
    expect(roleLabel("weird")).toBe("Outro");
    expect(kindLabel("bread")).toBe("Pão");
    expect(kindLabel("sweet_dough")).toBe("Massa doce");
    expect(kindLabel("nope")).toBe("Outra");
    expect(partKindLabel("old_dough")).toBe("Massa velha");
    expect(partKindLabel("custom")).toBe("custom");
    expect(anchorLabel("flour")).toBe("Farinhas totais");
  });

  it("maps version status to tone and badge variant", () => {
    expect(statusTone("draft")).toBe("warning");
    expect(statusTone("published")).toBe("ok");
    expect(statusTone("superseded")).toBe("muted");
    expect(statusBadgeVariant("draft")).toBe("warning");
    expect(statusBadgeVariant("published")).toBe("success");
    expect(statusBadgeVariant("superseded")).toBe("outline");
  });

  it("only the warning tone carries saturated color", () => {
    expect(toneClass("warning")).toContain("amber");
    expect(toneClass("ok")).not.toContain("amber");
    expect(toneClass("muted")).toContain("muted-foreground");
    expect(toneChip("warning")).toContain("amber");
    expect(toneChip("muted")).toContain("bg-muted");
  });
});

// ── <ref>@<n> ───────────────────────────────────────────────────────────────
describe("versionRefLabel / parseVersionRef", () => {
  it("builds and parses the canonical version reference", () => {
    expect(versionRefLabel("croissant", 3)).toBe("croissant@3");
    expect(parseVersionRef("croissant@3")).toEqual({ ref: "croissant", number: 3 });
    expect(parseVersionRef("pao-de-queijo@12")).toEqual({ ref: "pao-de-queijo", number: 12 });
  });

  it("rejects malformed references", () => {
    expect(parseVersionRef("croissant")).toBeNull();
    expect(parseVersionRef("@3")).toBeNull();
    expect(parseVersionRef("croissant@0")).toBeNull();
    expect(parseVersionRef("croissant@x")).toBeNull();
    expect(parseVersionRef("")).toBeNull();
  });
});

// ── Fórmula: vazio e edição imutável ────────────────────────────────────────
describe("emptyFormula and immutable edits", () => {
  it("starts empty with the requested anchor", () => {
    expect(emptyFormula()).toEqual({ anchor: { kind: "flour" }, basis_g: null, standardized: false, items: [], parts: [] });
    expect(emptyFormula("total").anchor).toEqual({ kind: "total" });
    expect(emptyFormula("ingredient", "LEITE").anchor).toEqual({ kind: "ingredient", sku: "LEITE" });
  });

  it("addItem/updateItem/removeItem never mutate the input", () => {
    const base = formula();
    const added = addItem(base, emptyItem({ name: "Levain", role: "other", quantity: 200 }));
    expect(added.items).toHaveLength(5);
    expect(base.items).toHaveLength(4);

    const updated = updateItem(base, 1, { sku: "FARINHA-CENTEIO" });
    expect(updated.items[1]?.sku).toBe("FARINHA-CENTEIO");
    expect(base.items[1]?.sku).toBe("");
    expect(updated.items[0]).toBe(base.items[0]);

    const removed = removeItem(base, 0);
    expect(removed.items.map((item) => item.name)).toEqual(["farinha de centeio", "Água", "Sal"]);
    expect(base.items).toHaveLength(4);
  });

  it("ignores out-of-range indexes (returns the same formula)", () => {
    const base = formula();
    expect(updateItem(base, 9, { sku: "X" })).toBe(base);
    expect(removeItem(base, -1)).toBe(base);
    expect(moveItem(base, 0, 9)).toBe(base);
    expect(moveItem(base, 2, 2)).toBe(base);
  });

  it("moveItem reorders without losing anything", () => {
    const base = formula();
    const moved = moveItem(base, 3, 0);
    expect(moved.items.map((item) => item.name)).toEqual(["Sal", "Farinha T65", "farinha de centeio", "Água"]);
    expect(base.items[0]?.name).toBe("Farinha T65");
    expect(moveItem(base, 0, 3).items.map((item) => item.name)).toEqual(["farinha de centeio", "Água", "Sal", "Farinha T65"]);
  });

  it("parts follow the same immutable discipline", () => {
    const base = formula();
    const withPart = addPart(base, emptyPart("preferment"));
    expect(withPart.parts).toHaveLength(1);
    expect(base.parts).toHaveLength(0);
    const set = updatePart(withPart, 0, { sku: "LEVAIN", flour_pct: 20 });
    expect(set.parts[0]).toMatchObject({ kind: "preferment", sku: "LEVAIN", flour_pct: 20 });
    expect(withPart.parts[0]?.sku).toBe("");
    expect(removePart(set, 0).parts).toHaveLength(0);
    expect(emptyPart("old_dough")).toEqual({ kind: "old_dough", cap_pct: 20 });
  });

  it("setAnchor keeps the sku only for the ingredient anchor", () => {
    const base = formula();
    expect(setAnchor(base, "ingredient", "AGUA").anchor).toEqual({ kind: "ingredient", sku: "AGUA" });
    expect(setAnchor(base, "total", "AGUA").anchor).toEqual({ kind: "total" });
  });

  it("suggests the flour anchor only when there is flour", () => {
    expect(formulaHasFlour(formula())).toBe(true);
    expect(suggestedAnchor(formula())).toBe("flour");
    const cream = formula({ items: [emptyItem({ name: "Leite", role: "dairy", quantity: 500 })] });
    expect(formulaHasFlour(cream)).toBe(false);
    expect(suggestedAnchor(cream)).toBe("total");
  });
});

// ── Feedback imediato ───────────────────────────────────────────────────────
describe("local percentages (editor feedback only)", () => {
  it("converts units to grams like the server does (volume 1.0, count needs grams_per_unit)", () => {
    expect(itemGrams(emptyItem({ quantity: 700, unit: "g" }))).toBe(700);
    expect(itemGrams(emptyItem({ quantity: 0.7, unit: "kg" }))).toBeCloseTo(700);
    expect(itemGrams(emptyItem({ quantity: 700, unit: "ml" }))).toBe(700);
    expect(itemGrams(emptyItem({ quantity: 0.5, unit: "L", density_g_per_ml: 1.03 }))).toBeCloseTo(515);
    expect(itemGrams(emptyItem({ quantity: 3, unit: "un" }))).toBe(0);
    expect(itemGrams(emptyItem({ quantity: 3, unit: "un", grams_per_unit: 55 }))).toBe(165);
  });

  it("anchorTotalOf follows the anchor kind", () => {
    const base = formula();
    expect(anchorTotalOf(base)).toBe(1000);
    expect(anchorTotalOf(setAnchor(base, "total"))).toBeCloseTo(1720);
    expect(anchorTotalOf(setAnchor(base, "ingredient", "AGUA"))).toBeCloseTo(700);
    expect(totalMassOf(base)).toBeCloseTo(1720);
  });

  it("pctOf formats in pt-BR and stays silent without an anchor", () => {
    const water = formula().items[2]!;
    expect(pctOf(water, 1000)).toBe("70,0");
    expect(pctOf(water, 0)).toBe("");
    expect(pctOf(emptyItem({ quantity: 0 }), 1000)).toBe("");
    expect(formatNumber(72.456, 1)).toBe("72,5");
    expect(gramsLabel(1719.6)).toBe("1720 g");
  });
});

// ── Captura → fórmula ───────────────────────────────────────────────────────
describe("formulaFromDraft", () => {
  it("keeps the matched skus, parses quantities and infers the flour anchor", () => {
    const result = formulaFromDraft(draft());
    expect(result.anchor).toEqual({ kind: "flour" });
    expect(result.items).toHaveLength(3);
    expect(result.items[0]).toMatchObject({ sku: "FARINHA-T65", role: "flour", quantity: 1000, unit: "g", note: "farine T65" });
    expect(result.items[1]).toMatchObject({ sku: "AGUA", unit: "ml", quantity: 700 });
    expect(result.items[2]).toMatchObject({ sku: "", role: "salt" });
    expect(result.standardized).toBe(false);
    expect(result.basis_g).toBeNull();
  });

  it("prefers the anchor and parts the server assembled", () => {
    const result = formulaFromDraft(
      draft({
        formula: { anchor: { kind: "ingredient", sku: "AGUA" }, parts: [{ kind: "old_dough", cap_pct: 15 }], basis_g: 1000, standardized: true },
      }),
    );
    expect(result.anchor).toEqual({ kind: "ingredient", sku: "AGUA" });
    expect(result.parts).toEqual([{ kind: "old_dough", cap_pct: 15 }]);
    expect(result.basis_g).toBe(1000);
    expect(result.standardized).toBe(true);
  });

  it("falls back to the total anchor when nothing is flour", () => {
    const result = formulaFromDraft(draft({ items: [captureItem({ name: "Leite", role: "dairy", sku: "LEITE" })] }));
    expect(result.anchor).toEqual({ kind: "total" });
  });

  it("itemFromCapture tolerates commas, unknown units and roles", () => {
    const item = itemFromCapture(captureItem({ quantity: "1,5", unit: "l", role: "mystery", original_text: "Farinha T65" }));
    expect(item.quantity).toBe(1.5);
    expect(item.unit).toBe("L");
    expect(item.role).toBe("other");
    expect(item.note).toBe("");
  });
});

describe("formulaFromServed", () => {
  it("rebuilds an editable formula from a served version dict", () => {
    const result = formulaFromServed({
      anchor: { kind: "flour" },
      basis_g: 1000,
      standardized: true,
      items: [{ sku: "FARINHA-T65", name: "Farinha T65", role: "flour", quantity: "1000", unit: "g", grams_per_unit: null }],
      parts: [{ sku: "LEVAIN", entry_ref: "levain", kind: "preferment", flour_pct: 20 }],
    });
    expect(result.items[0]).toMatchObject({ sku: "FARINHA-T65", quantity: 1000, unit: "g", role: "flour" });
    expect(result.parts[0]).toMatchObject({ sku: "LEVAIN", flour_pct: 20 });
    expect(result.standardized).toBe(true);
  });

  it("degrades a broken dict to an empty flour formula", () => {
    expect(formulaFromServed({})).toEqual(emptyFormula());
  });
});

describe("steps and unmatched", () => {
  it("round-trips steps through the textarea, dropping blank lines", () => {
    expect(stepsFromText("Autólise 40 min\n\n  Sova  \n")).toEqual(["Autólise 40 min", "Sova"]);
    expect(stepsToText(["a", "b"])).toBe("a\nb");
  });

  it("unmatchedItems lists lens rows without a matched sku", () => {
    const rows = [lensItem(), lensItem({ sku: "", name: "castanha", matched: false }), lensItem({ sku: "X", matched: false })];
    expect(unmatchedItems(rows).map((row) => row.name)).toEqual(["castanha", "Farinha T65"]);
  });

  it("originLines renders what was informed without inventing", () => {
    expect(originLines(null)).toEqual([]);
    expect(originLines({})).toEqual([]);
    expect(
      originLines({
        yield_quantity: "2",
        yield_unit: "kg",
        items: [
          { name: "farine T65", quantity: "1000", unit: "g" },
          { name: "eau", quantity: 700 },
          { garbage: true },
        ],
        text: "ignored when items exist",
      }),
    ).toEqual(["Rendimento 2 kg", "farine T65 — 1000 g", "eau — 700"]);
    expect(originLines({ text: "1 kg farine\n700 g eau\n" })).toEqual(["1 kg farine", "700 g eau"]);
  });

  it("errorField reads the canonical dialect", () => {
    expect(errorField({ detail: "x", field: "output_sku" })).toBe("output_sku");
    expect(errorField({ detail: "x" })).toBe("");
    expect(errorField("nope")).toBe("");
  });
});

// ── Inventário ──────────────────────────────────────────────────────────────
describe("filterEntries", () => {
  const entries = [
    card(),
    card({ ref: "brioche", name: "Brioche", kind: "viennoiserie", output_sku: "", output_name: "", draft_count: 1 }),
    card({ ref: "creme-pat", name: "Creme pâtissier", kind: "cream", output_sku: "CREME-PAT", output_name: "Creme", draft_count: 2 }),
  ];

  it("matches on name, ref, sku and product name, case-insensitively", () => {
    expect(filterEntries(entries, "BRIO", "", false, false).map((e) => e.ref)).toEqual(["brioche"]);
    expect(filterEntries(entries, "creme-pat", "", false, false).map((e) => e.ref)).toEqual(["creme-pat"]);
    expect(filterEntries(entries, "pao-camp", "", false, false).map((e) => e.ref)).toEqual(["pao-campanha"]);
    expect(filterEntries(entries, "800 g", "", false, false).map((e) => e.ref)).toEqual(["pao-campanha"]);
  });

  it("filters by kind and by the two toggles", () => {
    expect(filterEntries(entries, "", "cream", false, false).map((e) => e.ref)).toEqual(["creme-pat"]);
    expect(filterEntries(entries, "", "", true, false).map((e) => e.ref)).toEqual(["brioche"]);
    expect(filterEntries(entries, "", "", false, true).map((e) => e.ref)).toEqual(["brioche", "creme-pat"]);
    expect(filterEntries(entries, "", "", true, true).map((e) => e.ref)).toEqual(["brioche"]);
  });

  it("returns everything with no filters", () => {
    expect(filterEntries(entries, "  ", "", false, false)).toHaveLength(3);
  });

  it("bookQuery omits empty filters", () => {
    expect(bookQuery("", "", false)).toEqual({});
    expect(bookQuery(" pão ", "bread", true)).toEqual({ q: "pão", kind: "bread", archived: "1" });
  });
});

// ── Comparação ──────────────────────────────────────────────────────────────
describe("compareQuery / comparePath", () => {
  it("builds the a/b query in the <ref>@<n> dialect", () => {
    expect(compareQuery("croissant", 2, "croissant", 3)).toEqual({ a: "croissant@2", b: "croissant@3" });
    expect(comparePath("croissant", 2, "brioche", 1)).toBe("/recipes/compare?a=croissant%402&b=brioche%401");
    expect(comparePath("croissant", 2)).toBe("/recipes/compare?a=croissant%402");
  });
});

// ── Foto ────────────────────────────────────────────────────────────────────
describe("downscaleTarget", () => {
  it("never upscales", () => {
    expect(downscaleTarget(800, 600)).toEqual({ width: 800, height: 600, scale: 1 });
    expect(downscaleTarget(1600, 1200)).toEqual({ width: 1600, height: 1200, scale: 1 });
  });

  it("fits the longest edge to 1600 keeping the ratio, in both orientations", () => {
    expect(downscaleTarget(4000, 3000)).toEqual({ width: 1600, height: 1200, scale: 0.4 });
    expect(downscaleTarget(3000, 4000)).toEqual({ width: 1200, height: 1600, scale: 0.4 });
    const odd = downscaleTarget(4032, 3024);
    expect(odd.width).toBe(1600);
    expect(odd.height).toBe(1200);
  });

  it("accepts a custom edge and survives zero", () => {
    expect(downscaleTarget(1000, 500, 100)).toEqual({ width: 100, height: 50, scale: 0.1 });
    expect(downscaleTarget(0, 0)).toEqual({ width: 0, height: 0, scale: 1 });
  });

  it("splits a data url into media type and base64 payload", () => {
    expect(splitDataUrl("data:image/jpeg;base64,AAAA")).toEqual({ media_type: "image/jpeg", data_base64: "AAAA" });
    expect(splitDataUrl("nope")).toBeNull();
    expect(outputMediaType("image/png")).toBe("image/png");
    expect(outputMediaType("image/heic")).toBe("image/jpeg");
  });
});
