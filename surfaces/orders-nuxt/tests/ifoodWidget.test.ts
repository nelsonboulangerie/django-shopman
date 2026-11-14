import { describe, expect, it } from "vitest";

import { ifoodChatNotice, ifoodWidgetInit, ifoodWidgetVisible } from "../app/presentation/ifoodWidget";

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
      autoShow: false,
    });
    const many = Array.from({ length: 12 }, (_, i) => `m${i}`);
    expect(ifoodWidgetInit({ widget_id: "w1", merchant_ids: many })?.merchantIds).toHaveLength(10);
  });
});

describe("widget do iFood: quando o botão aparece (DEV-2026-023)", () => {
  it("com pedido iFood em andamento, em qualquer tela", () => {
    expect(ifoodWidgetVisible(true, false)).toBe(true);
  });
  it("no detalhe de um pedido iFood, mesmo entregue", () => {
    expect(ifoodWidgetVisible(false, true)).toBe(true);
  });
  it("sem pedido iFood em andamento e fora de um pedido iFood, some", () => {
    expect(ifoodWidgetVisible(false, false)).toBe(false);
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
