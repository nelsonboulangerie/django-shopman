// V6-GESTOR (auditoria v4): recortes da Fila, "+N" pela atenção, tempo sempre âmbar,
// prazo duro na frente e a previsão "próximo pronto em ~N min". Travas das classes
// de divergência que podem voltar (G01, G02, G03, G10, G11).
import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

import { timerChip } from "../app/presentation/board";
import {
  kitchenDetail,
  QUEUE_FOCUS,
  queueItems,
  queueScopeCounts,
  queueToneClass,
  restLine,
  type QueueTone,
} from "../app/presentation/queue";
import type { OrderCardProjection } from "../app/types/orders";

const NOW = Date.parse("2026-10-04T22:03:00Z");
const ago = (s: number) => new Date(NOW - s * 1000).toISOString();
const ahead = (s: number) => new Date(NOW + s * 1000).toISOString();

function card(over: Partial<OrderCardProjection> = {}): OrderCardProjection {
  return {
    ref: "WEB-261004-R7K", status: "ready", status_label: "Pronto", attention: "dispatch", attention_since_iso: ago(27 * 60),
    goal_minutes: 30, goal_label: "meta 30", elapsed_seconds: 1620, created_at_iso: ago(1620), dispatched_at_iso: "",
    fulfillment_type: "delivery", fulfillment_label: "Entrega", delivery_address: "", customer_name: "João",
    actions: [], confirmation_deadline_iso: "", confirmation_action: "", ready_eta_iso: "",
    ...over,
  } as OrderCardProjection;
}

describe("G03: o tempo nunca é vermelho", () => {
  it("atraso é âmbar com intensidade; vermelho é só do bloqueio", () => {
    for (const tone of ["ok", "warning", "late"] as QueueTone[]) {
      expect(queueToneClass(tone)).not.toMatch(/destructive|red-/);
    }
    expect(queueToneClass("late")).toContain("text-warning");
    expect(queueToneClass("late")).toContain("font-bold");
    for (const tone of ["ok", "warning", "late", "muted"] as const) expect(timerChip(tone)).not.toMatch(/destructive|red-/);
  });

  it("a Fila e o cartão não pintam o relógio de vermelho", () => {
    const queueView = readFileSync(new URL("../app/components/QueueView.vue", import.meta.url), "utf8");
    expect(queueView).not.toMatch(/data-queue-time[^>]*destructive/);
    const orderCard = readFileSync(new URL("../app/components/OrderCard.vue", import.meta.url), "utf8");
    expect(orderCard).not.toMatch(/clock\.tone === 'late' \? '[^']*text-destructive/);
  });
});

describe("G05: a cópia da Fila não se corta", () => {
  it("nenhuma reticência de CSS na Fila; a linha quebra", () => {
    const queueView = readFileSync(new URL("../app/components/QueueView.vue", import.meta.url), "utf8");
    expect(queueView).not.toMatch(/\btruncate\b|line-clamp/);
  });
});

describe("G07: Fila F | Supervisão T, dois segmentos", () => {
  it("a Supervisão é a tabela densa; as colunas saem do alternador", () => {
    const page = readFileSync(new URL("../app/pages/index.vue", import.meta.url), "utf8");
    const segment = page.slice(page.indexOf("data-view-switch"), page.indexOf("</div>", page.indexOf("data-view-switch")));
    expect(segment).toContain("viewMode = 'queue'");
    expect(segment).toContain("viewMode = 'table'");
    expect(segment).not.toContain("viewMode = 'board'");
  });
});

describe("G01: os recortes Precisa de você · Todos · Atrasados", () => {
  const cards = [
    card({ ref: "A-1-LATE", attention_since_iso: ago(40 * 60) }),
    card({ ref: "A-1-OK", attention: "handoff", attention_since_iso: ago(60), goal_minutes: 10 }),
    card({ ref: "A-1-KIT", attention: "", status: "preparing", status_label: "Em preparo" }),
  ];
  it("conta cada recorte com a régua da Fila", () => {
    expect(queueScopeCounts(cards, NOW)).toEqual({ attention: 2, late: 1, all: 3 });
  });
  it("Todos inclui o que só está andando, sem gesto; Atrasados só o que passou da meta", () => {
    expect(queueItems(cards, NOW, { scope: "all" }).map((i) => i.card.ref)).toEqual(["A-1-LATE", "A-1-OK", "A-1-KIT"]);
    expect(queueItems(cards, NOW, { scope: "all" })[2]).toMatchObject({ kind: "", goalLabel: "Em preparo" });
    expect(queueItems(cards, NOW, { scope: "late" }).map((i) => i.card.ref)).toEqual(["A-1-LATE"]);
  });
});

describe("G02: densidade pela atenção", () => {
  it("4 em foco; o resto da fila e o que anda viram um número só", () => {
    expect(QUEUE_FOCUS).toBe(4);
    const lines = [
      { key: "kitchen" as const, label: "Na Cozinha", icon: "", count: 5, detail: "" },
      { key: "road" as const, label: "Na rua", icon: "", count: 2, detail: "" },
    ];
    expect(restLine(lines, 5)).toEqual({ count: 12, text: "mais 5 pedem você · em andamento: 5 na cozinha, 2 na rua" });
    expect(restLine(lines)).toEqual({ count: 7, text: "em andamento, nada pede você: 5 na cozinha, 2 na rua" });
  });
});

describe("G11: o prazo duro passa à frente", () => {
  it("o pedido que o sistema vai cancelar sozinho vem antes do atrasado", () => {
    const items = queueItems([
      card({ ref: "A-1-LATE", attention_since_iso: ago(60 * 60) }),
      card({ ref: "A-1-IFD", status: "new", attention: "confirm", attention_since_iso: ago(400), goal_minutes: 8, confirmation_action: "cancel", confirmation_deadline_iso: ahead(100) }),
      card({ ref: "A-1-AUTO", status: "new", attention: "confirm", attention_since_iso: ago(60), goal_minutes: 5, confirmation_action: "confirm", confirmation_deadline_iso: ahead(240) }),
    ], NOW);
    expect(items.map((i) => i.card.ref)).toEqual(["A-1-IFD", "A-1-LATE", "A-1-AUTO"]);
  });
});

describe("G10: próximo pronto em ~N min", () => {
  it("a previsão mais próxima; vencida, o fato do mais antigo", () => {
    expect(kitchenDetail([card({ ready_eta_iso: ahead(200) }), card({ ready_eta_iso: ahead(600) })], NOW, 900)).toBe("próximo pronto em ~4 min");
    expect(kitchenDetail([card({ ready_eta_iso: ago(30) })], NOW, 1380)).toBe("o mais antigo há 23 min · passou da previsão");
    expect(kitchenDetail([card()], NOW, 600)).toBe("o mais antigo há 10 min");
    expect(kitchenDetail([], NOW, 0)).toBe("");
  });
});
