import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { computed, nextTick, ref, watch } from "vue";
import { enableAutoUnmount, mount } from "@vue/test-utils";

import MiseEnPlacePage from "../../app/pages/mise-en-place.vue";
import type { WeighingTicketProjection } from "../../app/types/production";
import { nuxtUiStubs } from "../support/nuxtUiStubs";
import { weighingRows } from "../../app/presentation/weighing";
import { markFor, type PrepMark } from "../../app/composables/useMiseEnPlace";

const tickets = ref<WeighingTicketProjection[]>([]);
const miseLines = ref<Array<Record<string, unknown>>>([]);
const printSpy = vi.fn();
const serverMarks = ref<PrepMark[]>([]);
const toggleSpy = vi.fn();
const purchaseUrl = ref("https://compras.example/");
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
  vi.stubGlobal("useOperatorLock", () => ({ stationRef: ref("prep-a") }));
  vi.stubGlobal("useMiseEnPlace", () => ({
    projection: computed(() => ({ work_order_count: 1, has_stock_readings: true, purchase_url: purchaseUrl.value })),
    lines: miseLines,
    expand: ref(false),
    pending: ref(false),
    error: ref(null),
    refresh: vi.fn(),
  }));
  vi.stubGlobal("usePrepMarks", () => ({
    marks: serverMarks,
    error: ref(null),
    refresh: vi.fn(),
    isMarked: (itemRef: string, quantity: string) => markFor(serverMarks.value, itemRef, quantity) !== null,
    markOf: (itemRef: string, quantity: string) => markFor(serverMarks.value, itemRef, quantity),
    toggle: toggleSpy,
  }));
  vi.stubGlobal("useOperatorAppLink", () => ({ attrsFor: () => ({}) }));
  vi.stubGlobal("useWeighing", () => ({
    projection: weighingProjection,
    tickets,
    dateDisplay: ref("10 set 2026"),
    pending: ref(false),
    error: ref(null),
    refresh: vi.fn(),
    rowsFor: (ticket: WeighingTicketProjection) => weighingRows(ticket),
  }));
  vi.stubGlobal("print", printSpy);
}

const stubs = {
  ...nuxtUiStubs,
  NuxtSwitch: {
    props: ["modelValue", "label"],
    emits: ["update:modelValue"],
    template: `
      <button
        type="button"
        role="switch"
        :aria-checked="String(modelValue === true)"
        @click="$emit('update:modelValue', modelValue !== true)"
      >{{ label }}</button>
    `,
  },
  ProductionHeader: true,
  Icon: true,
  NuxtLink: { template: "<a><slot /></a>" },
  // A tabela do kit tem teste próprio; aqui ela só desenha as células da tela.
  OperatorTable: {
    props: ["data", "columns", "expandAt", "pinned"],
    template: `
      <table data-mise-lines :data-expand-at="expandAt" :data-pinned="pinned">
        <tr v-for="line in data" :key="line.sku" :data-sku="line.sku">
          <td v-for="column in columns" :key="column.id" :data-column="column.id">
            <slot :name="column.id + '-cell'" :row="{ original: line }" />
          </td>
        </tr>
      </table>
    `,
  },
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
        :data-weights="labels.map((label) => label.weight).join('|')"
        :data-ticket-refs="tickets.map((ticket) => ticket.ticket_ref || ticket.recipe_ref).join(',')"
      />
    `,
  },
};

function line(overrides: Record<string, unknown>) {
  return {
    sku: "X",
    name: "X",
    quantity_display: "100 g",
    unit: "g",
    is_subrecipe: false,
    available_display: "",
    is_short: false,
    missing_display: "",
    breakdown: [],
    annotation: "",
    margin_display: "",
    margin_reason: "",
    ...overrides,
  };
}

async function openInsumos(wrapper: ReturnType<typeof mount>) {
  await wrapper
    .findAll("button")
    .find((button) => button.text().includes("Por insumo"))!
    .trigger("click");
}

beforeEach(() => {
  installGlobals();
  printSpy.mockReset();
  toggleSpy.mockReset();
  serverMarks.value = [];
  purchaseUrl.value = "https://compras.example/";
  miseLines.value = [];
  tickets.value = [
    ticket("massa-base", "Massa Croissant", "D8", "ticket-croissant"),
    ticket("massa-base", "Massa Forma", "S5", "ticket-forma"),
  ];
});

enableAutoUnmount(afterEach);
afterEach(() => vi.unstubAllGlobals());

describe("Preparação — preview e identificação", () => {
  it("abre em Por preparo e mantém Por insumo como segunda visão", () => {
    const wrapper = mount(MiseEnPlacePage, { global: { stubs } });
    const viewMode = wrapper.get('[aria-label="Modo de visualização"]');
    const tabs = viewMode.findAll('[role="tab"]');

    expect(tabs.map((tab) => tab.text().trim())).toEqual([
      "Por preparo",
      "Por insumo",
    ]);
    expect(tabs[0]?.attributes("aria-selected")).toBe("true");
    expect(tabs[1]?.attributes("aria-selected")).toBe("false");
    expect(wrapper.find("article").exists()).toBe(true);
  });

  it("Por insumo: a marca vem do servidor e a frase do dispositivo saiu", async () => {
    miseLines.value = [line({ sku: "FARINHA", name: "Farinha", quantity_display: "1000 g" })];
    serverMarks.value = [
      { item_ref: "FARINHA", quantity: "1000 g", marked_by: "Ana", marked_at: "2026-09-10T05:40:00-03:00" },
    ];
    const wrapper = mount(MiseEnPlacePage, { global: { stubs } });
    await openInsumos(wrapper);

    expect(wrapper.text()).not.toContain("somente");
    expect(wrapper.text()).not.toContain("neste dispositivo");
    expect(wrapper.text()).toContain("1/1 separados");
    expect(wrapper.get('[data-sku="FARINHA"] [role="checkbox"]').attributes("aria-checked")).toBe("true");
    expect(wrapper.get("[data-prep-mark-author]").text()).toContain("Separado por Ana");

    // A caixa é o primeiro gesto: mora na coluna fixada do nome, antes dele; a seta da
    // linha vai para o fim (dono, 26/11).
    const nameCell = wrapper.get('[data-sku="FARINHA"] [data-column="name"]');
    expect(nameCell.element.firstElementChild?.firstElementChild?.querySelector('[role="checkbox"]')).not.toBeNull();
    expect(wrapper.findAll('[data-sku="FARINHA"] td').map((td) => td.attributes("data-column"))).toEqual([
      "name",
      "quantity",
      "available",
    ]);
    expect(wrapper.get("[data-mise-lines]").attributes("data-pinned")).toBe("name");
    expect(wrapper.get("[data-mise-lines]").attributes("data-expand-at")).toBe("end");

    await wrapper.get('[data-sku="FARINHA"] [role="checkbox"]').trigger("click");
    expect(toggleSpy).toHaveBeenCalledWith("FARINHA", "1000 g", "Farinha");
  });

  it("a falta diz quanto e oferece Pedir no Compras; pré-preparo não mostra saldo nem falta", async () => {
    miseLines.value = [
      line({
        sku: "FARINHA",
        name: "Farinha",
        available_display: "700 g",
        is_short: true,
        missing_display: "300 g",
      }),
      line({
        sku: "MASSA-BASE",
        name: "Massa base",
        is_subrecipe: true,
        available_display: "0 g",
        is_short: true,
        missing_display: "300 g",
      }),
    ];
    const wrapper = mount(MiseEnPlacePage, { global: { stubs } });
    await openInsumos(wrapper);

    // A falta mora sob o nome, visível em qualquer largura; o saldo fica na coluna.
    const farinha = wrapper.get('[data-sku="FARINHA"] [data-column="name"]');
    expect(farinha.get("[data-prep-shortage]").text()).toBe("Faltam 300 g");
    const pedir = farinha.get("[data-prep-purchase]");
    expect(pedir.text()).toContain("Pedir no Compras");
    expect(pedir.attributes("href")).toBe("https://compras.example/");
    expect(wrapper.get('[data-sku="FARINHA"] [data-column="available"]').text()).toBe("700 g");

    const massa = wrapper.get('[data-sku="MASSA-BASE"]');
    expect(massa.find("[data-prep-shortage]").exists()).toBe(false);
    expect(massa.get('[data-column="available"]').text()).toBe("");
  });

  it("sem o Compras, a falta continua dita e o atalho não aparece", async () => {
    purchaseUrl.value = "";
    miseLines.value = [
      line({ sku: "FARINHA", name: "Farinha", available_display: "700 g", is_short: true, missing_display: "300 g" }),
    ];
    const wrapper = mount(MiseEnPlacePage, { global: { stubs } });
    await openInsumos(wrapper);

    expect(wrapper.get("[data-prep-shortage]").text()).toBe("Faltam 300 g");
    expect(wrapper.find("[data-prep-purchase]").exists()).toBe(false);
  });

  it("Por preparo também marca, com a chave do preparo e a quantidade da linha", async () => {
    serverMarks.value = [
      { item_ref: "massa-base/FARINHA", quantity: "1 kg", marked_by: "Ana", marked_at: "2026-09-10T05:40:00-03:00" },
    ];
    const wrapper = mount(MiseEnPlacePage, { global: { stubs } });
    const [croissant] = wrapper.findAll("article");
    const boxes = croissant!.findAll('[role="checkbox"]');

    expect(boxes.map((box) => box.attributes("aria-checked"))).toEqual(["true", "false"]);
    expect(croissant!.get("[data-ticket-progress]").text()).toBe("1/2 separados");

    await boxes[1]!.trigger("click");
    expect(toggleSpy).toHaveBeenCalledWith("massa-base/AGUA", "700 g", "Água");
  });

  it("a caixa do Separado tem alvo de 44 px", () => {
    const wrapper = mount(MiseEnPlacePage, {
      global: {
        stubs: {
          ...stubs,
          NuxtCheckbox: { props: ["ui", "size"], template: '<span data-prep-box :data-ui="ui.base" :data-size="size" />' },
        },
      },
    });
    const box = wrapper.get("[data-prep-box]");
    expect(box.attributes("data-ui")).toBe("after:size-11");
    expect(box.attributes("data-size")).toBe("xl");
  });

  it("mostra Nome e, na última linha do cabeçalho, SKU · peso total em gramas", () => {
    const wrapper = mount(MiseEnPlacePage, { global: { stubs } });
    const header = wrapper.find("article header");

    expect(header.text()).toContain("Massa Croissant");
    expect(header.text()).toContain("MASSA-BASE · Peso total 2.000 g");
    expect(header.text()).not.toContain("12 un. · MASSA-BASE");
  });

  it("não há mais interruptor de massa velha: a etiqueta e o cartão pesam a mesma lista", async () => {
    const wrapper = mount(MiseEnPlacePage, { global: { stubs } });
    expect(wrapper.find('[role="switch"]').exists()).toBe(false);
    expect(wrapper.text()).not.toContain("Com massa velha");

    await wrapper
      .get('button[aria-label="Abrir etiquetas de pesagem de Massa Croissant"]')
      .trigger("click");
    expect(wrapper.get('[data-testid="print-preview"]').attributes("data-weights")).toBe(
      "1.000 g|700 g",
    );
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
      .find((button) => button.text().includes("Etiquetas dos preparos"))!
      .trigger("click");
    preview = wrapper.get('[data-testid="print-preview"]');
    expect(preview.attributes("data-mode")).toBe("preparo");
    expect(printSpy).not.toHaveBeenCalled();
  });
});
