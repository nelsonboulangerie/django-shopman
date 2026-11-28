// Grade ou Lista (dono, 03/11/2026: os itens da venda "podem ser vistos em forma de
// lista também, caso o operador prefira"). A escolha é do dispositivo, como a
// densidade: guardada em `pos.productLayout`, lida ao montar. Na lista, cada produto é
// uma linha e o toque lança igual; o cartão de escolha abre as opções igual.
import { mountSuspended } from "@nuxt/test-utils/runtime";
import { beforeEach, describe, expect, it } from "vitest";
import { nextTick } from "vue";

import PosProductGrid from "~/components/PosProductGrid.vue";
import type { POSProductProjection } from "~/types/pos";

function product(sku: string, name: string): POSProductProjection {
  return { sku, name, price_q: 500, price_display: "R$ 5,00", collections: [], image_url: "" } as unknown as POSProductProjection;
}

beforeEach(() => window.localStorage.removeItem("pos.productLayout"));

async function mount() {
  return mountSuspended(PosProductGrid, {
    props: { products: [product("PAO", "Pão francês"), product("CAFE", "Café coado")], collections: [], cartItems: [], loading: false },
  });
}

describe("PosProductGrid — Grade ou Lista", () => {
  it("nasce em grade; Lista troca para uma linha por produto e fica guardada", async () => {
    const wrapper = await mount();
    expect(wrapper.find("[data-pos-product-layout-view]").attributes("data-pos-product-layout-view")).toBe("grid");
    expect(wrapper.findAll("[data-pos-product-row]")).toHaveLength(0);

    await wrapper.get('[data-pos-product-layout-option="list"]').trigger("click");
    await nextTick();
    expect(wrapper.find("[data-pos-product-layout-view]").attributes("data-pos-product-layout-view")).toBe("list");
    expect(wrapper.findAll("[data-pos-product-row]")).toHaveLength(2);
    expect(wrapper.get('[data-pos-product-layout-option="list"]').attributes("aria-pressed")).toBe("true");
    expect(window.localStorage.getItem("pos.productLayout")).toBe("list");
    wrapper.unmount();
  });

  it("a lista lança o produto no toque, como o tile", async () => {
    window.localStorage.setItem("pos.productLayout", "list");
    const wrapper = await mount();
    await nextTick();
    await wrapper.findAll("[data-pos-product-row]")[0]!.trigger("click");
    expect(wrapper.emitted("add")?.[0]?.[0]).toMatchObject({ sku: "PAO" });
    wrapper.unmount();
  });

  it("o botão da vista diz a vista que abre (o toque usa um botão só)", async () => {
    const wrapper = await mount();
    const toggle = wrapper.find("[data-pos-product-layout-toggle]");
    if (toggle.exists()) {
      expect(toggle.attributes("aria-label")).toBe("Ver em lista");
      await toggle.trigger("click");
      await nextTick();
      expect(wrapper.get("[data-pos-product-layout-toggle]").attributes("aria-label")).toBe("Ver em grade");
    } else {
      expect(wrapper.get('[data-pos-product-layout-option="grid"]').attributes("aria-pressed")).toBe("true");
    }
    wrapper.unmount();
  });

  it("a densidade é só da grade: na lista ela sai da barra", async () => {
    window.localStorage.setItem("pos.productLayout", "list");
    const wrapper = await mount();
    await nextTick();
    expect(wrapper.find('[aria-label="Densidade da grade"]').exists()).toBe(false);
    wrapper.unmount();
  });
});
