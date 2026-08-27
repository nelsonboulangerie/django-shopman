import { describe, expect, it } from "vitest";

import { askedMarkFor, shouldAskFulfillment, type FulfillmentPromptState } from "~/presentation/fulfillmentPrompt";

function state(overrides: Partial<FulfillmentPromptState> = {}): FulfillmentPromptState {
  return {
    inSaleView: true,
    checkoutMode: false,
    hasOpenTab: true,
    itemCount: 0,
    askedFor: "",
    tabSessionKey: "SESS-1",
    ...overrides,
  };
}

describe("shouldAskFulfillment — quando a primeira pergunta aparece", () => {
  it("comanda aberta e vazia, na tela de venda: pergunta", () => {
    expect(shouldAskFulfillment(state())).toBe(true);
  });

  it("no quadro de comandas, não", () => {
    expect(shouldAskFulfillment(state({ inSaleView: false }))).toBe(false);
  });

  it("no checkout, não — a pergunta é do começo, não do fim", () => {
    expect(shouldAskFulfillment(state({ checkoutMode: true }))).toBe(false);
  });

  it("sem comanda aberta, não", () => {
    expect(shouldAskFulfillment(state({ hasOpenTab: false }))).toBe(false);
  });

  it("com item já lançado, não — quem começou a vender já respondeu com o corpo", () => {
    expect(shouldAskFulfillment(state({ itemCount: 1 }))).toBe(false);
  });

  it("respondida nesta comanda, não volta", () => {
    expect(shouldAskFulfillment(state({ askedFor: "SESS-1" }))).toBe(false);
  });

  it("respondida na comanda ANTERIOR, volta na próxima", () => {
    // O atendimento seguinte é outro cliente: a pergunta é dele também.
    expect(shouldAskFulfillment(state({ askedFor: "SESS-0", tabSessionKey: "SESS-1" }))).toBe(true);
  });
});

describe("askedMarkFor — a marca de 'já perguntei'", () => {
  it("usa a comanda como chave", () => {
    expect(askedMarkFor("SESS-9")).toBe("SESS-9");
  });

  it("sem comanda, cai num sentinela que nunca é uma chave real", () => {
    // Marcar com string vazia deixaria a pergunta 'respondida' para a PRÓXIMA
    // comanda, que nasce sem chave por um instante.
    const mark = askedMarkFor("");
    expect(mark).not.toBe("");
    expect(shouldAskFulfillment(state({ askedFor: mark, tabSessionKey: "SESS-2" }))).toBe(true);
  });
});
