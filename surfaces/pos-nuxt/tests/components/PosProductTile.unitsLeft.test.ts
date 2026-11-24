// O saldo em número no tile (#2610, WP-E8): "Restam 3" quando a projeção dá o
// número, atualizado pelo mesmo aviso de estoque do selo "Esgotado" (WP-E4), e
// fora do tile quando o número não diz "restam" (bloqueado, encomenda de outro dia).
// À vista só quando o item está ACABANDO (DEV-2026-077, opção C do dono): a
// porcentagem do SKU decide no servidor (`running_low`); fora disso, o número
// fica para o hover e o foco do teclado.
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
    running_low: true,
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
  it("acabando, a grade mostra o número à vista na faixa", async () => {
    const wrapper = await mountSuspended(PosProductTile, { props: { product: product(), qty: 0 } });
    const pill = wrapper.find("[data-pos-product-units-left]");
    expect(pill.text()).toBe("Restam 3");
    expect(pill.attributes("data-pos-product-units-left")).toBe("low");
    expect(pill.classes()).toContain("inline-flex");
    expect(pill.classes()).not.toContain("hidden");
  });

  it("longe de acabar, o número existe mas só aparece no hover e no foco", async () => {
    const wrapper = await mountSuspended(PosProductTile, {
      props: { product: product({ units_left: 18, running_low: false }), qty: 0 },
    });
    const pill = wrapper.find("[data-pos-product-units-left]");
    expect(pill.text()).toBe("Restam 18");
    expect(pill.attributes("data-pos-product-units-left")).toBe("hover");
    expect(pill.classes()).toEqual(expect.arrayContaining(["hidden", "group-hover:inline-flex", "group-focus-visible:inline-flex"]));
  });

  it("acabando, a lista mostra o número junto das pílulas", async () => {
    const wrapper = await mountSuspended(PosProductTile, { props: { product: product(), qty: 0, row: true } });
    expect(wrapper.find("[data-pos-product-units-left]").text()).toBe("Restam 3");
  });

  it("longe de acabar, a lista fica limpa", async () => {
    const wrapper = await mountSuspended(PosProductTile, {
      props: { product: product({ units_left: 18, running_low: false }), qty: 0, row: true },
    });
    expect(wrapper.find("[data-pos-product-units-left]").exists()).toBe(false);
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
    const next = mergeAvailability(grid, [{ sku: "PAO", sold_out: false, sold_out_reason: "", units_left: 2, running_low: true }]);
    expect(next[0]!.units_left).toBe(2);
    // Aviso que não muda o número devolve a MESMA lista.
    expect(mergeAvailability(next, [{ sku: "PAO", sold_out: false, sold_out_reason: "", units_left: 2, running_low: true }])).toBe(next);
  });

  it("a venda que leva o item ao limiar acende o número à vista", () => {
    const grid = [product({ units_left: 6, running_low: false })];
    const next = mergeAvailability(grid, [{ sku: "PAO", sold_out: false, sold_out_reason: "", units_left: 5, running_low: true }]);
    expect(next[0]!.running_low).toBe(true);
  });

  it("na encomenda para outro dia o número de hoje sai do tile", () => {
    const schedule = { date: "2026-11-30", is_today: false, sold_out_skus: [], unplanned_skus: [] };
    const [forDate] = productsForOrderDate([product()], schedule, "2026-11-30");
    expect(forDate!.units_left).toBeNull();
    expect(forDate!.running_low).toBe(false);
    // Para hoje, fica.
    const [today] = productsForOrderDate([product()], { ...schedule, is_today: true }, "2026-11-30");
    expect(today!.units_left).toBe(3);
  });
});
