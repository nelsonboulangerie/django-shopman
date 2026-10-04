import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { computed } from "vue";
import { mount } from "@vue/test-utils";

import PlanReasonCard from "../../app/components/PlanReasonCard.vue";
import type { ProductionSuggestionProjection } from "../../app/types/production";
import { UiButtonStub } from "../support/nativeUiStubs";

// O conteúdo do "Por quê" (UX-P2): cada bloco só aparece quando o backend tem
// o dado. A conta é sempre; histórico, falta de insumo, atalho do Compras e a
// alternativa que cabe no estoque dependem do que a projeção trouxe.

function suggestion(
  over: Partial<ProductionSuggestionProjection> = {},
): ProductionSuggestionProjection {
  return {
    recipe_pk: 1,
    recipe_ref: "croissant",
    recipe_name: "Croissant",
    base_usages: [],
    output_sku: "CRO",
    quantity: "52",
    committed: "6",
    avg_demand: "44.0",
    confidence: "Média",
    sample_size: 4,
    high_demand_applied: false,
    projected: "44",
    margin: "2",
    safety_percent: 4,
    same_weekday: true,
    season_label: "",
    season_fallback: false,
    current_season_label: "",
    soldout_days: 0,
    waste_percent: 0,
    waste_discounted: false,
    material_shortages: [],
    fits_quantity: "",
    ...over,
  };
}

const butter = {
  sku: "MANTEIGA",
  name: "Manteiga",
  missing_display: "1200 g",
  fits_quantity: "40",
};

const attrsFor = vi.fn(() => ({ target: "_blank", rel: "noopener" }));

function mountCard(
  s: ProductionSuggestionProjection,
  over: Partial<{
    purchaseUrl: string;
    canPlanSuggested: boolean;
    canPlanManual: boolean;
  }> = {},
) {
  return mount(PlanReasonCard, {
    props: {
      suggestion: s,
      productName: "Croissant Manteiga",
      isoDate: "2026-10-03",
      purchaseUrl: "",
      canPlanSuggested: true,
      canPlanManual: true,
      ...over,
    },
    global: {
      stubs: {
        Icon: true,
        OperatorKbd: { template: "<kbd><slot /></kbd>" },
        UiButton: UiButtonStub,
      },
    },
  });
}

const button = (w: ReturnType<typeof mountCard>, text: string) =>
  w.findAll("button").find((el) => el.text().trim() === text);

beforeEach(() => {
  vi.stubGlobal("computed", computed);
  vi.stubGlobal("useOperatorAppLink", () => ({ attrsFor }));
});
afterEach(() => vi.unstubAllGlobals());

describe("PlanReasonCard", () => {
  it("só a conta, quando não há mais nada a dizer", () => {
    const w = mountCard(suggestion());

    expect(w.text()).toContain("Por que 52");
    expect(w.text()).toContain("confiança média · 4 sábados de histórico");
    const math = w.find('[data-testid="reason-math"]').text();
    expect(math).toContain("média dos sábados");
    expect(math).toContain("encomendas");
    expect(math).toContain("margem");
    expect(math).toContain("sugestão");
    expect(w.find('[data-testid="reason-margin-note"]').text()).toBe(
      "Margem: segurança 4%",
    );
    expect(w.find('[data-testid="reason-history"]').exists()).toBe(false);
    expect(w.find('[data-testid="reason-material"]').exists()).toBe(false);
    expect(button(w, "Planejar 52")).toBeDefined();
  });

  it("o histórico curto aparece quando houve esgotamento ou sobra", () => {
    const w = mountCard(
      suggestion({
        soldout_days: 3,
        waste_percent: 18,
        waste_discounted: true,
      }),
    );

    const history = w.find('[data-testid="reason-history"]').text();
    expect(history).toContain(
      "Acabou antes de fechar em 3 dos 4 sábados usados na conta",
    );
    expect(history).toContain("Sobrou 18% do que vendeu");
    expect(history).toContain("a média já desconta essa sobra");
  });

  it("a falta de insumo traz o atalho do Compras e a alternativa que cabe", async () => {
    const w = mountCard(
      suggestion({ material_shortages: [butter], fits_quantity: "40" }),
      { purchaseUrl: "https://compras.example/" },
    );

    const material = w.find('[data-testid="reason-material"]');
    expect(material.text()).toContain("Manteiga: dá para 40; faltam 1200 g");
    const link = material.find("a");
    expect(link.text()).toContain("Pedir no Compras");
    expect(link.attributes("href")).toBe("https://compras.example/");
    expect(link.attributes("rel")).toBe("noopener");

    // Com a alternativa à mão, ela é a ação do detalhe.
    expect(button(w, "Planejar 52")).toBeUndefined();
    await button(w, "Planejar 40 (cabe no estoque)")!.trigger("click");
    expect(w.emitted("plan")).toEqual([["40", "manual"]]);
  });

  it("sem URL do Compras, a falta aparece sem o atalho", () => {
    const w = mountCard(
      suggestion({ material_shortages: [butter], fits_quantity: "40" }),
    );

    expect(w.find('[data-testid="reason-material"]').exists()).toBe(true);
    expect(w.find('[data-testid="reason-material"] a').exists()).toBe(false);
  });

  it("sem permissão de número próprio, a alternativa não aparece", () => {
    const w = mountCard(
      suggestion({ material_shortages: [butter], fits_quantity: "40" }),
      { canPlanManual: false },
    );

    expect(button(w, "Planejar 40 (cabe no estoque)")).toBeUndefined();
    expect(button(w, "Planejar 52")).toBeDefined();
  });

  it("quem não planeja só lê", () => {
    const w = mountCard(suggestion(), {
      canPlanSuggested: false,
      canPlanManual: false,
    });

    expect(button(w, "Planejar 52")).toBeUndefined();
    expect(button(w, "Fechar")).toBeDefined();
  });

  it("Planejar N emite a sugestão; Fechar e o X fecham", async () => {
    const w = mountCard(suggestion());

    await button(w, "Planejar 52")!.trigger("click");
    await button(w, "Fechar")!.trigger("click");
    await w.find('button[aria-label="Fechar"]').trigger("click");

    expect(w.emitted("plan")).toEqual([["52", "suggested"]]);
    expect(w.emitted("close")).toHaveLength(2);
  });
});
