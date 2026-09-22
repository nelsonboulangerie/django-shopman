import { describe, expect, it } from "vitest";

import { ifoodStatusLine } from "../app/presentation/ifoodStore";
import type { IFoodStoreProjection } from "../app/types/ifoodStore";

function store(over: Partial<IFoodStoreProjection> = {}): IFoodStoreProjection {
  return {
    enabled: true,
    governs: true,
    channel_off: false,
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
