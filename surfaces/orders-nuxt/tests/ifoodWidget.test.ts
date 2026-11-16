import { describe, expect, it } from "vitest";

import { ifoodChatNotice, ifoodWidgetInit, ifoodWidgetLift } from "../app/presentation/ifoodWidget";

describe("widget do iFood: quando iniciar", () => {
  it("sem ID do widget ou sem loja, não inicia (init vazio apaga a autorização)", () => {
    expect(ifoodWidgetInit(null)).toBeNull();
    expect(ifoodWidgetInit({ widget_id: "", merchant_ids: ["m1"] })).toBeNull();
    expect(ifoodWidgetInit({ widget_id: "  ", merchant_ids: ["m1"] })).toBeNull();
    expect(ifoodWidgetInit({ widget_id: "w1", merchant_ids: [] })).toBeNull();
    expect(ifoodWidgetInit({ widget_id: "w1", merchant_ids: [" "] })).toBeNull();
  });

  it("com os dois, inicia com o ID e as lojas (até 10, o limite do iFood)", () => {
    expect(ifoodWidgetInit({ widget_id: " w1 ", merchant_ids: ["m1"] })).toEqual({
      widgetId: "w1",
      merchantIds: ["m1"],
    });
    const many = Array.from({ length: 12 }, (_, i) => `m${i}`);
    expect(ifoodWidgetInit({ widget_id: "w1", merchant_ids: many })?.merchantIds).toHaveLength(10);
  });
});

describe("widget do iFood: o aviso no detalhe do pedido", () => {
  it("fora do iFood ou com o widget desligado, não aparece", () => {
    expect(ifoodChatNotice("ready", false)).toBeNull();
    expect(ifoodChatNotice("off", true)).toBeNull();
  });

  it("pronto: diz onde o chat está", () => {
    const notice = ifoodChatNotice("ready", true);
    expect(notice?.tone).toBe("info");
    expect(notice?.description).toContain("botão do iFood");
  });

  it("falhou: avisa e manda para o Gestor do iFood", () => {
    const notice = ifoodChatNotice("failed", true);
    expect(notice?.tone).toBe("warning");
    expect(notice?.description).toContain("Gestor do iFood");
  });

  it("nenhuma frase usa travessão", () => {
    for (const state of ["loading", "ready", "failed"] as const) {
      const notice = ifoodChatNotice(state, true)!;
      expect(`${notice.title} ${notice.description}`).not.toMatch(/[—–]/);
    }
  });
});

describe("o botão do iFood não tampa a base", () => {
  it("sobe o que a base ocupa além da margem do Portal, com respiro", () => {
    // barra das seções (81) + área segura do iPhone (34): 115 + 12 - 96
    expect(ifoodWidgetLift(115, false)).toBe(31);
    // barra das seções + barra de ação da tela
    expect(ifoodWidgetLift(160, false)).toBe(76);
  });

  it("sem base alta, fica onde o Portal pôs; com a conversa aberta, não sobe", () => {
    expect(ifoodWidgetLift(0, false)).toBe(0);
    expect(ifoodWidgetLift(60, false)).toBe(0);
    expect(ifoodWidgetLift(160, true)).toBe(0);
  });
});
