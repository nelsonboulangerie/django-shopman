import { describe, expect, it } from "vitest";

import { refreshScopeForChannel, shouldConnectSse, shouldPollTick } from "../app/presentation/events";

describe("refreshScopeForChannel — o aviso de comanda relê só o quadro", () => {
  it("o stream das comandas relê só o quadro", () => {
    expect(refreshScopeForChannel("/sse/tabs")).toBe("tabs");
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
