import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { computed, nextTick, ref, watch } from "vue";
import { mount } from "@vue/test-utils";

import MiseEnPlacePage from "../../app/pages/mise-en-place.vue";
import type { WeighingTicketProjection } from "../../app/types/production";

const tickets = ref<WeighingTicketProjection[]>([]);
const printSpy = vi.fn();
const weighingProjection = ref({
  selected_date: "2026-09-10",
  selected_date_display: "10 set 2026",
  selected_position_ref: "",
  selected_base_recipe: "",
  tickets: [],
  access: {},
  actions: [],
  generated_at: "2026-09-10T10:00:00Z",
  source_revision: "weighing:7",
  fresh_until: "2099-09-10T10:05:00Z",
  contract_version: 1,
  scale_precision_g: "2",
  scale_precision_display: "2 g",
  scale_rounding_note: "Alvos arredondados para cima · balança 2 g",
});

function ticket(
  recipeRef: string,
  name: string,
  blindCode: string,
  ticketRef?: string,
): WeighingTicketProjection {
  return {
    ...(ticketRef ? { ticket_ref: ticketRef } : {}),
    recipe_ref: recipeRef,
    output_sku: recipeRef.toUpperCase(),
    name,
    output_quantity_display: "12 un.",
    dough_weight_display: "2 kg",
    total_weight_display: "2.000 g",
    sources_display: "12 un.",
    blind_code: blindCode,
    made_display: "10/09",
    expiry_display: "11/09",
    ingredients: [
      {
        sku: "FARINHA",
        name: "Farinha",
        quantity_display: "1 kg",
        target_display: "1.000 g",
        is_subrecipe: false,
      },
      {
        sku: "AGUA",
        name: "Água",
        quantity_display: "700 g",
        is_subrecipe: false,
      },
    ],
    table: { contract_version: 1, headers: [], rows: [] },
  };
}

function installGlobals() {
  vi.stubGlobal("computed", computed);
  vi.stubGlobal("ref", ref);
  vi.stubGlobal("watch", watch);
  vi.stubGlobal("useRoute", () => ({ query: {} }));
  vi.stubGlobal("useMiseEnPlace", () => ({
    projection: ref(null),
    lines: ref([]),
    expand: ref(false),
    pending: ref(false),
    error: ref(null),
    refresh: vi.fn(),
    isChecked: () => false,
    toggleChecked: vi.fn(),
    checkedCount: ref(0),
  }));
  vi.stubGlobal("useWeighing", () => ({
    projection: weighingProjection,
    tickets,
    dateDisplay: ref("10 set 2026"),
    pending: ref(false),
    error: ref(null),
    refresh: vi.fn(),
  }));
  vi.stubGlobal("print", printSpy);
}

const stubs = {
  ProductionHeader: true,
  Icon: true,
  NuxtLink: { template: "<a><slot /></a>" },
  UiBadge: { template: "<span><slot /></span>" },
  WeighingLabels: {
    props: ["printMode", "labels", "tickets"],
    template: `
      <div
        data-testid="print-payload"
        :data-mode="printMode"
        :data-label-count="labels.length"
        :data-ticket-refs="tickets.map((ticket) => ticket.ticket_ref || ticket.recipe_ref).join(',')"
      />
    `,
  },
  ProductionLabelPrintDialog: {
    props: ["open", "printMode", "labels", "tickets"],
    template: `
      <div
        v-if="open"
        data-testid="print-preview"
        :data-mode="printMode"
        :data-label-count="labels.length"
        :data-ticket-refs="tickets.map((ticket) => ticket.ticket_ref || ticket.recipe_ref).join(',')"
      />
    `,
  },
};

beforeEach(() => {
  installGlobals();
  printSpy.mockReset();
  tickets.value = [
    ticket("massa-base", "Massa Croissant", "D8", "ticket-croissant"),
    ticket("massa-base", "Massa Forma", "S5", "ticket-forma"),
  ];
});

afterEach(() => vi.unstubAllGlobals());

describe("Preparação — preview e identificação", () => {
  it("abre em Por preparo e mantém Por insumo como segunda visão", () => {
    const wrapper = mount(MiseEnPlacePage, { global: { stubs } });
    const viewMode = wrapper.get('[aria-label="Modo de visualização"]');
    const buttons = viewMode.findAll("button");

    expect(buttons.map((button) => button.text().trim())).toEqual([
      "Por preparo",
      "Por insumo",
    ]);
    expect(buttons[0]?.attributes("aria-pressed")).toBe("true");
    expect(wrapper.find("article").exists()).toBe(true);
  });

  it("mostra Nome e, na última linha do cabeçalho, SKU · peso total em gramas", () => {
    const wrapper = mount(MiseEnPlacePage, { global: { stubs } });
    const header = wrapper.find("article header");

    expect(header.text()).toContain("Massa Croissant");
    expect(header.text()).toContain("MASSA-BASE · Peso total 2.000 g");
    expect(header.text()).not.toContain("12 un. · MASSA-BASE");
  });

  it("identifica o insumo por Nome + SKU e apresenta kg em gramas", () => {
    const wrapper = mount(MiseEnPlacePage, { global: { stubs } });
    const firstIngredient = wrapper.find("article ul li");

    expect(firstIngredient.text()).toContain("Farinha");
    expect(firstIngredient.text()).toContain("FARINHA");
    expect(firstIngredient.text()).toContain("1.000 g");
    expect(firstIngredient.text()).not.toContain("1 kg");
    expect(wrapper.text()).toContain(
      "Alvos arredondados para cima · balança 2 g",
    );
  });

  it("primeiro toque abre preview do ticket_ref escolhido e não chama window.print", async () => {
    const wrapper = mount(MiseEnPlacePage, { global: { stubs } });

    await wrapper
      .get('button[aria-label="Abrir etiquetas de pesagem de Massa Croissant"]')
      .trigger("click");
    await nextTick();

    const preview = wrapper.get('[data-testid="print-preview"]');
    expect(preview.attributes("data-mode")).toBe("pesagem");
    expect(preview.attributes("data-ticket-refs")).toBe("ticket-croissant");
    expect(preview.attributes("data-label-count")).toBe("2");
    expect(printSpy).not.toHaveBeenCalled();
  });

  it("usa recipe_ref apenas como fallback para um contrato antigo", async () => {
    tickets.value = [ticket("massa-legada", "Massa Legada", "L1")];
    const wrapper = mount(MiseEnPlacePage, { global: { stubs } });

    await wrapper
      .get('button[aria-label="Abrir etiquetas de pesagem de Massa Legada"]')
      .trigger("click");

    expect(
      wrapper
        .get('[data-testid="print-preview"]')
        .attributes("data-ticket-refs"),
    ).toBe("massa-legada");
  });

  it("a ação geral restaura todos os preparos e a explícita preserva o modo", async () => {
    const wrapper = mount(MiseEnPlacePage, { global: { stubs } });

    await wrapper
      .get('button[aria-label="Abrir etiquetas de pesagem de Massa Forma"]')
      .trigger("click");
    await wrapper
      .findAll("button")
      .find((button) => button.text().includes("Etiquetas de pesagem"))!
      .trigger("click");

    let preview = wrapper.get('[data-testid="print-preview"]');
    expect(preview.attributes("data-ticket-refs")).toBe(
      "ticket-croissant,ticket-forma",
    );
    expect(preview.attributes("data-label-count")).toBe("4");

    await wrapper
      .findAll("button")
      .find((button) => button.text().includes("Etiquetas do preparo"))!
      .trigger("click");
    preview = wrapper.get('[data-testid="print-preview"]');
    expect(preview.attributes("data-mode")).toBe("preparo");
    expect(printSpy).not.toHaveBeenCalled();
  });
});
