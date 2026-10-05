import { mountSuspended } from "@nuxt/test-utils/runtime";
import { afterEach, describe, expect, it } from "vitest";
import type { VueWrapper } from "vue";

import OperatorDayPicker from "../../app/components/OperatorDayPicker.vue";
import OperatorPeriodPicker from "../../app/components/OperatorPeriodPicker.vue";
import UiDateField from "../../app/components/UiDateField.vue";

// Os dois controles de data da casa (decisão do dono, 02/10/2026), testados na fonte.
// 01/10/2026 é quinta-feira.
const TODAY = "2026-10-01";

const mounted: VueWrapper[] = [];
async function mount(component: Parameters<typeof mountSuspended>[0], options: Parameters<typeof mountSuspended>[1] = {}) {
  const wrapper = await mountSuspended(component, options);
  mounted.push(wrapper as unknown as VueWrapper);
  return wrapper;
}
afterEach(() => {
  for (const wrapper of mounted.splice(0)) wrapper.unmount();
});

describe("OperatorDayPicker (Tipo 1)", () => {
  it("quatro botões de 44 px: Hoje, Amanhã, a próxima data nominada e Outra data", async () => {
    const wrapper = await mount(OperatorDayPicker, { props: { modelValue: "", today: TODAY, min: TODAY } });
    const radios = wrapper.findAll('[role="radio"]');
    expect(radios).toHaveLength(4);
    expect(radios.map((radio) => radio.attributes("aria-label"))).toEqual([
      "Hoje, Qui 01/10",
      "Amanhã, Sex 02/10",
      "Sábado, 03/10",
      "Outra data, No calendário",
    ]);
    for (const radio of radios) expect(radio.classes()).toContain("min-h-control");
    expect(wrapper.get('[role="radiogroup"]').exists()).toBe(true);
  });

  it("um toque escolhe", async () => {
    const wrapper = await mount(OperatorDayPicker, { props: { modelValue: "", today: TODAY } });
    await wrapper.get('[data-day-option="next"]').trigger("click");
    expect(wrapper.emitted("update:modelValue")).toEqual([["2026-10-03"]]);
  });

  it("dia fechado aparece, não se escolhe, e diz o motivo", async () => {
    const wrapper = await mount(OperatorDayPicker, {
      props: { modelValue: "", today: TODAY, availableDates: ["2026-10-01", "2026-10-03"] },
    });
    const tomorrow = wrapper.get('[data-day-option="tomorrow"]');
    expect(tomorrow.attributes("disabled")).toBeDefined();
    expect(tomorrow.text()).toContain("fechado");
    await tomorrow.trigger("click");
    expect(wrapper.emitted("update:modelValue")).toBeUndefined();
  });

  it("Outra data abre o calendário canônico com min/max, e a data escolhida vira a legenda", async () => {
    const wrapper = await mount(OperatorDayPicker, {
      props: { modelValue: "", today: TODAY, min: TODAY, max: "2026-10-30" },
    });
    expect(wrapper.find("[data-day-other-input]").exists()).toBe(false);
    await wrapper.get('[data-day-option="other"]').trigger("click");
    const input = wrapper.getComponent(UiDateField);
    expect(input.props("min")).toBe(TODAY);
    expect(input.props("max")).toBe("2026-10-30");
    input.vm.$emit("update:modelValue", "2026-10-14");
    await wrapper.vm.$nextTick();
    expect(wrapper.emitted("update:modelValue")).toEqual([["2026-10-14"]]);

    await wrapper.setProps({ modelValue: "2026-10-14" });
    const other = wrapper.get('[data-day-option="other"]');
    expect(other.attributes("aria-checked")).toBe("true");
    expect(other.text()).toContain("Qua 14/10");
  });

  it("Outra data recusa dia fechado com a frase do motivo", async () => {
    const wrapper = await mount(OperatorDayPicker, {
      props: { modelValue: "", today: TODAY, availableDates: ["2026-10-01", "2026-10-20"] },
    });
    await wrapper.get('[data-day-option="other"]').trigger("click");
    const input = wrapper.getComponent(UiDateField);
    input.vm.$emit("update:modelValue", "2026-10-14");
    await wrapper.vm.$nextTick();
    expect(wrapper.emitted("update:modelValue")).toBeUndefined();
    expect(wrapper.get("[data-day-other-error]").text()).toBe("Qua 14/10: fechado. Escolha outro dia.");
  });
});

describe("OperatorPeriodPicker (Tipo 2)", () => {
  it("o botão diz o período; ‹ recua um igual; › para no max", async () => {
    const wrapper = await mount(OperatorPeriodPicker, {
      props: { modelValue: { preset: "day", from: "", to: "" }, today: TODAY, max: TODAY, presets: ["day", "week"] },
    });
    expect(wrapper.get("[data-period-label]").text()).toBe("Hoje, qui 01/10");
    expect(wrapper.get("[data-period-next]").attributes("disabled")).toBeDefined();
    expect(wrapper.find("[data-period-today]").exists()).toBe(false);

    await wrapper.get("[data-period-prev]").trigger("click");
    expect(wrapper.emitted("update:modelValue")).toEqual([[{ preset: "day", from: "2026-09-30", to: "" }]]);
  });

  it("fora de hoje, oferece Voltar para hoje", async () => {
    const wrapper = await mount(OperatorPeriodPicker, {
      props: { modelValue: { preset: "week", from: "2026-09-20", to: "" }, today: TODAY, presets: ["day", "week"] },
    });
    expect(wrapper.get("[data-period-label]").text()).toBe("Semana · 14/09 a 20/09");
    expect(wrapper.get("[data-period-prev]").attributes("aria-label")).toBe("Semana anterior");
    await wrapper.get("[data-period-today]").trigger("click");
    expect(wrapper.emitted("update:modelValue")).toEqual([[{ preset: "week", from: "", to: "" }]]);
  });

  it("o popover mostra só as granularidades declaradas, e Ir para o dia quando não há personalizado", async () => {
    const wrapper = await mount(OperatorPeriodPicker, {
      props: { modelValue: { preset: "day", from: "", to: "" }, today: TODAY, presets: ["day", "week"] },
    });
    await wrapper.get("[data-period-button]").trigger("click");
    const keys = wrapper.findAll("[data-period-preset]").map((chip) => chip.attributes("data-period-preset"));
    expect(keys).toEqual(["day", "week"]);
    expect(wrapper.find("[data-period-custom-from]").exists()).toBe(false);

    await wrapper.get("[data-period-preset=\"week\"]").trigger("click");
    expect(wrapper.emitted("update:modelValue")![0]).toEqual([{ preset: "week", from: "", to: "" }]);
  });

  it("personalizado aplica o intervalo", async () => {
    const wrapper = await mount(OperatorPeriodPicker, {
      props: {
        modelValue: { preset: "28d", from: "", to: "" },
        today: TODAY,
        max: TODAY,
        presets: ["day", "week", "month", "year", "7d", "28d", "max"],
        custom: true,
      },
    });
    await wrapper.get("[data-period-button]").trigger("click");
    const fields = wrapper.findAllComponents(UiDateField);
    fields[0]!.vm.$emit("update:modelValue", "2026-09-10");
    fields[1]!.vm.$emit("update:modelValue", "2026-09-01");
    await wrapper.vm.$nextTick();
    await wrapper.get("[data-period-custom-apply]").trigger("click");
    expect(wrapper.emitted("update:modelValue")).toEqual([[{ preset: "custom", from: "2026-09-01", to: "2026-09-10" }]]);
  });

  it("os quatro grupos na ordem da casa: Período, Próximos, Últimos, Personalizado", async () => {
    const wrapper = await mount(OperatorPeriodPicker, {
      props: {
        modelValue: { preset: "week", from: "", to: "" },
        today: TODAY,
        presets: ["day", "week", "7d", "next7d", "next14d"],
        custom: true,
      },
    });
    await wrapper.get("[data-period-button]").trigger("click");
    const popover = wrapper.get("[data-period-popover]");
    const headings = popover.findAll("p").map((p) => p.text());
    expect(headings).toEqual(["Período", "Próximos", "Últimos", "Personalizado"]);
    const keys = wrapper.findAll("[data-period-preset]").map((chip) => chip.attributes("data-period-preset"));
    expect(keys).toEqual(["day", "week", "next7d", "next14d", "7d"]);
    // O chip diz "7D" dentro do grupo; o nome acessível diz para que lado.
    expect(wrapper.get('[data-period-preset="next7d"]').attributes("aria-label")).toBe("Próximos 7 dias");
    expect(wrapper.get('[data-period-preset="7d"]').attributes("aria-label")).toBe("Últimos 7 dias");

    await wrapper.get('[data-period-preset="next7d"]').trigger("click");
    expect(wrapper.emitted("update:modelValue")![0]).toEqual([{ preset: "next7d", from: "", to: "" }]);
  });

  it("Próximos 7 dias: o botão diz a janela e ‹ fica parado em hoje", async () => {
    const wrapper = await mount(OperatorPeriodPicker, {
      props: { modelValue: { preset: "next7d", from: "", to: "" }, today: TODAY, presets: ["day", "next7d"] },
    });
    expect(wrapper.get("[data-period-label]").text()).toBe("Próximos 7 dias · 01/10 a 07/10");
    expect(wrapper.get("[data-period-prev]").attributes("disabled")).toBeDefined();
    await wrapper.get("[data-period-next]").trigger("click");
    expect(wrapper.emitted("update:modelValue")).toEqual([[{ preset: "next7d", from: "2026-10-08", to: "" }]]);
  });

  it("o personalizado recusa o intervalo acima do teto, com o motivo", async () => {
    const wrapper = await mount(OperatorPeriodPicker, {
      props: {
        modelValue: { preset: "week", from: "", to: "" },
        today: TODAY,
        presets: ["day", "week"],
        custom: true,
        maxSpanDays: 62,
      },
    });
    await wrapper.get("[data-period-button]").trigger("click");
    const fields = wrapper.findAllComponents(UiDateField);
    fields[0]!.vm.$emit("update:modelValue", "2026-10-01");
    fields[1]!.vm.$emit("update:modelValue", "2026-12-31");
    await wrapper.vm.$nextTick();
    expect(wrapper.get("[data-period-custom-error]").text()).toBe("No máximo 62 dias por vez.");
    expect(wrapper.get("[data-period-custom-apply]").attributes("disabled")).toBeDefined();
    await wrapper.get("[data-period-custom-apply]").trigger("click");
    expect(wrapper.emitted("update:modelValue")).toBeUndefined();

    fields[1]!.vm.$emit("update:modelValue", "2026-11-30");
    await wrapper.vm.$nextTick();
    expect(wrapper.find("[data-period-custom-error]").exists()).toBe(false);
    await wrapper.get("[data-period-custom-apply]").trigger("click");
    expect(wrapper.emitted("update:modelValue")).toEqual([[{ preset: "custom", from: "2026-10-01", to: "2026-11-30" }]]);
  });
});
