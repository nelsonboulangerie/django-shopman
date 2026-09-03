import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { computed, ref } from "vue";
import { mount } from "@vue/test-utils";

import FormulaLens from "../../app/components/FormulaLens.vue";
import type { FormulaItemProjection, FormulaLensProjection } from "../../app/types/recipeBook";

// FormulaLens é puro sobre a projection (já formatada pelo servidor). Sem runtime
// Nuxt: reatividade Vue real como globais; Icon/UiBadge viram stubs.

function item(over: Partial<FormulaItemProjection> = {}): FormulaItemProjection {
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

function lens(over: Partial<FormulaLensProjection> = {}): FormulaLensProjection {
  return {
    is_bakery: true,
    anchor_kind: "flour",
    anchor_label: "Farinhas totais",
    basis_display: "1000 g",
    standardized: true,
    anchor_total_display: "1000 g",
    total_mass_display: "1720 g",
    items: [
      item(),
      item({ sku: "AGUA", name: "Água", role: "liquid", role_label: "Líquido", quantity_display: "700 g", quantity_g: "700", pct_display: "70%", is_anchor: false }),
      item({ sku: "", name: "castanha", role: "inclusion", role_label: "Inclusão", quantity_display: "50 g", quantity_g: "50", pct_display: "5%", is_anchor: false, matched: false }),
    ],
    final_mix: [],
    bom: [],
    parts: [],
    metrics: [
      { code: "hydration", label: "Hidratação", value_display: "70%", low_display: "68%", high_display: "80%", max_display: "", tone: "ok", note: "" },
      { code: "salt", label: "Sal", value_display: "3,0%", low_display: "1,8%", high_display: "2,2%", max_display: "2,5%", tone: "warning", note: "" },
    ],
    warnings: [{ code: "part_without_formula", message: "O levain ainda não tem fórmula publicada.", tone: "warning" }],
    ...over,
  };
}

const stubs = {
  Icon: true,
  UiBadge: { template: "<span><slot /></span>" },
};

function mountLens(props: { lens: FormulaLensProjection | null; pending?: boolean; error?: string; compact?: boolean }) {
  return mount(FormulaLens, { props, global: { stubs } });
}

beforeEach(() => {
  vi.stubGlobal("computed", computed);
  vi.stubGlobal("ref", ref);
});
afterEach(() => vi.unstubAllGlobals());

describe("FormulaLens", () => {
  it("renders the anchor line, the g/% table and the unmatched hint", () => {
    const w = mountLens({ lens: lens() });
    const text = w.text();
    expect(text).toContain("Farinhas totais");
    expect(text).toContain("1720 g");
    expect(text).toContain("Padrão da casa");
    expect(w.findAll("tbody tr")).toHaveLength(3);
    expect(text).toContain("70%");
    expect(text).toContain("Sem insumo casado");
    expect(text).toContain("1 ingrediente ainda sem insumo");
  });

  it("shows bakery metrics with the reference range and flags 'fora da faixa' only on warning", () => {
    const w = mountLens({ lens: lens() });
    const text = w.text();
    expect(text).toContain("Hidratação");
    expect(text).toContain("Referência 68% a 80%");
    expect(text).toContain("Referência 1,8% a 2,2% (máx 2,5%)");
    expect(text.match(/fora da faixa/g)).toHaveLength(1);
    expect(text).toContain("O levain ainda não tem fórmula publicada.");
  });

  it("hides the bakery metrics for a non-flour anchor (a cream gets the same screen, another anchor)", () => {
    const w = mountLens({ lens: lens({ is_bakery: false, anchor_kind: "total", anchor_label: "Massa total", metrics: [], standardized: false }) });
    expect(w.text()).not.toContain("Hidratação");
    expect(w.text()).toContain("Como informada");
  });

  it("parts, final mix and BOM appear only when served — and never in compact mode", () => {
    const served = lens({
      parts: [{ sku: "LEVAIN", entry_ref: "levain", name: "Levain", kind: "preferment", kind_label: "Pré-fermento", flour_pct_display: "20%", quantity_display: "400 g", cap_pct_display: "", has_formula: true }],
      final_mix: [item({ quantity_display: "800 g" })],
      bom: [item({ sku: "LEVAIN", name: "Levain", quantity_display: "400 g" })],
    });
    const full = mountLens({ lens: served });
    expect(full.text()).toContain("Partes");
    expect(full.text()).toContain("20% da farinha");
    expect(full.text()).toContain("Mistura final");
    expect(full.text()).toContain("Ficha de execução (BOM)");

    const compact = mountLens({ lens: served, compact: true });
    expect(compact.text()).toContain("Partes");
    expect(compact.text()).not.toContain("Mistura final");
    expect(compact.text()).not.toContain("BOM");

    const bare = mountLens({ lens: lens() });
    expect(bare.text()).not.toContain("Partes");
  });

  it("never renders a blank screen: empty, pending and error states are explicit", () => {
    expect(mountLens({ lens: null }).text()).toContain("Sem prévia ainda");
    expect(mountLens({ lens: null, pending: true }).text()).toContain("Calculando…");
    expect(mountLens({ lens: lens(), error: "Não foi possível calcular a prévia." }).text()).toContain("Não foi possível calcular a prévia.");
    expect(mountLens({ lens: lens({ items: [] }) }).text()).toContain("Nenhum ingrediente ainda.");
  });
});
