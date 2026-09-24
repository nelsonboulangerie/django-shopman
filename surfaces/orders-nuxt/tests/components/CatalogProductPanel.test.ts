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
  fiscal: { profile: "standard", ncm: "", cest: "", unit: "UN" },
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

it("informa rascunho à página para proteger navegação e descarte", async () => {
  const w = panel();
  await w.find('input[type="text"]').setValue("Rascunho para retomar");
  expect(w.emitted("dirty-change")?.at(-1)).toEqual([true]);
  await w.setProps({ open: false });
  expect(w.emitted("dirty-change")?.at(-1)).toEqual([false]);
});

describe("Vendido por peso", () => {
  it("vira kg, o mesmo campo passa a ser o preço do quilo, e avisa que é só no balcão", async () => {
    const w = panel();
    const toggle = w.find('[data-testid="sold-by-weight"] input');
    expect(w.text()).not.toContain("Preço por kg");
    await toggle.setValue(true);
    expect(w.text()).toContain("Preço por kg");
    expect(w.text()).toContain("Vendido só no balcão");
    await w.findAll("button").find(b => b.text() === "Salvar")!.trigger("click");
    expect(w.emitted("save")).toEqual([[{ unit: "kg" }]]);
  });

  it("desligar volta a vender por unidade e o rótulo volta a Preço", async () => {
    const w = panel();
    await w.setProps({ detail: { ...detail, unit: "kg" } });
    await w.find('[data-testid="sold-by-weight"] input').setValue(false);
    expect(w.text()).not.toContain("Preço por kg");
    await w.findAll("button").find(b => b.text() === "Salvar")!.trigger("click");
    expect(w.emitted("save")).toEqual([[{ unit: "un" }]]);
  });
});

describe("Permitir compra", () => {
  it("é gesto na hora, fora do rascunho, e o quadrado espera o servidor", async () => {
    const w = panel();
    await w.setProps({ roles: { purchasable: false, sellable: true, produced: false, used_in_recipe: true } });
    const box = w.find('[data-testid="purchase-toggle"] input[type="checkbox"]');
    expect(w.find('[data-testid="purchase-toggle"]').text()).toContain("Vendável");
    expect(w.find('[data-testid="purchase-toggle"]').text()).toContain("Usado em receita");
    await box.setValue(true);
    expect(w.emitted("set-purchasable")).toEqual([[true]]);
    // Ninguém confirmou ainda: o quadrado volta ao que o servidor diz.
    expect((box.element as HTMLInputElement).checked).toBe(false);
    expect(w.emitted("dirty-change")?.at(-1)).toEqual([false]);
  });

  it("o que é produzido aqui não oferece o interruptor", async () => {
    const w = panel();
    await w.setProps({ roles: { purchasable: false, sellable: true, produced: true, used_in_recipe: false } });
    expect(w.find('[data-testid="purchase-toggle"] input[type="checkbox"]').exists()).toBe(false);
    expect(w.find('[data-testid="purchase-toggle"]').text()).toContain("É produzido aqui");
  });
});

it("mostra mudança de origem mesmo quando o valor não mudou", async () => {
  const w = panel();
  await w.setProps({ detail: { ...detail, allergens: ["leite"], field_sources: { allergens: "recipe" } } });
  await w.setProps({ conflict: { product: { ...detail, allergens: ["leite"], field_sources: { allergens: "manual" } }, conflicting_fields: ["allergens"] } });
  expect(w.text()).toContain("Origem: ficha técnica → edição manual.");
  expect(w.findAll("button").find(button => button.text() === "Salvar")!.attributes("disabled")).toBeDefined();
  expect(w.emitted("save")).toBeUndefined();
});
