import { describe, expect, it } from "vitest";

import {
  MAX_SWAP_SKUS,
  queryWithoutSwap,
  swapFocus,
  swapSkusFromQuery,
  swapUnsearchedTitle,
} from "~/presentation/preorderSwap";
import type { PreorderSwapItem, PreorderSwapResponse } from "~/types/preorders";

// A troca vinda do link do Gestor (#2765): o endereço leva só a intenção.

function item(sku: string, partial: Partial<PreorderSwapItem> = {}): PreorderSwapItem {
  return {
    sku, name: sku, qty: "1", qty_label: `1x ${sku}`, fact: "", searched: true, options: [], empty_phrase: "", ...partial,
  };
}

describe("swapSkusFromQuery", () => {
  it("lê um SKU ou vários, na ordem, sem vazios nem repetidos", () => {
    expect(swapSkusFromQuery("BAGUETE")).toEqual(["BAGUETE"]);
    expect(swapSkusFromQuery(["BAGUETE", " BRIOCHE ", "", "BAGUETE"])).toEqual(["BAGUETE", "BRIOCHE"]);
  });

  it("parâmetro inválido vira nada, em silêncio", () => {
    expect(swapSkusFromQuery(undefined)).toEqual([]);
    expect(swapSkusFromQuery(null)).toEqual([]);
    expect(swapSkusFromQuery({ sku: "X" })).toEqual([]);
    expect(swapSkusFromQuery("x".repeat(65))).toEqual([]);
  });

  it("corta no mesmo teto do servidor", () => {
    const many = Array.from({ length: MAX_SWAP_SKUS + 5 }, (_, i) => `SKU${i}`);
    expect(swapSkusFromQuery(many)).toHaveLength(MAX_SWAP_SKUS);
  });
});

describe("queryWithoutSwap", () => {
  it("tira só o item trocado e mantém o resto do endereço", () => {
    expect(queryWithoutSwap({ swap: ["A", "B"], back: "/preorders" }, "A")).toEqual({ swap: ["B"], back: "/preorders" });
    expect(queryWithoutSwap({ swap: "A", back: "/preorders" }, "A")).toEqual({ back: "/preorders" });
  });
});

describe("swapFocus", () => {
  it("o foco é o primeiro item a trocar; sem item, nenhum", () => {
    const read = { items: [item("A"), item("B")] } as PreorderSwapResponse;
    expect(swapFocus(read)).toBe("swap:A");
    expect(swapFocus({ ...read, items: [] })).toBeNull();
    expect(swapFocus(null)).toBeNull();
  });
});

describe("swapUnsearchedTitle", () => {
  it("nomeia o item quando é um só, e nunca diz que não há", () => {
    expect(swapUnsearchedTitle([item("Baguete", { searched: false }), item("Brioche")])).toBe(
      "Não deu para procurar agora o que trocar por Baguete.",
    );
    expect(swapUnsearchedTitle([item("A", { searched: false }), item("B", { searched: false })])).toBe(
      "Não deu para procurar agora as alternativas da troca.",
    );
  });
});
