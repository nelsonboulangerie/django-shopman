import { describe, expect, it } from "vitest";

import type { POSProductProjection } from "../app/types/pos";
import {
  enterTargetProduct,
  filterProducts,
  gridEntries,
  hiddenUnavailableLabel,
  hideUnavailableProducts,
  isUnavailableProduct,
  parseHideUnavailable,
  productsForOrderDate,
} from "../app/presentation/catalog";

function product(overrides: Partial<POSProductProjection> & { sku: string }): POSProductProjection {
  return {
    name: overrides.sku,
    price_q: 1400,
    price_display: "R$ 14,00",
    collection_ref: "paes",
    collection_color: "",
    collection_icon: "",
    image_url: "",
    ...overrides,
  };
}

const baguete = product({ sku: "BAG", name: "Baguete" });
const brioche = product({ sku: "BRI", name: "Brioche", sold_out: true });
const semPreco = product({ sku: "SP0", name: "Broa", price_q: 0, price_display: "" });
const semCaixa = product({ sku: "CX", name: "Caixa de bombons", sold_out: true, sold_out_reason: "Sem caixa" });
const catalog = [baguete, brioche, semPreco, semCaixa];

describe("presentation/catalog — ocultar indisponíveis", () => {
  it("indisponível é o mesmo critério do selo do tile: esgotado ou sem preço", () => {
    expect(isUnavailableProduct(baguete)).toBe(false);
    expect(isUnavailableProduct(brioche)).toBe(true);
    expect(isUnavailableProduct(semPreco)).toBe(true);
    expect(isUnavailableProduct(semCaixa)).toBe(true);
  });

  it("desligado, a grade é a mesma de sempre e nada conta como oculto", () => {
    const result = hideUnavailableProducts(catalog, false);
    expect(result.products).toBe(catalog);
    expect(result.hiddenCount).toBe(0);
  });

  it("ligado, sai só o indisponível e a conta diz quantos saíram", () => {
    const result = hideUnavailableProducts(catalog, true);
    expect(result.products.map((p) => p.sku)).toEqual(["BAG"]);
    expect(result.hiddenCount).toBe(3);
  });

  it("busca que só acha indisponível: grade vazia com a conta dos ocultos", () => {
    const matched = filterProducts(catalog, { query: "bri" });
    const result = hideUnavailableProducts(matched, true);
    expect(result.products).toEqual([]);
    expect(result.hiddenCount).toBe(1);
    expect(hiddenUnavailableLabel(result.hiddenCount)).toBe("1 indisponível oculto");
    expect(hiddenUnavailableLabel(4)).toBe("4 indisponíveis ocultos");
  });

  it("o Enter da busca continua lançando o primeiro disponível", () => {
    const result = hideUnavailableProducts(filterProducts(catalog, { query: "b" }), true);
    expect(enterTargetProduct(result.products, "b")?.sku).toBe("BAG");
  });

  it("oculto, a opção indisponível sai do cartão de escolha", () => {
    const camille = product({ sku: "CHCAM", choice_group: "Chás" });
    const rouge = product({ sku: "CHROU", choice_group: "Chás" });
    const hibisco = product({ sku: "CHHIB", choice_group: "Chás", sold_out: true });
    const all = [camille, rouge, hibisco];
    const visible = hideUnavailableProducts(all, true).products;
    const tile = gridEntries(visible, visible, "")[0];
    if (tile?.kind !== "group") throw new Error("esperava o tile do grupo");
    expect(tile.group.options.map((o) => o.sku)).toEqual(["CHCAM", "CHROU"]);
  });

  it("o storage só liga com '1'; vazio ou lixo é o padrão (mostrar)", () => {
    expect(parseHideUnavailable("1")).toBe(true);
    expect(parseHideUnavailable("0")).toBe(false);
    expect(parseHideUnavailable(null)).toBe(false);
    expect(parseHideUnavailable("true")).toBe(false);
  });
});

describe("productsForOrderDate — a grade da encomenda lê o saldo do dia combinado", () => {
  // Beta test de 05/11/2026 (PDV2-04): o esgotado de HOJE bloqueava a
  // encomenda para amanhã, e o que a grade deixava entrar o salvamento recusava.
  const amanha = { date: "2026-11-07", is_today: false, sold_out_skus: ["BAG"] };

  it("o esgotado de hoje entra amanhã; o sem saldo amanhã sai com a data no motivo", () => {
    const grade = productsForOrderDate([baguete, brioche], amanha, "2026-11-07");
    expect(grade.find((p) => p.sku === "BRI")?.sold_out).toBe(false);
    expect(grade.find((p) => p.sku === "BAG")).toMatchObject({ sold_out: true, sold_out_reason: "Sem saldo para 07/11" });
  });

  it("bloqueio com motivo do catálogo continua", () => {
    const grade = productsForOrderDate([semCaixa], amanha, "2026-11-07");
    expect(grade[0]).toBe(semCaixa);
  });

  it("sem a resposta da data escolhida, ou para hoje, a grade fica como está", () => {
    const produtos = [baguete, brioche];
    expect(productsForOrderDate(produtos, null, "2026-11-07")).toBe(produtos);
    expect(productsForOrderDate(produtos, amanha, "2026-11-08")).toBe(produtos);
    expect(productsForOrderDate(produtos, { ...amanha, is_today: true }, "2026-11-07")).toBe(produtos);
    expect(productsForOrderDate(produtos, amanha, "")).toBe(produtos);
  });
});
