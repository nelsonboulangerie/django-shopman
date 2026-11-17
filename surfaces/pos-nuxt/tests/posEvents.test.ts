import { describe, expect, it } from "vitest";

import { mergeAvailability, refreshScopeForChannel, shouldConnectSse, shouldPollTick } from "../app/presentation/events";

describe("refreshScopeForChannel — o aviso de comanda relê só o quadro", () => {
  it("o stream das comandas relê só o quadro", () => {
    expect(refreshScopeForChannel("/sse/tabs")).toBe("tabs");
  });

  it("o stream de estoque relê só os selos da grade (WP-E4)", () => {
    expect(refreshScopeForChannel("/sse/stock")).toBe("availability");
  });

  it("caixa, poll e volta à aba relêem a projeção inteira", () => {
    expect(refreshScopeForChannel("/sse/cash")).toBe("all");
    expect(refreshScopeForChannel(undefined)).toBe("all");
  });
});

describe("shouldPollTick — o poll é fallback, não segundo canal", () => {
  it("com o SSE vivo, o tick não refaz nada (o push já refez)", () => {
    expect(shouldPollTick("live")).toBe(false);
  });

  it("sem o SSE de pé, o tick carrega a tela", () => {
    expect(shouldPollTick("polling")).toBe(true);
    // Conectando ainda não é vivo: até o onopen, quem garante dado é o poll.
    expect(shouldPollTick("connecting")).toBe(true);
  });
});

describe("shouldConnectSse — o SSE só conecta com a estação identificada (F3)", () => {
  it("por padrão (sem gate) conecta", () => {
    expect(shouldConnectSse(undefined)).toBe(true);
  });

  it("com o gate desabilitado, não conecta — o poll de fallback cobre", () => {
    expect(shouldConnectSse(false)).toBe(false);
  });

  it("estação identificada e desbloqueada conecta", () => {
    expect(shouldConnectSse(true)).toBe(true);
  });
});

describe("mergeAvailability — o selo troca sem ninguém tocar (WP-E4)", () => {
  const grid = [
    { sku: "BAGUETE", name: "Baguete", price_q: 1200, sold_out: false, sold_out_reason: "" },
    { sku: "CAIXA-NATAL", name: "Caixa de Natal", price_q: 9000, sold_out: false, sold_out_reason: "" },
    { sku: "CROISSANT", name: "Croissant", price_q: 900, sold_out: true, sold_out_reason: "" },
  ];

  it("outro balcão vendeu a última unidade: o tile vira Esgotado, o resto do tile fica igual", () => {
    const next = mergeAvailability(grid, [
      { sku: "BAGUETE", sold_out: true, sold_out_reason: "" },
      { sku: "CAIXA-NATAL", sold_out: false, sold_out_reason: "" },
      { sku: "CROISSANT", sold_out: true, sold_out_reason: "" },
    ]);
    expect(next).not.toBe(grid);
    expect(next[0]).toEqual({ ...grid[0], sold_out: true, sold_out_reason: "" });
    // O tile que não mudou é o MESMO objeto: o Vue não redesenha o que não mexeu.
    expect(next[1]).toBe(grid[1]);
    expect(next[2]).toBe(grid[2]);
  });

  it("o lote entrou: o esgotado volta a vender", () => {
    const next = mergeAvailability(grid, [{ sku: "CROISSANT", sold_out: false, sold_out_reason: "" }]);
    expect(next[2]!.sold_out).toBe(false);
  });

  it("a caixa física do kit acabou: o motivo chega junto (Sem caixa)", () => {
    const next = mergeAvailability(grid, [{ sku: "CAIXA-NATAL", sold_out: true, sold_out_reason: "Sem caixa" }]);
    expect(next[1]).toMatchObject({ sold_out: true, sold_out_reason: "Sem caixa" });
  });

  it("aviso que não muda selo nenhum devolve a MESMA lista (a grade não redesenha)", () => {
    expect(mergeAvailability(grid, [{ sku: "BAGUETE", sold_out: false, sold_out_reason: "" }])).toBe(grid);
    expect(mergeAvailability(grid, [])).toBe(grid);
  });

  it("SKU fora da leitura atual (sem preço, fora da grade) é ignorado", () => {
    expect(mergeAvailability(grid, [{ sku: "FARINHA", sold_out: true, sold_out_reason: "" }])).toBe(grid);
  });
});
