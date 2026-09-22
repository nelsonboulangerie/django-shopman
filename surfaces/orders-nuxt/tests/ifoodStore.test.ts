import { describe, expect, it } from "vitest";

import {
  ifoodStatusLine,
  menuNeedsAttention,
  pauseInFlight,
  pauseTrail,
  refusedPauseLine,
} from "../app/presentation/ifoodStore";
import type { IFoodPause, IFoodStoreProjection } from "../app/types/ifoodStore";

function pause(over: Partial<IFoodPause> = {}): IFoodPause {
  return {
    ref: 1,
    state: "active",
    state_label: "Em vigor no iFood",
    reason: "Cozinha cheia",
    starts_at: "2026-12-22T10:00:00-03:00",
    ends_at: "2026-12-22T11:00:00-03:00",
    ends_at_display: "11:00",
    requested_by: "Ana",
    requested_at_display: "10:00",
    removed_by: "",
    error: "",
    ...over,
  };
}

function store(over: Partial<IFoodStoreProjection> = {}): IFoodStoreProjection {
  return {
    enabled: true,
    governs: true,
    can_pause: true,
    shop_open: true,
    shop_message: "Aberto até 18h",
    ifood_available: true,
    ifood_status_label: "Recebendo pedidos",
    ifood_checked_at_display: "09:55",
    ifood_problems: [],
    diverges: false,
    pause: null,
    last_pause: null,
    options: [],
    ...over,
  };
}

describe("a loja no iFood — frases", () => {
  it("diz o que o iFood faz agora, com a hora da conferência", () => {
    expect(ifoodStatusLine(store())).toBe("iFood: recebendo pedidos (conferido às 09:55)");
    expect(ifoodStatusLine(store({ ifood_available: null, ifood_status_label: "Ainda sem conferência com o iFood" })))
      .toBe("Ainda sem conferência com o iFood");
  });

  it("a pausa manda na frase: pedida, em vigor, sendo retomada", () => {
    expect(ifoodStatusLine(store({ pause: pause({ state: "pending_create" }) }))).toBe("Pedindo a pausa ao iFood…");
    expect(ifoodStatusLine(store({ pause: pause() }))).toBe("iFood pausado até 11:00");
    expect(ifoodStatusLine(store({ pause: pause({ state: "pending_remove" }) }))).toBe("Retomando os pedidos no iFood…");
  });

  it("a trilha diz motivo, quem e quando", () => {
    expect(pauseTrail(pause())).toBe("Motivo: Cozinha cheia. Pausado por Ana às 10:00.");
  });

  it("a recusa do iFood fica na tela, e só ela entre as pausas encerradas", () => {
    const refused = pause({ state: "failed", error: "O iFood recusou: já existe outra pausa no mesmo horário." });
    expect(refusedPauseLine(store({ last_pause: refused }))).toContain("mesmo horário");
    expect(refusedPauseLine(store({ last_pause: pause({ state: "removed" }) }))).toBe("");
  });

  it("o ponto de atenção acende só com divergência, pausa ou recusa — e nunca desligado", () => {
    expect(menuNeedsAttention(store())).toBe(false);
    expect(menuNeedsAttention(store({ diverges: true }))).toBe(true);
    expect(menuNeedsAttention(store({ pause: pause() }))).toBe(true);
    expect(menuNeedsAttention(store({ enabled: false, diverges: true }))).toBe(false);
    expect(menuNeedsAttention(null)).toBe(false);
  });

  it("pausa em trânsito é pedida ou retomada, não em vigor", () => {
    expect(pauseInFlight(store({ pause: pause({ state: "pending_create" }) }))).toBe(true);
    expect(pauseInFlight(store({ pause: pause() }))).toBe(false);
  });
});
