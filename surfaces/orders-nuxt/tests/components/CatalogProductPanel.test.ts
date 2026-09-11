import { describe, expect, it, vi } from "vitest";
import { computed, reactive, ref, watch } from "vue";
import { mount } from "@vue/test-utils";
import CatalogProductPanel from "../../app/components/CatalogProductPanel.vue";
import type { ProductDetailProjection } from "../../app/types/catalog";

vi.stubGlobal("computed", computed);
vi.stubGlobal("reactive", reactive);
vi.stubGlobal("ref", ref);
vi.stubGlobal("watch", watch);
const detail = {
  sku: "A", name: "Original", base_price_q: 500, unit: "un", availability_policy: "planned_ok",
  is_published: true, is_sellable: true, keywords: [], allergens: [], dietary_info: [],
  short_description: "", long_description: "", image_url: "", storage_tip: "", ingredients_text: "",
  unit_weight_g: null, shelf_life_days: null, production_cycle_hours: null, is_batch_produced: false,
  allows_next_day_sale: false, serves: "", approx_dimensions: "",
  social: { condition: "new", brand: "", gtin: "", mpn: "", google_product_category: "", tiktok_category_id: "", social_caption: "", hashtags: [] },
  fiscal: { profile: "own_production", ncm: "", cest: "", unit: "UN" },
} as ProductDetailProjection;
function panel() {
  return mount(CatalogProductPanel, { props: { open: true, sku: "A", detail, loading: false, busy: false,
    assist: vi.fn(), assistBusy: () => false }, global: { stubs: {
      UiSheet: { template: "<div><slot /></div>" }, UiSheetContent: { template: "<div><slot /></div>" },
      Icon: true, CatalogAiSuggest: true,
    } } });
}

describe("rascunho do produto", () => {
  it("conflito conserva a digitação e aguarda revisão explícita", async () => {
    const w = panel();
    await w.find('input[type="text"]').setValue("Meu rascunho");
    await w.setProps({ conflict: { product: { ...detail, name: "Outra pessoa" }, conflicting_fields: ["name"] } });
    expect((w.find('input[type="text"]').element as HTMLInputElement).value).toBe("Meu rascunho");
    expect(w.text()).toContain("Nome — atual: Outra pessoa");
    expect(w.findAll("button").find(b => b.text() === "Salvar")!.attributes("disabled")).toBeDefined();
    await w.findAll("button").find(b => b.text() === "Manter meu rascunho")!.trigger("click");
    expect(w.emitted("review-conflict")).toEqual([[true]]);
    expect(w.emitted("save")).toBeUndefined();
  });

  it("fechar um rascunho requer descarte explícito e não salva", async () => {
    const w = panel();
    await w.find('input[type="text"]').setValue("Meu rascunho");
    await w.findAll("button").find(b => b.text() === "Cancelar")!.trigger("click");
    expect(w.emitted("update:open")).toBeUndefined();
    await w.findAll("button").find(b => b.text() === "Continuar editando")!.trigger("click");
    expect((w.find('input[type="text"]').element as HTMLInputElement).value).toBe("Meu rascunho");
    await w.findAll("button").find(b => b.text() === "Cancelar")!.trigger("click");
    await w.findAll("button").find(b => b.text() === "Descartar e fechar")!.trigger("click");
    expect(w.emitted("update:open")).toEqual([[false]]);
    expect(w.emitted("save")).toBeUndefined();
  });
});
