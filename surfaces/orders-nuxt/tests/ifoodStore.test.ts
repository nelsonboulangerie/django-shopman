import { describe, expect, it } from "vitest";

import {
  ifoodStatusLine,
  pauseInFlight,
  pauseTrail,
  queueSignal,
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

  it("o sinal da aba Pedidos: em estado normal, nada — e nunca com a integração desligada", () => {
    const now = new Date("2026-12-22T10:30:00-03:00");
    expect(queueSignal(store(), now)).toBe("");
    expect(queueSignal(store({ enabled: false, diverges: true, pause: pause() }), now)).toBe("");
    expect(queueSignal(null, now)).toBe("");
  });

  it("o sinal diz a pausa: até quando e por quê; em trânsito, o que está acontecendo", () => {
    const now = new Date("2026-12-22T10:30:00-03:00");
    expect(queueSignal(store({ pause: pause() }), now)).toBe("iFood pausado até 11:00 — Cozinha cheia");
    expect(queueSignal(store({ pause: pause({ state: "pending_create" }) }), now)).toBe("Pedindo a pausa ao iFood…");
    expect(queueSignal(store({ pause: pause({ state: "pending_remove" }) }), now)).toBe("Retomando os pedidos no iFood…");
  });

  it("o sinal diz a divergência pelo lado que importa à fila", () => {
    const now = new Date("2026-12-22T10:30:00-03:00");
    expect(queueSignal(store({ diverges: true, ifood_available: false, ifood_status_label: "Fechado para pedidos" }), now))
      .toBe("iFood fechado com a loja aberta: nenhum pedido do iFood entra");
    expect(queueSignal(store({ diverges: true, shop_open: false }), now)).toBe("iFood recebendo pedidos com a loja fechada");
  });

  it("a recusa vira sinal só enquanto dura a janela que o gestor pediu", () => {
    const refused = pause({ state: "failed", error: "O iFood recusou o pedido (HTTP 409).", requested_at_display: "10:00" });
    expect(queueSignal(store({ last_pause: refused }), new Date("2026-12-22T10:30:00-03:00")))
      .toBe("O iFood recusou a pausa pedida às 10:00");
    expect(queueSignal(store({ last_pause: refused }), new Date("2026-12-22T11:30:00-03:00"))).toBe("");
    expect(queueSignal(store({ last_pause: pause({ state: "removed" }) }), new Date("2026-12-22T10:30:00-03:00"))).toBe("");
  });

  it("pausa em trânsito é pedida ou retomada, não em vigor", () => {
    expect(pauseInFlight(store({ pause: pause({ state: "pending_create" }) }))).toBe(true);
    expect(pauseInFlight(store({ pause: pause() }))).toBe(false);
  });
});
