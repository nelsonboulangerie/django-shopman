import { mountSuspended } from "@nuxt/test-utils/runtime";
import { DOMWrapper } from "@vue/test-utils";
import { afterEach, describe, expect, it } from "vitest";
import type { VueWrapper } from "vue";

import OperatorDayPicker from "../../app/components/OperatorDayPicker.vue";
import OperatorPeriodPicker from "../../app/components/OperatorPeriodPicker.vue";
import UiDateField from "../../app/components/UiDateField.vue";

// Os dois controles de data da casa (decisão do dono, 02/10/2026), testados na fonte.
// 01/10/2026 é quinta-feira.
const TODAY = "2026-10-01";

const mounted: VueWrapper[] = [];
const dom = (selector: string) => new DOMWrapper(document.querySelector(selector) as Element);
const periodTabs = () => dom("[data-period-popover]").findAll('[role="tab"]');
const presetKeys = () =>
  dom("[data-period-popover]")
    .findAll("[data-period-preset]")
    .map((chip) => chip.attributes("data-period-preset"));
const presetTab = (key: string) =>
  new DOMWrapper(
    document.querySelector(`[data-period-preset="${key}"]`)!.closest('[role="tab"]')!,
  );
// O nome que o leitor de tela lê: o texto do gatilho sem o que é aria-hidden.
function accessibleName(node: DOMWrapper<Element>) {
  const clone = node.element.cloneNode(true) as Element;
  for (const hidden of clone.querySelectorAll('[aria-hidden="true"]')) hidden.remove();
  return clone.textContent?.trim() ?? "";
}
async function activate(node: DOMWrapper<Element>) {
  node.element.dispatchEvent(new MouseEvent("mousedown", { bubbles: true, button: 0 }));
  (node.element as HTMLElement).click();
  await new Promise((resolve) => setTimeout(resolve, 0));
}
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
    expect(presetKeys()).toEqual(["day", "week"]);
    expect(periodTabs().map((tab) => tab.text())).toEqual(["Dia", "Semana"]);
    expect(document.querySelector("[data-period-custom-from]")).toBeNull();
    // Sem personalizado, "Ir para o dia" é o campo canônico de data, com os limites.
    const jump = wrapper.getComponent(UiDateField);
    expect(jump.props("label")).toBe("Data para mostrar");

    await activate(periodTabs()[1]!);
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
    // De e Até são o campo canônico de data (decisão do dono: nunca o nativo).
    // A pilha do Gestor trocou por <NuxtInput type="date"> e este teste passou a
    // exigir o nativo; volta a conferir o componente, com os limites repassados.
    const fields = wrapper.findAllComponents(UiDateField);
    expect(fields).toHaveLength(2);
    expect(fields.map((field) => field.props("label"))).toEqual([
      "Início do período personalizado",
      "Fim do período personalizado",
    ]);
    expect(fields[0]!.props("max")).toBe(TODAY);
    expect(fields[1]!.props("max")).toBe(TODAY);
    expect(
      dom("[data-period-popover]").findAll('input[type="date"]:not([aria-hidden="true"])'),
    ).toHaveLength(0);
    fields[0]!.vm.$emit("update:modelValue", "2026-09-10");
    await wrapper.vm.$nextTick();
    (dom("[data-period-custom-apply]").element as HTMLElement).click();
    await wrapper.vm.$nextTick();
    // Exato, e não `.at(-1)`: abrir o popover em 28D não pode escolher nada sozinho.
    // A versão anterior olhava só o último evento e escondia um "Dia" emitido pelo
    // foco que o popover põe no primeiro gatilho ao abrir.
    expect(wrapper.emitted("update:modelValue")).toEqual([[{ preset: "custom", from: "2026-09-10", to: TODAY }]]);
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
    const popover = dom("[data-period-popover]");
    const headings = popover.findAll("p").map((p) => p.text());
    expect(headings).toEqual(["Período", "Próximos", "Últimos", "Personalizado"]);
    expect(presetKeys()).toEqual(["day", "week", "next7d", "next14d", "7d"]);
    // O chip diz "7D" dentro do grupo; o nome acessível diz para que lado. O
    // NuxtTabs não repassa "aria-label" do item ao gatilho (a pilha o pôs lá e ele
    // morria antes do DOM), então o nome vai no conteúdo do gatilho.
    expect(accessibleName(presetTab("next7d"))).toBe("Próximos 7 dias");
    expect(accessibleName(presetTab("7d"))).toBe("Últimos 7 dias");
    expect(accessibleName(presetTab("week"))).toBe("Semana");

    await activate(periodTabs()[2]!);
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
    // O campo canônico, não o nativo (ver "personalizado aplica o intervalo").
    const fields = wrapper.findAllComponents(UiDateField);
    fields[0]!.vm.$emit("update:modelValue", "2026-10-01");
    fields[1]!.vm.$emit("update:modelValue", "2026-12-31");
    await wrapper.vm.$nextTick();
    expect(dom("[data-period-custom-error]").text()).toContain("No máximo 62 dias por vez.");
    expect(dom("[data-period-custom-apply]").attributes("disabled")).toBeDefined();
    await dom("[data-period-custom-apply]").trigger("click");
    expect(wrapper.emitted("update:modelValue")).toBeUndefined();

    fields[1]!.vm.$emit("update:modelValue", "2026-11-30");
    await wrapper.vm.$nextTick();
    expect(document.querySelector("[data-period-custom-error]")).toBeNull();
    await dom("[data-period-custom-apply]").trigger("click");
    expect(wrapper.emitted("update:modelValue")).toEqual([[{ preset: "custom", from: "2026-10-01", to: "2026-11-30" }]]);
  });

  it("compact: no celular o botão diz a forma curta; o nome acessível segue inteiro", async () => {
    const wrapper = await mount(OperatorPeriodPicker, {
      props: {
        modelValue: { preset: "28d", from: "", to: "" },
        today: TODAY,
        max: TODAY,
        presets: ["day", "28d"],
        compact: true,
      },
    });
    const button = wrapper.get("[data-period-button]");
    expect(button.get("[data-period-label-full]").text()).toBe("Últimos 28 dias · 04/09 a 01/10");
    expect(button.get("[data-period-label-full]").classes()).toContain("max-sm:hidden");
    expect(button.get("[data-period-label-short]").text()).toBe("28D · 04/09 a 01/10");
    expect(button.get("[data-period-label-short]").classes()).toContain("sm:hidden");
    expect(button.attributes("aria-label")).toBe("Período: Últimos 28 dias · 04/09 a 01/10");
  });

  it("sem compact, o botão segue com uma frase só", async () => {
    const wrapper = await mount(OperatorPeriodPicker, {
      props: { modelValue: { preset: "day", from: "", to: "" }, today: TODAY },
    });
    expect(wrapper.find("[data-period-label-short]").exists()).toBe(false);
  });

  it("um dia com ‹ ›: as setas vão aos dias que a leitura tem, e a sem destino desliga", async () => {
    const wrapper = await mount(OperatorPeriodPicker, {
      props: {
        modelValue: { preset: "day", from: "2026-09-29", to: "" },
        today: TODAY,
        max: "2026-09-30",
        prevDay: "2026-09-27",
        nextDay: "",
        compact: true,
      },
    });
    expect(wrapper.get("[data-period-label-short]").text()).toBe("Ter 29/09");
    const prev = wrapper.get("[data-period-prev]");
    expect(prev.attributes("aria-label")).toBe("Dia anterior: Dom 27/09");
    const next = wrapper.get("[data-period-next]");
    expect(next.attributes("disabled")).toBeDefined();
    expect(next.attributes("aria-label")).toBe("Próximo dia");
    await prev.trigger("click");
    expect(wrapper.emitted("update:modelValue")).toEqual([[{ preset: "day", from: "2026-09-27", to: "" }]]);

    await wrapper.setProps({ nextDay: "2026-09-30" });
    expect(wrapper.get("[data-period-next]").attributes("aria-label")).toBe("Próximo dia: Qua 30/09");
    await wrapper.get("[data-period-next]").trigger("click");
    expect(wrapper.emitted("update:modelValue")![1]).toEqual([{ preset: "day", from: "2026-09-30", to: "" }]);
  });
});
