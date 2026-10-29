import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";

import OperatorFieldRow from "../../app/components/OperatorFieldRow.vue";

describe("OperatorFieldRow", () => {
  it("distribui a linha pela prioridade sem o consumidor declarar larguras", () => {
    const wrapper = mount(OperatorFieldRow, {
      props: { priority: "context" },
      slots: { value: "Quantidade", context: "Base" },
    });

    expect(wrapper.attributes("data-priority")).toBe("context");
    expect(wrapper.classes()).toContain("min-[360px]:grid-cols-[minmax(7rem,2fr)_minmax(0,3fr)]");
    expect(wrapper.get("[data-operator-field-value]").text()).toBe("Quantidade");
    expect(wrapper.get("[data-operator-field-context]").text()).toBe("Base");
  });

  it("leva o campo condicional para uma linha inteira", () => {
    const wrapper = mount(OperatorFieldRow, {
      slots: { value: "Quantidade", context: "Base", detail: "Ingrediente da base" },
    });

    const detail = wrapper.get("[data-operator-field-detail]");
    expect(detail.text()).toBe("Ingrediente da base");
    expect(detail.classes()).toContain("min-[360px]:col-span-2");
  });

  it("não reserva uma linha vazia quando não há detalhe", () => {
    const wrapper = mount(OperatorFieldRow, {
      slots: { value: "Quantidade", context: "Unidade" },
    });

    expect(wrapper.find("[data-operator-field-detail]").exists()).toBe(false);
  });
});
