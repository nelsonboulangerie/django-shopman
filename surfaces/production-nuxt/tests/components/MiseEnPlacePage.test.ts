import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { computed, nextTick, ref, watch } from "vue";
import { mount } from "@vue/test-utils";

import MiseEnPlacePage from "../../app/pages/mise-en-place.vue";
import type { WeighingTicketProjection } from "../../app/types/production";

const tickets = ref<WeighingTicketProjection[]>([]);
const printSpy = vi.fn();
const printWarningSpy = vi.fn();

function ticket(
  recipeRef: string,
  name: string,
  blindCode: string,
): WeighingTicketProjection {
  return {
    recipe_ref: recipeRef,
    output_sku: recipeRef.toUpperCase(),
    name,
    output_quantity_display: "12 un.",
    dough_weight_display: "2 kg",
    sources_display: "12 un.",
    blind_code: blindCode,
    made_display: "10/09",
    expiry_display: "11/09",
    ingredients: [
      {
        sku: "FARINHA",
        name: "Farinha",
        quantity_display: "1 kg",
        is_subrecipe: false,
      },
      {
        sku: "AGUA",
        name: "Água",
        quantity_display: "700 ml",
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
    tickets,
    dateDisplay: ref("10 set 2026"),
    pending: ref(false),
    error: ref(null),
    refresh: vi.fn(),
  }));
  vi.stubGlobal("useSonner", { warning: printWarningSpy });
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
        :data-ticket-refs="tickets.map((ticket) => ticket.recipe_ref).join(',')"
      />
    `,
  },
};

beforeEach(() => {
  installGlobals();
  printSpy.mockReset();
  printWarningSpy.mockReset();
  tickets.value = [
    ticket("massa-croissant", "Massa Croissant", "D8"),
    ticket("massa-forma", "Massa Forma", "S5"),
  ];
});

afterEach(() => vi.unstubAllGlobals());

describe("Preparação — impressão por preparo", () => {
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

  it("mantém o código junto da identificação e a ação isolada à direita", async () => {
    const wrapper = mount(MiseEnPlacePage, { global: { stubs } });
    await wrapper
      .findAll("button")
      .find((button) => button.text().trim() === "Por preparo")!
      .trigger("click");

    const cardHeader = wrapper.find("article header");
    const leftIdentity = cardHeader.get(":scope > div");
    const printButton = cardHeader.get(":scope > button");

    expect(leftIdentity.text()).toContain("D8");
    expect(leftIdentity.text()).toContain("Massa Croissant");
    expect(printButton.attributes("aria-label")).toBe(
      "Imprimir etiquetas de pesagem de Massa Croissant",
    );
    expect(printButton.classes()).toContain("size-11");
  });

  it("imprime somente as etiquetas de pesagem do cartão escolhido", async () => {
    const wrapper = mount(MiseEnPlacePage, { global: { stubs } });
    await wrapper
      .findAll("button")
      .find((button) => button.text().trim() === "Por preparo")!
      .trigger("click");

    await wrapper
      .get(
        'button[aria-label="Imprimir etiquetas de pesagem de Massa Croissant"]',
      )
      .trigger("click");
    await nextTick();

    const payload = wrapper.get('[data-testid="print-payload"]');
    expect(payload.attributes("data-mode")).toBe("pesagem");
    expect(payload.attributes("data-ticket-refs")).toBe("massa-croissant");
    expect(payload.attributes("data-label-count")).toBe("2");
    expect(printSpy).toHaveBeenCalledTimes(1);
  });

  it("mantém a impressão geral e restaura todos os preparos", async () => {
    const wrapper = mount(MiseEnPlacePage, { global: { stubs } });
    await wrapper
      .findAll("button")
      .find((button) => button.text().trim() === "Por preparo")!
      .trigger("click");

    await wrapper
      .get('button[aria-label="Imprimir etiquetas de pesagem de Massa Forma"]')
      .trigger("click");
    await nextTick();
    await wrapper
      .findAll("button")
      .find((button) => button.text().includes("Etiquetas de pesagem"))!
      .trigger("click");
    await nextTick();

    const payload = wrapper.get('[data-testid="print-payload"]');
    expect(payload.attributes("data-ticket-refs")).toBe(
      "massa-croissant,massa-forma",
    );
    expect(payload.attributes("data-label-count")).toBe("4");
    expect(printSpy).toHaveBeenCalledTimes(2);
  });

  it("monta e envia as etiquetas explícitas de todos os preparos", async () => {
    const wrapper = mount(MiseEnPlacePage, { global: { stubs } });

    await wrapper
      .findAll("button")
      .find((button) => button.text().includes("Etiquetas do preparo"))!
      .trigger("click");
    await nextTick();

    const payload = wrapper.get('[data-testid="print-payload"]');
    expect(payload.attributes("data-mode")).toBe("preparo");
    expect(payload.attributes("data-ticket-refs")).toBe(
      "massa-croissant,massa-forma",
    );
    expect(printSpy).toHaveBeenCalledTimes(1);
    expect(printWarningSpy).not.toHaveBeenCalled();
  });

  it("explica a limitação quando o preview não oferece impressão", async () => {
    vi.stubGlobal("print", undefined);
    const wrapper = mount(MiseEnPlacePage, { global: { stubs } });

    await wrapper
      .findAll("button")
      .find((button) => button.text().includes("Etiquetas do preparo"))!
      .trigger("click");
    await nextTick();

    expect(
      wrapper.get('[data-testid="print-payload"]').attributes("data-mode"),
    ).toBe("preparo");
    expect(printWarningSpy).toHaveBeenCalledWith(
      "Impressão indisponível neste preview.",
      { description: "Abra Produção no Chrome ou Safari para imprimir." },
    );
  });
});
