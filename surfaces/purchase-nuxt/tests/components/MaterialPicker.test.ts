// Escolher o insumo tem que FECHAR e COMITAR — o bug do balcão era o contrário:
// o operador digitava, via o resultado, tocava nele, e a lista continuava aberta
// como se nada tivesse acontecido. A causa não estava no componente e sim em
// quem o usava: um `<label>` em volta adota o primeiro controle rotulável de
// dentro (o botão que abre) e reencaminha para ele todo clique que cai em parte
// NÃO interativa da label — incluindo o véu de "fechar ao tocar fora". Fechava e
// reabria no mesmo gesto.
//
// Aqui provamos as duas metades: o contrato do componente (escolher fecha e
// emite; teclado anda na lista) e a imunidade ao `<label>` em volta.
import { computed, nextTick, ref, useId, useTemplateRef, watch } from "vue";
import { mount } from "@vue/test-utils";
import { describe, expect, it, vi } from "vitest";

import MaterialPicker from "../../app/components/MaterialPicker.vue";
import type { Material } from "../../app/types/purchase";

// Auto-imports do Nuxt que o SFC usa como globais (sem runtime Nuxt aqui).
vi.stubGlobal("computed", computed);
vi.stubGlobal("ref", ref);
vi.stubGlobal("watch", watch);
vi.stubGlobal("nextTick", nextTick);
vi.stubGlobal("useId", useId);
vi.stubGlobal("useTemplateRef", useTemplateRef);

const materials: Material[] = [
  {
    sku: "MANTEIGA-FR",
    name: "Manteiga francesa",
    unit: "kg",
    shelfLifeDays: 90,
    isActive: true,
    category: "Laticínios",
    stockOnHand: 10,
    dailyUse: 1,
    minStock: 5,
    recipes: [],
  },
  {
    sku: "ACUCAR",
    name: "Açúcar refinado",
    unit: "kg",
    shelfLifeDays: 365,
    isActive: true,
    category: "Secos",
    stockOnHand: 40,
    dailyUse: 4,
    minStock: 20,
    recipes: [],
  },
  {
    sku: "FARINHA-T65",
    name: "Farinha T65",
    unit: "kg",
    shelfLifeDays: 180,
    isActive: true,
    category: "Farinhas",
    stockOnHand: 80,
    dailyUse: 20,
    minStock: 60,
    recipes: [],
  },
];

function mountPicker(modelValue = "", extra: Record<string, unknown> = {}) {
  return mount(MaterialPicker, {
    props: { materials, modelValue, ...extra },
    global: { stubs: { Icon: true } },
    attachTo: document.body,
  });
}

/** Envolve o picker num `<label>` — exatamente o que quebrava no recebimento. */
const LabelWrapper = {
  components: { MaterialPicker },
  props: { materials: { type: Array, required: true }, modelValue: { type: String, default: "" } },
  emits: ["update:modelValue"],
  template: `
    <label class="block">Insumo<MaterialPicker :materials="materials" :model-value="modelValue"
      @update:model-value="$emit('update:modelValue', $event)" /></label>
  `,
};

async function open(wrapper: ReturnType<typeof mountPicker>) {
  await wrapper.get('button[aria-haspopup="listbox"]').trigger("click");
  await nextTick();
  await nextTick();
}

describe("MaterialPicker — escolher fecha e comita", () => {
  it("abre com o botão e mostra a lista inteira", async () => {
    const wrapper = mountPicker();
    expect(wrapper.find('[role="listbox"]').exists()).toBe(false);

    await open(wrapper);

    expect(wrapper.get('button[aria-haspopup="listbox"]').attributes("aria-expanded")).toBe("true");
    expect(wrapper.findAll('[role="option"]')).toHaveLength(3);
  });

  it("digitar filtra sem acento e sem caixa", async () => {
    const wrapper = mountPicker();
    await open(wrapper);

    await wrapper.get('input[role="combobox"]').setValue("acucar");

    const options = wrapper.findAll('[role="option"]');
    expect(options).toHaveLength(1);
    expect(options[0]!.text()).toContain("Açúcar refinado");
  });

  it("clicar no resultado EMITE o sku e FECHA a lista", async () => {
    const wrapper = mountPicker();
    await open(wrapper);
    await wrapper.get('input[role="combobox"]').setValue("mant");

    await wrapper.get('[role="option"]').trigger("click");
    await nextTick();

    expect(wrapper.emitted("update:modelValue")?.at(-1)).toEqual(["MANTEIGA-FR"]);
    expect(wrapper.find('[role="listbox"]').exists()).toBe(false);
    expect(wrapper.get('button[aria-haspopup="listbox"]').attributes("aria-expanded")).toBe("false");
  });

  it("dentro de um <label>, escolher continua fechando — o véu não reabre", async () => {
    // A regressão de verdade: aqui o `<label>` reencaminha para o botão que
    // abre todo clique que não cai em conteúdo interativo.
    const wrapper = mount(LabelWrapper, {
      props: { materials },
      global: { stubs: { Icon: true } },
      attachTo: document.body,
    });
    await wrapper.get('button[aria-haspopup="listbox"]').trigger("click");
    await nextTick();
    await nextTick();
    expect(wrapper.find('[role="listbox"]').exists()).toBe(true);

    // Tocar fora: o véu fecha, e o `<label>` NÃO pode reabrir no mesmo clique.
    await wrapper.get("div.fixed.inset-0").trigger("click");
    await nextTick();
    await nextTick();

    expect(wrapper.find('[role="listbox"]').exists()).toBe(false);
  });

  it("↑ ↓ andam na lista e Enter pega o destacado", async () => {
    const wrapper = mountPicker();
    await open(wrapper);
    const input = wrapper.get('input[role="combobox"]');

    await input.trigger("keydown", { key: "ArrowDown" });
    await input.trigger("keydown", { key: "ArrowDown" });
    await nextTick();
    expect(wrapper.findAll('[role="option"]')[2]!.attributes("data-active")).toBe("true");

    await input.trigger("keydown", { key: "Enter" });
    await nextTick();

    expect(wrapper.emitted("update:modelValue")?.at(-1)).toEqual(["FARINHA-T65"]);
    expect(wrapper.find('[role="listbox"]').exists()).toBe(false);
  });

  it("↓ dá a volta no fim da lista", async () => {
    const wrapper = mountPicker();
    await open(wrapper);
    const input = wrapper.get('input[role="combobox"]');

    for (let i = 0; i < 3; i += 1) await input.trigger("keydown", { key: "ArrowDown" });
    await nextTick();

    expect(wrapper.findAll('[role="option"]')[0]!.attributes("data-active")).toBe("true");
  });

  it("Esc fecha sem escolher nada", async () => {
    const wrapper = mountPicker();
    await open(wrapper);

    await wrapper.get('input[role="combobox"]').trigger("keydown", { key: "Escape" });
    await nextTick();

    expect(wrapper.find('[role="listbox"]').exists()).toBe(false);
    expect(wrapper.emitted("update:modelValue")).toBeUndefined();
  });

  it("filtrar de novo devolve o destaque para o primeiro resultado", async () => {
    const wrapper = mountPicker();
    await open(wrapper);
    const input = wrapper.get('input[role="combobox"]');

    await input.trigger("keydown", { key: "ArrowDown" });
    await input.trigger("keydown", { key: "ArrowDown" });
    await input.setValue("a");
    await nextTick();

    expect(wrapper.findAll('[role="option"]')[0]!.attributes("data-active")).toBe("true");
  });

  it("o painel aponta o insumo já escolhido e o nomeia pelo rótulo de fora", async () => {
    const wrapper = mountPicker("ACUCAR", { labelledBy: "rotulo-insumo" });
    const trigger = wrapper.get('button[aria-haspopup="listbox"]');
    expect(trigger.text()).toContain("Açúcar refinado");
    expect(trigger.attributes("aria-labelledby")).toContain("rotulo-insumo");

    await open(wrapper);

    const options = wrapper.findAll('[role="option"]');
    expect(options[1]!.attributes("aria-selected")).toBe("true");
    expect(options[1]!.attributes("data-active")).toBe("true");
    expect(wrapper.get('input[role="combobox"]').attributes("aria-activedescendant")).toBe(
      options[1]!.attributes("id"),
    );
  });
});
