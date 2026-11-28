import { describe, it, expect, vi } from "vitest";
import { computed, ref, watch } from "vue";
import { mount, flushPromises } from "@vue/test-utils";
import Links from "../../app/components/CatalogProductLinks.vue";
import type { ProductDetailProjection } from "../../app/types/catalog";
vi.stubGlobal("ref", ref);
vi.stubGlobal("computed", computed);
vi.stubGlobal("watch", watch);
const detail = {
  collections: [{ ref: "bread", is_primary: true, sort_order: 3 }],
  collection_choices: [{ ref: "bread", name: "Pães", is_active: true }],
  listing_links: [
    {
      surface_ref: "web",
      name: "Loja online",
      price_q: 500,
      min_qty: "1",
      is_published: true,
      is_sellable: false,
      action: { enabled: true },
    },
  ],
} as ProductDetailProjection;
function setup() {
  const saveCollections = vi.fn().mockResolvedValue(true);
  const saveListing = vi.fn().mockResolvedValue(true);
  const wrapper = mount(Links, {
    props: { detail, busy: false, saveCollections, saveListing },
    global: {
      stubs: {
        NuxtCard: { template: "<div><slot /></div>" },
        NuxtButton: {
          props: ["label", "disabled"],
          template: '<button :disabled="disabled">{{ label }}</button>',
        },
        NuxtFormField: {
          props: ["label", "error"],
          template: "<label>{{ label }}<slot />{{ error }}</label>",
        },
        NuxtInput: {
          props: ["modelValue"],
          emits: ["update:modelValue"],
          template:
            '<input :value="modelValue" @input="$emit(\'update:modelValue\', $event.target.value)" />',
        },
        NuxtCheckbox: {
          props: ["modelValue", "label"],
          emits: ["update:modelValue"],
          template:
            '<label><input type="checkbox" :checked="modelValue" @change="$emit(\'update:modelValue\', $event.target.checked)" />{{ label }}</label>',
        },
        NuxtBadge: { template: "<span><slot /></span>" },
        NuxtModal: true,
      },
    },
  });
  const click = async (label: string) => {
    await wrapper
      .findAll("button")
      .find((button) => button.text() === label)!
      .trigger("click");
    await flushPromises();
  };
  return { wrapper, saveCollections, saveListing, click };
}
describe("Vínculos do produto", () => {
  it("aplica preço pt-BR, mínimo e flags pelo canal observado", async () => {
    const { wrapper, click, saveListing } = setup();
    await click("Editar canal");
    await wrapper.findAll("input")[0]!.setValue("12,50");
    await wrapper.findAll("input")[1]!.setValue("2,5");
    await click("Aplicar");
    expect(saveListing).toHaveBeenCalledWith(detail.listing_links![0], {
      price_q: 1250,
      min_qty: "2.5",
      is_published: true,
      is_sellable: false,
    });
  });
  it("valida antes de salvar e mantém o editor na recusa", async () => {
    const { wrapper, click, saveListing } = setup();
    await click("Editar canal");
    await wrapper.findAll("input")[1]!.setValue("0");
    await click("Aplicar");
    expect(saveListing).not.toHaveBeenCalled();
    expect(wrapper.text()).toContain("quantidade mínima positiva");
    await click("Cancelar");
    expect(wrapper.text()).not.toContain("quantidade mínima positiva");
  });
  it("recusa de gravação mantém edição e rascunho", async () => {
    const { wrapper, click, saveListing } = setup();
    saveListing.mockResolvedValue(false);
    await click("Editar canal");
    await wrapper.findAll("input")[0]!.setValue("9,50");
    await click("Aplicar");
    expect(wrapper.findAll("input")[0]!.element.value).toBe("9,50");
    expect(
      wrapper.findAll("button").some((button) => button.text() === "Cancelar"),
    ).toBe(true);
  });
  it("usar detalhe atual descarta o editor local antigo", async () => {
    const { wrapper, click } = setup();
    await click("Editar coleções");
    await click("Retirar");
    await wrapper.setProps({ detail: { ...detail, name: "Detalhe relido" } });
    expect(wrapper.text()).toContain("Editar coleções");
    expect(wrapper.text()).toContain("Pães");
    expect(
      wrapper.findAll("button").some((button) => button.text() === "Aplicar"),
    ).toBe(false);
  });
  it("cancelar coleções não grava; aplicar retirada salva só curadoria", async () => {
    const { click, saveCollections, saveListing } = setup();
    await click("Editar coleções");
    await click("Retirar");
    await click("Cancelar");
    expect(saveCollections).not.toHaveBeenCalled();
    await click("Editar coleções");
    await click("Retirar");
    await click("Aplicar");
    expect(saveCollections).toHaveBeenCalledWith([]);
    expect(saveListing).not.toHaveBeenCalled();
    expect(detail.collections).toHaveLength(1);
  });
});
