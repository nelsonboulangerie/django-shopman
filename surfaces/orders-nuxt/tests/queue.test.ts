// A Fila "Precisa de você" (V4-G4): urgência contra a meta, o resto agregado e o gesto
// com o verbo da v4. O fato e a meta vêm do servidor; aqui só relógio e ordem.
import { describe, expect, it } from "vitest";

import { goalTone, inProgress, minutesLabel, queueGesture, queueItems, queueWho, restLine } from "../app/presentation/queue";
import type { OrderCardProjection } from "../app/types/orders";

const NOW = Date.parse("2026-10-04T22:03:00Z");
const ago = (s: number) => new Date(NOW - s * 1000).toISOString();
const action = (ref: string, over: Record<string, unknown> = {}) => ({ ref, label: ref, enabled: true, priority: "primary", reason: "", payload_schema: {}, ...over }) as never;

function card(over: Partial<OrderCardProjection> = {}): OrderCardProjection {
  return {
    ref: "WEB-261004-R7K", status: "ready", attention: "dispatch", attention_since_iso: ago(27 * 60), goal_minutes: 30, goal_label: "meta 30",
    elapsed_seconds: 1620, created_at_iso: ago(1620), dispatched_at_iso: "", fulfillment_type: "delivery", fulfillment_label: "Entrega",
    delivery_address: "Rua Paranaguá, 800", customer_name: "João Oliveira", actions: [action("advance", { label: "Marcar saída para entrega" })],
    can_settle_delivery_cash: false, equipment_back_pending: false, next_status: "dispatched",
    ...over,
  } as OrderCardProjection;
}

describe("queueItems", () => {
  it("só entra o que espera alguém, o mais urgente primeiro", () => {
    const items = queueItems([
      card({ ref: "A-1-NEW", attention: "confirm", attention_since_iso: ago(120), goal_minutes: 5, goal_label: "meta 5" }),
      card({ ref: "A-1-R7K" }),
      card({ ref: "A-1-KIT", attention: "", status: "preparing" }),
      card({ ref: "A-1-F15", attention: "handoff", attention_since_iso: ago(360), goal_minutes: 10, goal_label: "no balcão" }),
    ], NOW);
    expect(items.map((i) => i.card.ref)).toEqual(["A-1-R7K", "A-1-F15", "A-1-NEW"]);
    expect(items[0]).toMatchObject({ timeLabel: "27 min", goalLabel: "meta 30", tone: "warning" });
    expect(items[1]).toMatchObject({ timeLabel: "6 min", goalLabel: "no balcão", tone: "ok" });
  });

  it("o mesmo pedido em duas listas (quadro e encomendas) entra uma vez", () => {
    expect(queueItems([card(), card()], NOW)).toHaveLength(1);
  });

  it("tom contra a meta", () => {
    expect(goalTone(8 * 60, 5)).toBe("late");
    expect(goalTone(4 * 60, 5)).toBe("warning");
    expect(goalTone(60, 5)).toBe("ok");
    expect(goalTone(600, 0)).toBe("ok");
    expect(minutesLabel(3900)).toBe("1h 5 min");
  });
});

describe("Em andamento e o excedente", () => {
  it("agrega o que não pede ninguém em Na Cozinha e Na rua", () => {
    const lines = inProgress([
      card({ attention: "", status: "preparing", created_at_iso: ago(600) }),
      card({ attention: "", status: "accepted", created_at_iso: ago(240) }),
      card({ attention: "", status: "dispatched", dispatched_at_iso: ago(18 * 60) }),
      card(),
    ], NOW);
    expect(lines).toEqual([
      expect.objectContaining({ key: "kitchen", count: 2, detail: "o mais antigo há 10 min" }),
      expect.objectContaining({ key: "road", count: 1, detail: "o mais antigo há 18 min" }),
    ]);
    expect(restLine(lines)).toEqual({ hidden: 0, moving: 3, text: "Sem pedir você: 2 na cozinha, 1 na rua" });
    expect(restLine(inProgress([card()], NOW))).toEqual({ hidden: 0, moving: 0, text: "" });
  });
});

describe("queueGesture", () => {
  it("o fato humano com o verbo da v4; o rótulo do servidor segue no title", () => {
    const [dispatch] = queueItems([card()], NOW);
    expect(queueGesture(dispatch!).primary).toMatchObject({ ref: "advance", verb: "Saiu", label: "Marcar saída para entrega" });
    expect(queueGesture(dispatch!).shortcut).toBe("Enter");

    const [pickup] = queueItems([card({ attention: "handoff", fulfillment_type: "pickup", next_status: "completed" })], NOW);
    expect(queueGesture(pickup!).primary?.verb).toBe("Retirou");
  });

  it("pedido novo: Aceitar (A) e Recusar ao lado", () => {
    const [item] = queueItems([card({ status: "new", attention: "confirm", actions: [action("confirm", { label: "Confirmar" }), action("reject", { label: "Recusar", priority: "danger" })] })], NOW);
    const gesture = queueGesture(item!);
    expect(gesture.primary).toMatchObject({ ref: "confirm", verb: "Aceitar" });
    expect(gesture.secondary).toMatchObject({ ref: "reject", label: "Recusar" });
    expect(gesture.shortcut).toBe("A");
  });

  it("bloqueado: o gesto aparece travado com o rótulo do servidor", () => {
    const [item] = queueItems([card({ status: "new", attention: "blocked", actions: [action("confirm", { label: "Aceitar", enabled: false, reason: "Pix pendente" })] })], NOW);
    expect(queueGesture(item!).primary).toMatchObject({ disabled: true, verb: "Aceitar", reason: "Pix pendente" });
  });

  it("quem e para onde", () => {
    expect(queueWho(card(), "PDV")).toEqual({ name: "João Oliveira", rest: "Entrega · Rua Paranaguá, 800 · PDV" });
  });
});
