// A Fila "Precisa de você" (V4-G4): urgência contra a meta, o resto agregado e o gesto
// com o verbo da v4. O fato e a meta vêm do servidor; aqui só relógio e ordem.
import { describe, expect, it } from "vitest";

import { goalTone, inKitchen, inProgress, minutesLabel, queueGesture, queueItems, queueWho, restLine, workingOrders } from "../app/presentation/queue";
import type { OrderCardProjection } from "../app/types/orders";

const NOW = Date.parse("2026-10-04T22:03:00Z");
const ago = (s: number) => new Date(NOW - s * 1000).toISOString();
const action = (ref: string, over: Record<string, unknown> = {}) => ({ ref, label: ref, enabled: true, priority: "primary", reason: "", payload_schema: {}, ...over }) as never;

function card(over: Partial<OrderCardProjection> = {}): OrderCardProjection {
  return {
    ref: "WEB-261004-R7K", status: "ready", attention: "dispatch", attention_since_iso: ago(27 * 60), goal_minutes: 30, goal_label: "meta 30 min",
    elapsed_seconds: 1620, created_at_iso: ago(1620), dispatched_at_iso: "", fulfillment_type: "delivery", fulfillment_label: "Entrega",
    delivery_address: "Rua Paranaguá, 800", customer_name: "João Oliveira", actions: [action("advance", { label: "Marcar saída para entrega" })],
    can_settle_delivery_cash: false, equipment_back_pending: false, next_status: "dispatched",
    ...over,
  } as OrderCardProjection;
}

describe("queueItems", () => {
  it("só entra o que espera alguém, o mais urgente primeiro", () => {
    const items = queueItems([
      card({ ref: "A-1-NEW", attention: "confirm", attention_since_iso: ago(120), goal_minutes: 5, goal_label: "meta 5 min" }),
      card({ ref: "A-1-R7K" }),
      card({ ref: "A-1-KIT", attention: "", status: "preparing" }),
      card({ ref: "A-1-F15", attention: "handoff", attention_since_iso: ago(360), goal_minutes: 10, goal_label: "no balcão" }),
    ], NOW);
    expect(items.map((i) => i.card.ref)).toEqual(["A-1-R7K", "A-1-F15", "A-1-NEW"]);
    expect(items[0]).toMatchObject({ timeLabel: "27 min", goalLabel: "meta 30 min", tone: "warning" });
    // Passou da metade da meta: atenção, como o iFood (dono, 13/11/2026).
    expect(items[1]).toMatchObject({ timeLabel: "6 min", goalLabel: "no balcão", tone: "warning" });
  });

  it("o mesmo pedido em duas listas (painel e encomendas) entra uma vez", () => {
    expect(queueItems([card(), card()], NOW)).toHaveLength(1);
  });

  it("tom contra a meta", () => {
    expect(goalTone(8 * 60, 5)).toBe("late");
    expect(goalTone(4 * 60, 5)).toBe("warning");
    expect(goalTone(2.5 * 60, 5)).toBe("warning");
    expect(goalTone(2 * 60, 5)).toBe("neutral");
    expect(goalTone(600, 0)).toBe("neutral");
    expect(minutesLabel(3900)).toBe("1h 5 min");
  });
});

describe("Em andamento e o excedente", () => {
  it("agrega o que não pede ninguém em Na Cozinha e Na rua", () => {
    const lines = inProgress([
      card({ attention: "", status: "preparing", created_at_iso: ago(600) }),
      card({ attention: "", status: "accepted", created_at_iso: ago(240), kitchen: { order_pk: 2, missing_label: "", stations: [{ station_ref: "cafes" }] } } as Partial<OrderCardProjection>),
      card({ attention: "", status: "dispatched", dispatched_at_iso: ago(18 * 60) }),
      card(),
    ], NOW);
    expect(lines).toEqual([
      expect.objectContaining({ key: "kitchen", count: 2, detail: "o mais antigo há 10 min" }),
      expect.objectContaining({ key: "road", count: 1, detail: "o mais antigo há 18 min" }),
    ]);
    expect(restLine(lines)).toEqual({ hidden: 0, moving: 3, text: "Seguem sozinhos: 2 na cozinha, 1 na rua" });
    expect(restLine(inProgress([card()], NOW))).toEqual({ hidden: 0, moving: 0, text: "" });
  });
});

describe("Na Cozinha é só o que foi para a cozinha (beta 05/11: GES-13, PDV2-03)", () => {
  it("aceito sem ticket ainda pede Iniciar preparo: não está na cozinha", () => {
    const waiting = card({ ref: "W-M99", attention: "", status: "accepted", kitchen: null });
    expect(inKitchen(waiting)).toBe(false);
    expect(inProgress([waiting], NOW)[0]).toMatchObject({ key: "kitchen", count: 0 });
    expect(workingOrders([waiting], NOW).kitchen).toEqual([]);
  });

  it("encomenda de amanhã não entra na cozinha de hoje, nem em preparo", () => {
    const tomorrow = card({ ref: "PDV-N84", attention: "", status: "preparing", is_preorder: true, commitment_date: "2026-10-05" });
    // De hoje: o servidor já não a chama de encomenda de outro dia (`is_preorder`).
    const today = card({ ref: "PDV-N85", attention: "", status: "preparing", is_preorder: false, commitment_date: "2026-10-04" });
    expect(inKitchen(tomorrow)).toBe(false);
    expect(inKitchen(today)).toBe(true);
    expect(workingOrders([tomorrow, today], NOW).kitchen.map((w) => w.card.ref)).toEqual(["PDV-N85"]);
  });

  it("o dia é o do servidor: o relógio e o fuso do dispositivo não entram na conta (WP-G09, P2-06)", () => {
    // A data combinada é o "hoje" de um tablet adiantado, e o servidor diz que é de outro dia.
    const deviceToday = new Date().toISOString().slice(0, 10);
    const other = card({ ref: "PDV-N86", attention: "", status: "preparing", is_preorder: true, commitment_date: deviceToday });
    expect(inKitchen(other)).toBe(false);
    // E o contrário: a data parece futura ao dispositivo, e o servidor diz que é de hoje.
    const mine = card({ ref: "PDV-N87", attention: "", status: "preparing", is_preorder: false, commitment_date: "2999-01-01" });
    expect(inKitchen(mine)).toBe(true);
  });
});

describe("queueGesture", () => {
  it("o botão diz o nome que o servidor dá ao gesto, o mesmo do Painel (#2758, item 4)", () => {
    const [dispatch] = queueItems([card({ actions: [action("advance", { label: "Despachar M09" })] })], NOW);
    expect(queueGesture(dispatch!).primary).toMatchObject({ ref: "advance", verb: "Despachar M09", label: "Despachar M09" });
    expect(queueGesture(dispatch!).shortcut).toBe("Enter");

    const [pickup] = queueItems([card({ attention: "handoff", fulfillment_type: "pickup", next_status: "completed", actions: [action("advance", { label: "Entregar a Ana" })] })], NOW);
    expect(queueGesture(pickup!).primary?.verb).toBe("Entregar a Ana");
    // Nunca os verbos próprios da Fila de antes.
    for (const item of [dispatch!, pickup!]) expect(["Saiu", "Retirou", "Entregue"]).not.toContain(queueGesture(item).primary?.verb);
  });

  it("pedido novo: Aceitar (A) e Recusar ao lado", () => {
    const [item] = queueItems([card({ status: "new", attention: "confirm", actions: [action("confirm", { label: "Aceitar" }), action("reject", { label: "Recusar", priority: "danger" })] })], NOW);
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
    expect(queueWho(card({ channel_name: "PDV" }))).toEqual({ name: "João Oliveira", rest: "Entrega · Rua Paranaguá, 800 · PDV" });
    // Sem canal, nada no lugar: nem travessão, nem ponto sobrando.
    expect(queueWho(card({ channel_name: "" }))).toEqual({ name: "João Oliveira", rest: "Entrega · Rua Paranaguá, 800" });
  });
});

it("duração antiga usa dias sem perder as horas restantes", () => {
  expect(minutesLabel(1046 * 3600)).toBe("43d 14h");
  expect(minutesLabel(24 * 3600)).toBe("1d");
});
