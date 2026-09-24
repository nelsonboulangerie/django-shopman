/**
 * Os selos do SKU: Comprável · Vendável · Produzido · Usado em receita.
 *
 * Um item comprado pode ser insumo E revenda — a manteiga que vai na massa e
 * que também se vende no balcão. O selo só diz o que é verdade.
 */
import { describe, expect, it } from "vitest";
import { skuRoleBadges } from "~/presentation/purchase";

describe("selos do SKU", () => {
  it("a manteiga que vai na massa e se vende no balcão leva três selos, na ordem", () => {
    expect(
      skuRoleBadges({ purchasable: true, sellable: true, produced: false, usedInRecipe: true }),
    ).toEqual(["Comprável", "Vendável", "Usado em receita"]);
  });

  it("a farinha só é comprável e usada em receita — nada de 'não vendável'", () => {
    expect(
      skuRoleBadges({ purchasable: true, sellable: false, produced: false, usedInRecipe: true }),
    ).toEqual(["Comprável", "Usado em receita"]);
  });

  it("sem papéis vindos do servidor, nenhum selo", () => {
    expect(skuRoleBadges(undefined)).toEqual([]);
  });
});
