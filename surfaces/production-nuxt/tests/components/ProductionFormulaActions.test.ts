import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { computed, defineComponent, h, nextTick, ref, watch } from "vue";
import { mount } from "@vue/test-utils";
import { nuxtUiStubs } from "../support/nuxtUiStubs";

import RegisterOldDoughDialog from "../../app/components/RegisterOldDoughDialog.vue";
import AuthorizeFormulaDeviationDialog from "../../app/components/AuthorizeFormulaDeviationDialog.vue";

const NuxtInputNumberStub = defineComponent({
  name: "NuxtInputNumber",
  inheritAttrs: false,
  props: {
    modelValue: { type: Number, default: null },
    min: Number,
    step: Number,
  },
  emits: ["update:modelValue"],
  setup(props, { attrs, emit, expose }) {
    const inputRef = ref<HTMLInputElement | null>(null);
    expose({ inputRef });
    return () =>
      h("input", {
        ...attrs,
        ref: inputRef,
        type: "number",
        min: props.min,
        step: props.step,
        value: props.modelValue ?? "",
        onInput: (event: Event) =>
          emit("update:modelValue", Number((event.target as HTMLInputElement).value)),
      });
  },
});

const NuxtSelectStub = defineComponent({
  name: "NuxtSelect",
  inheritAttrs: false,
  props: {
    modelValue: { type: String, default: "" },
    items: { type: Array, default: () => [] },
  },
  emits: ["update:modelValue"],
  setup(props, { attrs, emit }) {
    return () =>
      h(
        "select",
        {
          ...attrs,
          value: props.modelValue,
          onChange: (event: Event) =>
            emit("update:modelValue", (event.target as HTMLSelectElement).value),
        },
        (props.items as Array<{ label: string; value: string }>).map((item) =>
          h("option", { value: item.value }, item.label),
        ),
      );
  },
});

const stubs = {
  ...nuxtUiStubs,
  NuxtInputNumber: NuxtInputNumberStub,
  NuxtSelect: NuxtSelectStub,
  Icon: true,
};

beforeEach(() => {
  vi.stubGlobal("ref", ref);
  vi.stubGlobal("computed", computed);
  vi.stubGlobal("watch", watch);
  vi.stubGlobal("nextTick", nextTick);
});
afterEach(() => vi.unstubAllGlobals());

describe("RegisterOldDoughDialog", () => {
  it("sugere amanhã e converte kg para g sem resíduo no passo", async () => {
    const wrapper = mount(RegisterOldDoughDialog, {
      props: { open: true, workOrderLabel: "Pão Francês · lote #42" },
      global: { stubs },
    });
    await nextTick();

    const date = wrapper.find('input[type="date"]');
    expect(date.element.getAttribute("value")).toMatch(/^\d{4}-\d{2}-\d{2}$/);

    const quantity = wrapper.find('input[aria-label="Quantidade de massa velha"]');
    await quantity.setValue("2");
    await wrapper.find('select[aria-label="Unidade da massa velha"]').setValue("kg");
    await wrapper.find('select[aria-label="Unidade da massa velha"]').setValue("g");

    expect((quantity.element as HTMLInputElement).value).toBe("2");
    expect(quantity.attributes("step")).toBe("1");
  });

  it("envia quantidade, unidade, validade e nota", async () => {
    const wrapper = mount(RegisterOldDoughDialog, {
      props: {
        open: true,
        workOrderLabel: "Pão Francês · lote #42",
        positionRef: "bancada-1",
      },
      global: { stubs },
    });
    await nextTick();
    await wrapper.find('input[aria-label="Quantidade de massa velha"]').setValue("1250");
    await wrapper.find("textarea").setValue("Aparas do turno");
    await wrapper.get("button[data-icon='i-lucide-package-plus']").trigger("click");

    expect(wrapper.emitted("submit")?.[0]?.[0]).toMatchObject({
      quantity: "1250",
      unit: "g",
      positionRef: "bancada-1",
      note: "Aparas do turno",
    });
  });
});

describe("AuthorizeFormulaDeviationDialog", () => {
  const levain = {
    ingredient_ref: "levain",
    sku: "LEVAIN",
    name: "Levain",
    kind: "ratio" as const,
    minimum: "18",
    target: "20",
    maximum: "22",
    unit: "%",
    basis_label: "Farinhas totais",
    actual: "20",
    available_batches: [],
  };

  it("mostra limites e exige motivo antes de autorizar", async () => {
    const wrapper = mount(AuthorizeFormulaDeviationDialog, {
      props: { open: true, workOrderLabel: "Pão · lote #42", limits: [levain] },
      global: { stubs },
    });
    await nextTick();

    expect(wrapper.text()).toContain("Mínimo");
    expect(wrapper.text()).toContain("18 %");
    const submit = wrapper.get("button[data-icon='i-lucide-shield-check']");
    expect(submit.attributes("disabled")).toBeDefined();

    await wrapper.find('input[aria-label="Quantidade real em %"]').setValue("17.5");
    await wrapper.find("textarea").setValue("Fermentação ajustada pelo gerente");
    await submit.trigger("click");

    expect(wrapper.emitted("submit")?.[0]?.[0]).toEqual({
      ingredientRef: "levain",
      actualQuantity: "17.5",
      batchRef: undefined,
      reason: "Fermentação ajustada pelo gerente",
    });
  });

  it("apresenta a composição recalculada devolvida pelo servidor", () => {
    const wrapper = mount(AuthorizeFormulaDeviationDialog, {
      props: {
        open: true,
        workOrderLabel: "Pão · lote #42",
        limits: [levain],
        result: {
          ok: true,
          ingredient_ref: "levain",
          ingredient_sku: "LEVAIN",
          ingredient_name: "Levain",
          expected: { minimum: "18", target: "20", maximum: "22" },
          actual: "17.5",
          reason: "Fermentação ajustada",
          impact: {
            bom: [{ sku: "FARINHA", quantity: "910", unit: "g" }],
            batch_ref: "MV-42",
          },
          work_order_rev: 6,
          replayed: false,
        },
      },
      global: { stubs },
    });

    expect(wrapper.text()).toContain("Impacto na composição");
    expect(wrapper.text()).toContain("FARINHA");
    expect(wrapper.text()).toContain("910 g");
    expect(wrapper.text()).toContain("Lote consumido: MV-42");
  });

  it("exige um lote disponível para desviar massa velha", async () => {
    const massOld = {
      ...levain,
      ingredient_ref: "massa-velha",
      sku: "MASSA-VELHA-PAO-FRANCES",
      name: "Massa Velha de Pão Francês",
      available_batches: [],
    };
    const wrapper = mount(AuthorizeFormulaDeviationDialog, {
      props: { open: true, workOrderLabel: "Pão · lote #42", limits: [massOld] },
      global: { stubs },
    });
    await nextTick();
    await wrapper.find("textarea").setValue("Ajuste autorizado pelo gerente");

    expect(wrapper.text()).toContain(
      "Nenhum lote válido de massa velha tem saldo disponível.",
    );
    expect(
      wrapper.get("button[data-icon='i-lucide-shield-check']").attributes("disabled"),
    ).toBeDefined();

    await wrapper.setProps({
      limits: [
        {
          ...massOld,
          available_batches: [
            {
              ref: "MV-42",
              quantity: "850",
              unit: "g",
              expiry_date: "2099-01-04",
            },
          ],
        },
      ],
    });
    await wrapper.findAll("select").at(-1)!.setValue("MV-42");
    await wrapper.get("button[data-icon='i-lucide-shield-check']").trigger("click");
    expect(wrapper.emitted("submit")?.[0]?.[0]).toMatchObject({
      ingredientRef: "massa-velha",
      batchRef: "MV-42",
    });
  });
});
