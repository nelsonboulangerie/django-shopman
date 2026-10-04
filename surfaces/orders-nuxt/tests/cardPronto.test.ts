// V4-G4: os dois dados do cartão que faltavam. O relógio conta desde o pronto ("pronto há
// 6 min") e desde a saída ("na rua há 18 min"); a etiqueta diz "N volumes" quando quem
// embalou declarou, e conta itens enquanto ninguém declarou (volume nunca é deduzido).
import { describe, expect, it } from "vitest";

import { cardClock, packLabel, secondsSince } from "../app/presentation/board";
import type { OrderCardProjection } from "../app/types/orders";

const NOW = Date.parse("2026-10-04T15:00:00Z");
const ago = (s: number) => new Date(NOW - s * 1000).toISOString();

function card(over: Partial<OrderCardProjection> = {}): OrderCardProjection {
  return {
    ref: "WEB-261004-U13", status: "ready", confirmation_deadline_iso: "", confirmation_action: "",
    elapsed_seconds: 1620, timer_class: "timer-muted", ready_at_iso: "", dispatched_at_iso: "", items_count: 2, volumes: 0,
    ...over,
  } as OrderCardProjection;
}

describe("cardClock com a hora do pronto e da saída", () => {
  it("pronto conta desde o pronto, não desde a chegada", () => {
    expect(cardClock(card({ ready_at_iso: ago(360) }), NOW).text).toBe("pronto há 6 min");
    expect(cardClock(card({ ready_at_iso: ago(20) }), NOW).text).toBe("pronto agora");
  });

  it("na rua conta desde a saída", () => {
    expect(cardClock(card({ status: "dispatched", dispatched_at_iso: ago(1080) }), NOW).text).toBe("na rua há 18 min");
    expect(cardClock(card({ status: "dispatched", dispatched_at_iso: ago(10) }), NOW).text).toBe("saiu agora");
  });

  it("sem os instantes, segue o decorrido desde a chegada", () => {
    expect(cardClock(card(), NOW).text).toBe("há 27 min");
  });

  it("o prazo de confirmação continua vencendo tudo", () => {
    const deadline = new Date(NOW + 100_000).toISOString();
    expect(cardClock(card({ status: "new", confirmation_deadline_iso: deadline, ready_at_iso: ago(60) }), NOW).countdown).toBe(true);
  });

  it("instante ilegível não vira número", () => {
    expect(secondsSince("ontem", NOW)).toBeNull();
    expect(secondsSince("", NOW)).toBeNull();
  });
});

describe("packLabel", () => {
  it("volumes declarados vencem a contagem de itens", () => {
    expect(packLabel(card({ volumes: 2 }))).toBe("2 volumes");
    expect(packLabel(card({ volumes: 1 }))).toBe("1 volume");
  });

  it("sem declaração, conta itens (nunca deduz volume)", () => {
    expect(packLabel(card())).toBe("2 itens");
    expect(packLabel(card({ items_count: 1 }))).toBe("1 item");
    expect(packLabel(card({ items_count: 0 }))).toBe("");
  });
});
