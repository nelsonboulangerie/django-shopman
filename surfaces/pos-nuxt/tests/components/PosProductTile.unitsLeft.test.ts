// O saldo em número no tile (#2610, WP-E8): "Restam 3" quando a projeção dá o
// número, atualizado pelo mesmo aviso de estoque do selo "Esgotado" (WP-E4), e
// fora do tile quando o número não diz "restam" (bloqueado, encomenda de outro dia).
import { mountSuspended } from "@nuxt/test-utils/runtime";
import { describe, expect, it } from "vitest";

import PosProductTile from "~/components/PosProductTile.vue";
import { productsForOrderDate, unitsLeftLabel } from "~/presentation/catalog";
import { mergeAvailability } from "~/presentation/events";
import type { POSProductProjection } from "~/types/pos";

function product(overrides: Partial<POSProductProjection> = {}): POSProductProjection {
  return {
    sku: "PAO",
    name: "Pão de Campanha",
    price_q: 1800,
    price_display: "R$ 18,00",
    collection_ref: "",
    collection_color: "",
    collection_icon: "",
    image_url: "",
    sold_out: false,
    units_left: 3,
    ...overrides,
  } as POSProductProjection;
}

describe("unitsLeftLabel", () => {
  it("diz quantas restam, no singular quando é a última", () => {
    expect(unitsLeftLabel(product())).toBe("Restam 3");
    expect(unitsLeftLabel(product({ units_left: 1 }))).toBe("Resta 1");
  });

  it("sem número, com zero ou esgotado não diz nada (o selo fala)", () => {
    expect(unitsLeftLabel(product({ units_left: null }))).toBe("");
    expect(unitsLeftLabel(product({ units_left: undefined }))).toBe("");
    expect(unitsLeftLabel(product({ units_left: 0 }))).toBe("");
    expect(unitsLeftLabel(product({ sold_out: true, units_left: 3 }))).toBe("");
  });
});

describe("PosProductTile — o saldo em número", () => {
  it("a grade mostra o número na faixa", async () => {
    const wrapper = await mountSuspended(PosProductTile, { props: { product: product(), qty: 0 } });
    expect(wrapper.find("[data-pos-product-units-left]").text()).toBe("Restam 3");
  });

  it("a lista mostra o número junto das pílulas", async () => {
    const wrapper = await mountSuspended(PosProductTile, { props: { product: product(), qty: 0, row: true } });
    expect(wrapper.find("[data-pos-product-units-left]").text()).toBe("Restam 3");
  });

  it("o tile bloqueado não mostra número", async () => {
    const wrapper = await mountSuspended(PosProductTile, {
      props: { product: product({ sold_out: true, units_left: 3 }), qty: 0 },
    });
    expect(wrapper.find("[data-pos-product-units-left]").exists()).toBe(false);
  });
});

describe("o número segue o estoque", () => {
  it("outro balcão vendeu uma: o aviso de estoque baixa o número sem ninguém tocar", () => {
    const grid = [product()];
    const next = mergeAvailability(grid, [{ sku: "PAO", sold_out: false, sold_out_reason: "", units_left: 2 }]);
    expect(next[0]!.units_left).toBe(2);
    // Aviso que não muda o número devolve a MESMA lista.
    expect(mergeAvailability(next, [{ sku: "PAO", sold_out: false, sold_out_reason: "", units_left: 2 }])).toBe(next);
  });

  it("na encomenda para outro dia o número de hoje sai do tile", () => {
    const schedule = { date: "2026-11-30", is_today: false, sold_out_skus: [], unplanned_skus: [] };
    const [forDate] = productsForOrderDate([product()], schedule, "2026-11-30");
    expect(forDate!.units_left).toBeNull();
    // Para hoje, fica.
    const [today] = productsForOrderDate([product()], { ...schedule, is_today: true }, "2026-11-30");
    expect(today!.units_left).toBe(3);
  });
});
