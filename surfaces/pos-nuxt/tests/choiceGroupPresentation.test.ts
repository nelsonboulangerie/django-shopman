import { describe, expect, it } from "vitest";

import type { POSProductProjection } from "../app/types/pos";
import { choiceGroup, choiceGroupsByName, filterProducts, gridEntries } from "../app/presentation/catalog";

function product(overrides: Partial<POSProductProjection> & { sku: string }): POSProductProjection {
  return {
    name: overrides.sku,
    price_q: 1400,
    price_display: "R$ 14,00",
    collection_ref: "bebidas-quentes",
    collection_color: "",
    collection_icon: "",
    image_url: "",
    ...overrides,
  };
}

const GROUP = "Chás da casa";
const camille = product({ sku: "CHCAM", name: "Chá Camille", choice_group: GROUP });
const rouge = product({ sku: "CHROU", name: "Chá Rouge", choice_group: GROUP });
const hibisco = product({
  sku: "CHHIB",
  name: "Chá Hibisco",
  price_q: 1800,
  price_display: "R$ 18,00",
  collection_ref: "bebidas-geladas",
  choice_group: GROUP,
});
const espresso = product({ sku: "SP", name: "Espresso", price_q: 800, price_display: "R$ 8,00" });
const catalog = [camille, espresso, hibisco, rouge];

describe("presentation/catalog — cartão de escolha", () => {
  it("sem busca, o grupo vira um tile no lugar do primeiro membro", () => {
    const entries = gridEntries(catalog, catalog, "");
    expect(entries.map((entry) => entry.key)).toEqual([`group:${GROUP}`, "product:SP"]);
    const tile = entries[0];
    if (tile?.kind !== "group") throw new Error("esperava o tile do grupo");
    expect(tile.group.options.map((option) => option.sku)).toEqual(["CHCAM", "CHHIB", "CHROU"]);
    expect(tile.group.priceLabel).toBe("a partir de R$ 14,00");
  });

  it("com categoria ativa, o tile abre o grupo inteiro do catálogo", () => {
    const geladas = filterProducts(catalog, { collectionRef: "bebidas-geladas" });
    const entries = gridEntries(geladas, catalog, "");
    expect(entries).toHaveLength(1);
    const tile = entries[0];
    if (tile?.kind !== "group") throw new Error("esperava o tile do grupo");
    expect(tile.group.options).toHaveLength(3);
  });

  it("com busca digitada, cada produto aparece sozinho (o Enter lança o SKU)", () => {
    const found = filterProducts(catalog, { query: "camille" });
    expect(gridEntries(found, catalog, "camille").map((entry) => entry.key)).toEqual(["product:CHCAM"]);
  });

  it("grupo de um produto só não vira tile de escolha", () => {
    expect(choiceGroupsByName([camille, espresso]).size).toBe(0);
    expect(gridEntries([camille, espresso], [camille, espresso], "").map((e) => e.key)).toEqual([
      "product:CHCAM",
      "product:SP",
    ]);
  });

  it("fica inerte só quando nenhuma opção entra no pedido", () => {
    const out = (p: POSProductProjection) => ({ ...p, sold_out: true });
    expect(choiceGroup(GROUP, [out(camille), rouge]).allBlocked).toBe(false);
    expect(choiceGroup(GROUP, [out(camille), out(rouge)]).allBlocked).toBe(true);
    expect(choiceGroup(GROUP, [camille, rouge]).priceLabel).toBe("R$ 14,00");
  });
});
