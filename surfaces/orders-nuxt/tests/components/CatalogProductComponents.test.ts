import { describe, it, expect, vi } from "vitest";
import { computed, ref, watch } from "vue";
import { mount, flushPromises } from "@vue/test-utils";
import Components from "../../app/components/CatalogProductComponents.vue";
vi.stubGlobal("ref", ref);
vi.stubGlobal("computed", computed);
vi.stubGlobal("watch", watch);
const confirm = vi.fn().mockResolvedValue(true);
vi.stubGlobal("useConfirm", () => confirm);
function setup() {
  confirm.mockClear();
  const save = vi.fn().mockResolvedValue(true);
  const search = vi.fn().mockResolvedValue([
    { sku: "PAO", name: "Pão", unit: "un" },
    { sku: "BOLO", name: "Bolo", unit: "kg" },
    { sku: "COMBO", name: "Combo", unit: "un" },
  ]);
  const wrapper = mount(Components, {
    props: {
      sku: "COMBO",
      unit: "un",
      components: [{ sku: "PAO", name: "Pão", unit: "un", qty: "2.000" }],
      busy: false,
      save,
      search,
    },
    global: {
      stubs: {
        NuxtCard: { template: "<div><slot /></div>" },
        NuxtButton: {
          props: ["label", "disabled"],
          template: '<button :disabled="disabled">{{ label }}</button>',
        },
        OperatorTimedButton: {
          props: ["label", "disabled"],
          template: '<button :disabled="disabled">{{ label }}</button>',
        },
        NuxtFormField: {
          props: ["label", "error"],
          template: "<label>{{ label }}<slot />{{ error }}</label>",
        },
        NuxtInput: {
          props: ["modelValue", "disabled"],
          emits: ["update:modelValue"],
          template:
            '<input :disabled="disabled" :value="modelValue" @input="$emit(\'update:modelValue\', $event.target.value)" />',
        },
        NuxtModal: {
          props: ["open"],
          template: '<div v-if="open"><slot name="body" /></div>',
        },
      },
    },
  });
  async function click(label: string) {
    await wrapper
      .findAll("button")
      .find((button) => button.text() === label)!
      .trigger("click");
    await flushPromises();
  }
  return { wrapper, save, search, click };
}
describe("Componentes do combo", () => {
  it("usar os valores atuais fecha o editor antigo, mas mutação aninhada não apaga o rascunho", async () => {
    const { wrapper, click } = setup();
    await click("Editar componentes");
    await wrapper.find("input").setValue("3");
    wrapper.props("components")[0]!.qty = "5";
    await flushPromises();
    expect(wrapper.find("input").element.value).toBe("3");
    await wrapper.setProps({
      components: [{ sku: "PAO", name: "Pão", unit: "un", qty: "4" }],
    });
    expect(wrapper.find("input").exists()).toBe(false);
    expect(wrapper.text()).toContain("4 un");
  });
  it("aplica quantidades pt-BR pela escrita canônica injetada", async () => {
    const { wrapper, save, click } = setup();
    await click("Editar componentes");
    await wrapper.find("input").setValue("2,5");
    await click("Aplicar");
    expect(save).toHaveBeenCalledWith([{ sku: "PAO", qty: "2.5" }]);
    expect(wrapper.text()).toContain("Desfazer composição");
    expect(wrapper.emitted("dirty-change")?.at(-1)).toEqual([false]);
  });
  it("busca por nome ou SKU e exclui o próprio combo e componentes repetidos", async () => {
    const { wrapper, search, save, click } = setup();
    await click("Editar componentes");
    await click("Incluir componente");
    expect(search).toHaveBeenCalledWith("");
    expect(
      wrapper.findAll("button").filter((button) => button.text() === "Combo"),
    ).toHaveLength(0);
    await wrapper.findAll("input").at(-1)!.setValue("bolo");
    await click("Buscar");
    expect(search).toHaveBeenLastCalledWith("bolo");
    await click("Bolo");
    await click("Aplicar");
    expect(save).toHaveBeenCalledWith([
      { sku: "PAO", qty: "2.000" },
      { sku: "BOLO", qty: "1" },
    ]);
  });
  it("recusa quantidade inválida sem gravar", async () => {
    const { wrapper, save, click } = setup();
    await click("Editar componentes");
    await wrapper.find("input").setValue("0");
    await click("Aplicar");
    expect(save).not.toHaveBeenCalled();
    expect(wrapper.text()).toContain("quantidade positiva");
    await click("Cancelar");
    expect(wrapper.emitted("dirty-change")?.at(-1)).toEqual([false]);
  });
  it("remover exige confirmação e oferece desfazer com o conjunto anterior", async () => {
    const { save, click } = setup();
    await click("Editar componentes");
    await click("Retirar Pão");
    await click("Aplicar");
    expect(confirm).toHaveBeenCalledOnce();
    expect(save).toHaveBeenLastCalledWith([]);
    await click("Desfazer composição");
    expect(save).toHaveBeenLastCalledWith([{ sku: "PAO", qty: "2.000" }]);
  });
  it("uma recusa mantém o rascunho; operação ocupada não começa outra edição", async () => {
    const { wrapper, save, click } = setup();
    save.mockResolvedValue(false);
    await click("Editar componentes");
    await wrapper.find("input").setValue("3");
    await click("Aplicar");
    expect(wrapper.find("input").element.value).toBe("3");
    expect(wrapper.text()).toContain("não foi aplicada");
    await click("Cancelar");
    await wrapper.setProps({ busy: true });
    expect(
      wrapper
        .findAll("button")
        .find((button) => button.text() === "Editar componentes")!
        .attributes("disabled"),
    ).toBeDefined();
  });
});
