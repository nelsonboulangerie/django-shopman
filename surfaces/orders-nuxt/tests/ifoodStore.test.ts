import { describe, expect, it } from "vitest";

import { ifoodStatusLine, queueSignal } from "../app/presentation/ifoodStore";
import type { IFoodStoreProjection } from "../app/types/ifoodStore";

function store(over: Partial<IFoodStoreProjection> = {}): IFoodStoreProjection {
  return {
    enabled: true,
    governs: true,
    channel_off: false,
    can_open_channels: true,
    shop_open: true,
    shop_message: "Aberto até 18h",
    ifood_available: true,
    ifood_status_label: "Recebendo pedidos",
    ifood_checked_at_display: "09:55",
    ifood_problems: [],
    diverges: false,
    ...over,
  };
}

describe("ifoodStatusLine", () => {
  it("diz o que o iFood informou e quando foi conferido", () => {
    expect(ifoodStatusLine(store())).toBe("iFood: recebendo pedidos (conferido às 09:55)");
  });

  it("sem conferência, diz isso — nunca inventa um estado", () => {
    expect(ifoodStatusLine(store({ ifood_available: null, ifood_status_label: "Ainda sem conferência com o iFood" })))
      .toBe("Ainda sem conferência com o iFood");
  });
});

describe("queueSignal", () => {
  it("estado normal: nada", () => {
    expect(queueSignal(store())).toBe("");
    expect(queueSignal(null)).toBe("");
  });

  it("canal desligado no Gestor vence a divergência: é o que explica a fila", () => {
    expect(queueSignal(store({ channel_off: true, diverges: true, ifood_available: false })))
      .toBe("iFood desligado no Gestor: nenhum pedido do iFood entra");
  });

  it("divergências dizem o lado que importa à fila", () => {
    expect(queueSignal(store({ diverges: true, ifood_available: false })))
      .toBe("iFood fechado com a loja aberta: nenhum pedido do iFood entra");
    expect(queueSignal(store({ diverges: true, ifood_available: true, shop_open: false })))
      .toBe("iFood recebendo pedidos com a loja fechada");
  });
});
