import { mountSuspended } from "@nuxt/test-utils/runtime";
import { afterEach, describe, expect, it } from "vitest";
import type { VueWrapper } from "vue";

import OperatorDayPicker from "../../app/components/OperatorDayPicker.vue";
import OperatorPeriodPicker from "../../app/components/OperatorPeriodPicker.vue";

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

  it("Outra data abre o campo nativo com min/max, e a data escolhida vira a legenda", async () => {
    const wrapper = await mount(OperatorDayPicker, {
      props: { modelValue: "", today: TODAY, min: TODAY, max: "2026-10-30" },
    });
    expect(wrapper.find("[data-day-other-input]").exists()).toBe(false);
    await wrapper.get('[data-day-option="other"]').trigger("click");
    const input = wrapper.get("[data-day-other-input]");
    expect(input.attributes("min")).toBe(TODAY);
    expect(input.attributes("max")).toBe("2026-10-30");
    await input.setValue("2026-10-14"); // dispara o `change` do campo de data
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
    const input = wrapper.get("[data-day-other-input]");
    await input.setValue("2026-10-14"); // dispara o `change` do campo de data
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
    await wrapper.get("[data-period-custom-from]").setValue("2026-09-10");
    await wrapper.get("[data-period-custom-to]").setValue("2026-09-01");
    await wrapper.get("[data-period-custom-apply]").trigger("click");
    expect(wrapper.emitted("update:modelValue")).toEqual([[{ preset: "custom", from: "2026-09-01", to: "2026-09-10" }]]);
  });
});
