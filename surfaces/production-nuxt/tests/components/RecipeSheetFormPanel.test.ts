import { computed, defineComponent, h, nextTick, onBeforeUnmount, reactive, ref, watch } from "vue";
import { enableAutoUnmount, mount } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { nuxtUiStubs } from "../support/nuxtUiStubs";
import RecipeSheetFormPanel from "../../app/components/RecipeSheetFormPanel.vue";
import RecipeSheetDuplicatePanel from "../../app/components/RecipeSheetDuplicatePanel.vue";

// O casco real é do kit; aqui ele vira um stub que mostra o corpo e o botão de
// salvar, e o campo de insumo vira um input que emite o SKU escolhido. O que se
// prova é o formulário da ficha: o corpo que sai e a prévia da massa.

const OperatorFormShellStub = defineComponent({
  name: "OperatorFormShell",
  props: { open: Boolean, saveDisabled: Boolean, saveDisabledReason: String },
  emits: ["save", "update:open"],
  setup(props, { emit, slots }) {
    return () =>
      props.open
        ? h("section", { "data-form-shell": "", "data-disabled-reason": props.saveDisabledReason }, [
            slots.default?.(),
            h("button", { disabled: props.saveDisabled, onClick: () => emit("save") }, "Salvar"),
          ])
        : null;
  },
});

const IngredientPickerStub = defineComponent({
  name: "IngredientPicker",
  props: { modelValue: String, matchedName: String },
  emits: ["update:modelValue", "select"],
  setup(props, { emit }) {
    return () =>
      h("input", {
        class: "ingredient-picker",
        value: props.modelValue,
        onInput: (event: Event) => emit("update:modelValue", (event.target as HTMLInputElement).value),
      });
  },
});

const passthrough = (name: string) =>
  defineComponent({ name, setup: (_, { slots }) => () => h("div", { "data-stub": name }, slots.default?.()) });

const stubs = {
  ...nuxtUiStubs,
  Icon: true,
  NuxtSelect: true,
  NuxtSelectMenu: true,
  OperatorFormShell: OperatorFormShellStub,
  OperatorFormSection: passthrough("OperatorFormSection"),
  IngredientPicker: IngredientPickerStub,
};

function installGlobals() {
  vi.stubGlobal("computed", computed);
  vi.stubGlobal("ref", ref);
  vi.stubGlobal("reactive", reactive);
  vi.stubGlobal("nextTick", nextTick);
  vi.stubGlobal("watch", watch);
  vi.stubGlobal("onBeforeUnmount", onBeforeUnmount);
  vi.stubGlobal("useSonner", { success: vi.fn(), error: vi.fn() });
}

beforeEach(() => installGlobals());
afterEach(() => vi.unstubAllGlobals());
enableAutoUnmount(afterEach);

async function fillCreate(wrapper: ReturnType<typeof mount>) {
  await wrapper.find("input[data-focus-control]").setValue("Pão Tradição");
  const inputs = wrapper.findAll("input");
  await inputs[2]!.setValue("pao-tradicao");
  await inputs[3]!.setValue("1,7");
  // O input do insumo entra na lista do DOM antes da quantidade (índice 4).
  await wrapper.find(".ingredient-picker").setValue("FARINHA-T55");
  await inputs[5]!.setValue("1,5");
  await nextTick();
}

function sheetFixture(over: Record<string, unknown> = {}) {
  return {
    ref: "pao-tradicao",
    revision: "rev-1",
    name: "Pão Tradição",
    output_sku: "PAO-TRADICAO",
    output_name: "Pão",
    batch_size: "1.7",
    output_unit: "kg",
    is_active: true,
    steps: [{ name: "Mistura" }],
    items: [
      { input_sku: "FARINHA-T55", name: "Farinha", quantity: "1.5", unit: "kg", usable_factor: "1", gross_quantity: "1.5", correction_factor: "1", sort_order: 0, is_optional: false, note: "" },
    ],
    mass_balance: { status: "ok", output_unit: "kg", batch_display: "1,7 kg", total_display: "1,5 kg", message: "", tone: "ok" },
    execution: { exists: true, ref: "pao-tradicao", revision: "rev-1", max_started_minutes: 90, capacity_per_day: "120", requires_batch_tracking: true, shelf_life_days: 3, shelf_life_reviewed: true, shelf_life_reviewed_by: "Pablo", production_lifecycle: "standard", lifecycle_options: [] },
    has_entry: true,
    entry_ref: "pao-tradicao",
    ...over,
  } as never;
}

describe("RecipeSheetFormPanel", () => {
  it("só libera o salvar quando o cadastro tem nome, SKU, rendimento e linha válida", async () => {
    const wrapper = mount(RecipeSheetFormPanel, { props: { open: true, sheet: null }, global: { stubs } });
    await nextTick();
    const shell = wrapper.findComponent(OperatorFormShellStub);
    expect(shell.props("saveDisabled")).toBe(true);
    expect(shell.props("saveDisabledReason")).toContain("nome");
    await fillCreate(wrapper);
    expect(shell.props("saveDisabled")).toBe(false);
  });

  it("emite o corpo snake/camel da ficha nova", async () => {
    const wrapper = mount(RecipeSheetFormPanel, { props: { open: true, sheet: null }, global: { stubs } });
    await fillCreate(wrapper);
    const inputs = wrapper.findAll("input");
    await inputs[8]!.setValue("90");
    await inputs[9]!.setValue("120");
    await nextTick();
    await wrapper.findAll("button").find((button) => button.text() === "Salvar")!.trigger("click");

    const payload = wrapper.emitted("save")?.[0]?.[0] as Record<string, unknown>;
    expect(payload.name).toBe("Pão Tradição");
    expect(payload.output_sku).toBe("PAO-TRADICAO");
    expect(payload.batch_size).toBe("1.7");
    expect(payload.maxStartedMinutes).toBe(90);
    expect(payload.capacityPerDay).toBe("120");
    expect(payload.items).toEqual([
      expect.objectContaining({ input_sku: "FARINHA-T55", quantity: "1.5", unit: "kg", usable_factor: "1" }),
    ]);
  });

  it("avisa na hora quando o rendimento passa da soma dos insumos", async () => {
    // Com a unidade de saída declarada (kg), a prévia compara como o modelo.
    const wrapper = mount(RecipeSheetFormPanel, { props: { open: true, sheet: sheetFixture() }, global: { stubs } });
    await nextTick();
    await wrapper.findAll("input")[3]!.setValue("3");
    await nextTick();
    expect(wrapper.text()).toContain("O rendimento passa da soma dos insumos");
  });

  it("edita a ficha semeada e trava a referência", async () => {
    const wrapper = mount(RecipeSheetFormPanel, { props: { open: true, sheet: sheetFixture() }, global: { stubs } });
    await nextTick();
    const inputs = wrapper.findAll("input");
    expect(inputs[1]!.element.value).toBe("pao-tradicao");
    expect(inputs[1]!.element.disabled).toBe(true);
    await inputs[0]!.setValue("Pão novo");
    await nextTick();
    await wrapper.findAll("button").find((button) => button.text() === "Salvar")!.trigger("click");
    const payload = wrapper.emitted("save")?.[0]?.[0] as Record<string, unknown>;
    expect(payload.name).toBe("Pão novo");
    expect(payload.expectedRevision).toBe("rev-1");
    expect(payload.steps).toEqual([{ name: "Mistura" }]);
  });
});

describe("RecipeSheetDuplicatePanel", () => {
  it("semeia o nome com (cópia) e devolve o corpo com a revisão", async () => {
    const source = { ref: "pao-tradicao", name: "Pão Tradição", revision: "rev-1", output_sku: "PAO-TRADICAO" } as never;
    const wrapper = mount(RecipeSheetDuplicatePanel, { props: { open: true, source }, global: { stubs } });
    await nextTick();
    const inputs = wrapper.findAll("input");
    expect(inputs[0]!.element.value).toBe("Pão Tradição (cópia)");
    await inputs[2]!.setValue("sku-novo");
    await wrapper.findAll("button").find((button) => button.text() === "Salvar")!.trigger("click");
    expect(wrapper.emitted("save")?.[0]?.[0]).toEqual({
      name: "Pão Tradição (cópia)",
      output_sku: "SKU-NOVO",
      expectedRevision: "rev-1",
    });
  });
});
