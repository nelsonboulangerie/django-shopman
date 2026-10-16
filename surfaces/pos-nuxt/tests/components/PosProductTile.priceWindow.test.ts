// O tile na Hora da Xepa: o preço do motor em destaque e a etiqueta cheia
// riscada NA MESMA LINHA (a altura do cartão não muda com o desconto).
import { mountSuspended } from "@nuxt/test-utils/runtime";
import { describe, expect, it } from "vitest";

import PosProductTile from "~/components/PosProductTile.vue";
import type { POSProductProjection } from "~/types/pos";

function product(overrides: Partial<POSProductProjection> = {}): POSProductProjection {
  return {
    sku: "PAO",
    name: "Pão",
    price_q: 1200,
    price_display: "R$ 12,00",
    collection_ref: "",
    collection_color: "",
    collection_icon: "",
    image_url: "",
    sold_out: false,
    ...overrides,
  } as POSProductProjection;
}

describe("PosProductTile — Hora da Xepa", () => {
  it("mostra o preço de agora e risca a etiqueta ao lado", async () => {
    const wrapper = await mountSuspended(PosProductTile, {
      props: {
        product: product({
          price_q: 900, price_display: "R$ 9,00",
          list_price_q: 1200, list_price_display: "R$ 12,00", discount_label: "Hora da Xepa",
        }),
        qty: 0,
      },
    });

    const line = wrapper.find("[data-pos-product-price]");
    expect(line.find("strong").text()).toBe("R$ 9,00");
    const strike = line.find("[data-pos-product-list-price]");
    expect(strike.element.tagName).toBe("S");
    expect(strike.text()).toBe("R$ 12,00");
    expect(strike.attributes("title")).toBe("Hora da Xepa: antes R$ 12,00");
    // Quem lê a tela ouve o desconto com nome, não dois preços soltos.
    expect(line.text()).toContain("Hora da Xepa, antes R$ 12,00");
  });

  it("sem desconto não há riscado", async () => {
    const wrapper = await mountSuspended(PosProductTile, { props: { product: product(), qty: 0 } });

    expect(wrapper.find("[data-pos-product-list-price]").exists()).toBe(false);
    expect(wrapper.find("[data-pos-product-price] strong").text()).toBe("R$ 12,00");
  });
});
