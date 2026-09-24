/**
 * Os selos do SKU: Comprável · Vendável · Produzido · Usado em receita.
 *
 * Um item comprado pode ser insumo E revenda — a manteiga que vai na massa e
 * que também se vende no balcão. O selo só diz o que é verdade.
 */
import { describe, expect, it } from "vitest";
import { resaleCopy, resaleSuggestionView, skuRoleBadges } from "~/presentation/purchase";

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

describe("Permitir revenda", () => {
  it("vendido por peso diz que é só no balcão e pede o preço do quilo", () => {
    const copy = resaleCopy("kg", "149,90");
    expect(copy.priceLabel).toBe("Preço por kg (R$)");
    expect(copy.reach).toBe("Vendido só no balcão, por peso.");
    expect(copy.ready).toBe(true);
  });

  it("preço zero ou ilegível não deixa colocar à venda", () => {
    expect(resaleCopy("un", "0,00").ready).toBe(false);
    expect(resaleCopy("un", "").ready).toBe(false);
    expect(resaleCopy("un", "abc").ready).toBe(false);
  });

  it("por unidade entra no PDV, e na loja online só com foto", () => {
    expect(resaleCopy("un", "42").reach).toBe("Entra no PDV. Na loja online, só com foto.");
  });
});

describe("sugestão de preço da revenda", () => {
  it("vem pronta para o campo e diz de onde saiu", () => {
    const view = resaleSuggestionView({ priceQ: 4200, costQ: 2790, markupPct: 50, markupCategory: "Mercearia" }, "un");
    expect(view?.input).toBe("42,00");
    expect(view?.basis).toContain("markup 50% (categoria Mercearia)");
  });

  it("sem categoria própria diz que é o padrão da loja; sem custo, não sugere", () => {
    expect(resaleSuggestionView({ priceQ: 1500, costQ: 1000, markupPct: 50, markupCategory: "" }, "un")?.basis)
      .toContain("(padrão da loja)");
    expect(resaleSuggestionView(null, "un")).toBeNull();
  });
});
