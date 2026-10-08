import { mountSuspended } from "@nuxt/test-utils/runtime";
import { DOMWrapper, flushPromises } from "@vue/test-utils";
import { afterEach, describe, expect, it } from "vitest";
import { nextTick, type VueWrapper } from "vue";

import FilterBar from "../../app/components/FilterBar.vue";
import UiDateField from "../../app/components/UiDateField.vue";
import type { ActiveFilters, FilterDimension } from "../../app/types/filters";

// O filtro universal no DOM: "+ Filtro" → campo → valores; chip que reabre a edição
// do próprio campo; busca na lista longa; campo digitado com "Aplicar".

const dimensions: FilterDimension[] = [
  {
    id: "payment",
    label: "Pagamento",
    type: "multi-select",
    options: [
      { value: "pix", label: "Pix", count: 12 },
      { value: "card", label: "Cartão", count: 7 },
    ],
  },
  {
    id: "channel",
    label: "Canal",
    type: "multi-select",
    options: Array.from({ length: 9 }, (_, i) => ({
      value: `c${i}`,
      label: i === 4 ? "iFood" : `Canal ${i}`,
    })),
  },
  {
    id: "customer",
    label: "Cliente",
    type: "text",
    options: [],
    placeholder: "Nome ou telefone",
  },
  { id: "closed", label: "Fechado em", type: "date-range", options: [] },
];

const mounted: VueWrapper[] = [];
const dom = (selector: string) =>
  new DOMWrapper(document.querySelector(selector) as Element);
async function click(selector: string) {
  (document.querySelector(selector) as HTMLElement).click();
  await nextTick();
}

async function mountBar(initial: ActiveFilters = {}) {
  const updates: ActiveFilters[] = [];
  const wrapper = await mountSuspended(FilterBar, {
    props: {
      dimensions,
      modelValue: initial,
      "onUpdate:modelValue": (value: ActiveFilters) => {
        updates.push(value);
        wrapper.setProps({ modelValue: value });
      },
    },
  });
  mounted.push(wrapper as unknown as VueWrapper);
  return { wrapper, updates };
}

afterEach(() => {
  for (const wrapper of mounted.splice(0)) wrapper.unmount();
});

describe("FilterBar universal", () => {
  it("marca vários valores sem fechar e mostra a contagem de cada um", async () => {
    const { wrapper, updates } = await mountBar();
    await wrapper.get("[data-filter-trigger]").trigger("click");
    await click('[data-filter-dimension="payment"]');
    expect(dom('[data-filter-option="payment:pix"]').text()).toContain("12");
    await click('[data-filter-option="payment:pix"]');
    await click('[data-filter-option="payment:card"]');
    expect(updates.at(-1)).toEqual({ payment: ["pix", "card"] });
    expect(document.querySelector("[data-filter-panel]")).not.toBeNull();
    expect(wrapper.get('[data-filter-chip="payment"]').text()).toContain(
      "Pagamento: Pix, Cartão",
    );
  });

  it("tocar no chip reabre a edição daquele campo", async () => {
    const { wrapper } = await mountBar({ payment: ["pix"] });
    expect(wrapper.find("[data-filter-panel]").exists()).toBe(false);
    await wrapper
      .get('[data-filter-chip="payment"] [data-filter-edit]')
      .trigger("click");
    expect(dom("[data-filter-panel]").attributes("aria-label")).toBe(
      "Filtrar por Pagamento",
    );
    expect(
      dom('[data-filter-option="payment:pix"]').attributes("aria-pressed"),
    ).toBe("true");
  });

  it("lista longa ganha busca", async () => {
    const { wrapper } = await mountBar();
    await wrapper.get("[data-filter-trigger]").trigger("click");
    await click('[data-filter-dimension="channel"]');
    await dom("[data-filter-search]").setValue("ifo");
    expect(
      [...document.querySelectorAll<HTMLElement>("[data-filter-option]")].map(
        (o) => o.textContent,
      ),
    ).toEqual(["iFood"]);
  });

  it("campo de texto e intervalo de data aplicam no Aplicar, e vários campos convivem", async () => {
    const { wrapper, updates } = await mountBar({ payment: ["pix"] });
    await wrapper.get("[data-filter-trigger]").trigger("click");
    await click('[data-filter-dimension="customer"]');
    await dom('[data-filter-input="text"]').setValue("maria");
    await dom("[data-filter-form]").trigger("submit");
    await flushPromises();
    expect(updates.at(-1)).toEqual({ payment: ["pix"], customer: ["maria"] });
    expect(wrapper.find("[data-filter-panel]").exists()).toBe(false);

    await wrapper.get("[data-filter-trigger]").trigger("click");
    await click('[data-filter-dimension="closed"]');
    // Data é o campo canônico, não o nativo. O InputDate do Nuxt UI guarda o valor
    // num <input type="date"> escondido (aria-hidden, só para o formulário); o que
    // não pode haver é um nativo que o operador veja e toque.
    expect(document.querySelector("[data-filter-panel]")).not.toBeNull();
    expect(
      document.querySelector('[data-filter-panel] input[type="date"]:not([aria-hidden="true"])'),
    ).toBeNull();
    const dates = wrapper.findAllComponents(UiDateField);
    expect(dates).toHaveLength(2);
    dates[0]!.vm.$emit("update:modelValue", "2026-10-01");
    await nextTick();
    await dom("[data-filter-form]").trigger("submit");
    await flushPromises();
    expect(updates.at(-1)).toEqual({
      payment: ["pix"],
      customer: ["maria"],
      closed: ["2026-10-01", ""],
    });
    expect(wrapper.get('[data-filter-chip="closed"]').text()).toContain(
      "Fechado em: a partir de 01/10",
    );
  });

  it("× remove um campo e Limpar filtros tira todos", async () => {
    const { wrapper, updates } = await mountBar({
      payment: ["pix"],
      customer: ["ana"],
    });
    await wrapper
      .get('[data-filter-chip="customer"] [data-filter-remove]')
      .trigger("click");
    expect(updates.at(-1)).toEqual({ payment: ["pix"] });
    await wrapper.get("[data-filter-clear]").trigger("click");
    expect(updates.at(-1)).toEqual({});
  });
});
