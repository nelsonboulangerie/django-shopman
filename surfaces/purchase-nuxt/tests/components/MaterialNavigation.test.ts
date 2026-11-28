import { flushPromises, mount } from "@vue/test-utils";
import { computed, defineComponent, h, ref } from "vue";
import { createMemoryHistory, createRouter } from "vue-router";
import { afterEach, describe, expect, it, vi } from "vitest";
import MaterialPage from "../../app/pages/base/materials/[sku].vue";

const ActionBar = defineComponent({
  name: "OperatorActionBar",
  props: ["action", "secondary"],
  render: () => null,
});
const Button = defineComponent({
  inheritAttrs: false,
  props: ["label"],
  setup:
    (props, { attrs }) =>
    () =>
      h("button", attrs, props.label),
});
afterEach(() => vi.unstubAllGlobals());

describe("retorno do insumo à lista consultada", () => {
  it("preserva página, ordem, busca e recortes ao fechar", async () => {
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: "/base/materials", component: { render: () => null } },
        { path: "/base/materials/:sku", component: { render: () => null } },
      ],
    });
    const query = {
      page: "2",
      order: "-name",
      q: "mostarda",
      category: ["Temperos", "Molhos"],
    };
    await router.push({ path: "/base/materials/DIJON", query });
    vi.stubGlobal("computed", computed);
    vi.stubGlobal("useRoute", () => router.currentRoute.value);
    vi.stubGlobal("useRouter", () => router);
    vi.stubGlobal("navigateTo", router.push.bind(router));
    vi.stubGlobal("usePurchaseDesk", () => ({
      findMaterial: () => ({ sku: "DIJON", name: "Mostarda Dijon" }),
      backendReady: ref(true),
      openMaterialEdit: vi.fn(),
      openMaterialDuplicate: vi.fn(),
    }));
    vi.stubGlobal("useRecordTrail", () => ({
      trail: ref({
        ids: ["DIJON", "MOSTARDA"],
        from: "/base/materials?page=2",
        label: "Insumos",
      }),
    }));
    const wrapper = mount(MaterialPage, {
      global: {
        stubs: {
          NuxtButton: Button,
          PurchaseMaterialDetail: {
            template: '<div><slot name="actions" /></div>',
          },
          OperatorPageHeader: true,
          OperatorActionBar: ActionBar,
          OperatorRecordNav: true,
          OperatorScreenState: true,
        },
      },
    });
    const next = wrapper.findComponent(ActionBar).props("action").to;
    expect(router.resolve(next).path).toBe("/base/materials/MOSTARDA");
    expect(router.resolve(next).query).toEqual(query);
    await wrapper.get('[aria-label="Fechar o insumo"]').trigger("click");
    await flushPromises();
    expect(router.currentRoute.value.path).toBe("/base/materials");
    expect(router.currentRoute.value.query).toEqual(query);
    wrapper.unmount();
  });
});
