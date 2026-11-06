// O tile bloqueado (beta test de 05/11/2026): o selo mora na faixa da foto, nunca
// ao lado do preço (lá ele cortava "R$ 219,00/kg"), e o toque diz o motivo em
// vez de não fazer nada.
import { mountSuspended } from "@nuxt/test-utils/runtime";
import { describe, expect, it, vi } from "vitest";
import { toast } from "vue-sonner";

import PosProductTile from "~/components/PosProductTile.vue";
import type { POSProductProjection } from "~/types/pos";

vi.mock("vue-sonner", async (importOriginal) => ({
  ...(await importOriginal<typeof import("vue-sonner")>()),
  toast: { error: vi.fn(), success: vi.fn(), info: vi.fn(), warning: vi.fn() },
}));

function product(overrides: Partial<POSProductProjection> = {}): POSProductProjection {
  return {
    sku: "QUEIJO",
    name: "Queijo Vale do Testo",
    price_q: 21900,
    price_display: "R$ 219,00/kg",
    collection_ref: "",
    collection_color: "",
    collection_icon: "",
    image_url: "",
    sold_out: true,
    ...overrides,
  } as POSProductProjection;
}

describe("PosProductTile — bloqueado", () => {
  it("o selo não divide a linha do preço", async () => {
    const wrapper = await mountSuspended(PosProductTile, { props: { product: product(), qty: 0 } });
    const priceLine = wrapper.find("[data-pos-product-price]").element.parentElement!;
    expect(priceLine.textContent).not.toContain("Esgotado");
    expect(wrapper.find("[data-pos-product-price] strong").text()).toBe("R$ 219,00/kg");
    expect(wrapper.find("[data-pos-product-blocked]").text()).toBe("Esgotado");
  });

  it("o selo diz o motivo da data", async () => {
    const wrapper = await mountSuspended(PosProductTile, {
      props: { product: product({ sold_out_reason: "Sem saldo para 07/11" }), qty: 0 },
    });
    expect(wrapper.find("[data-pos-product-blocked]").text()).toBe("Sem saldo para 07/11");
  });

  it("o toque no bloqueado não lança e diz por quê", async () => {
    const wrapper = await mountSuspended(PosProductTile, {
      props: { product: product({ sold_out_reason: "Sem saldo para 07/11" }), qty: 0 },
    });
    const tile = wrapper.find("[data-pos-product]");
    expect(tile.attributes("disabled")).toBeUndefined();
    expect(tile.attributes("aria-disabled")).toBe("true");
    await tile.trigger("click");
    expect(wrapper.emitted("add")).toBeUndefined();
    expect(toast.info).toHaveBeenCalledWith("Queijo Vale do Testo: Sem saldo para 07/11.");
  });

  it("o disponível lança no toque", async () => {
    const wrapper = await mountSuspended(PosProductTile, { props: { product: product({ sold_out: false }), qty: 0 } });
    await wrapper.find("[data-pos-product]").trigger("click");
    expect(wrapper.emitted("add")).toHaveLength(1);
    expect(wrapper.find("[data-pos-product-blocked]").exists()).toBe(false);
  });
});
