// WP-G02 (EXCELENCIA-GESTOR P1-02 a P1-05): a hora da Cozinha no Gestor.
//
// A encomenda do dia caía no fluxo à meia-noite com "Iniciar preparo" em primeiro plano,
// tocava o aviso às 00:00 e mostrava "há 3d 4h" (o tempo desde a compra). O servidor
// publica a hora em que ela chega à Cozinha; aqui se prende o que a tela faz com isso.
import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

import {
  attentionKeyRef,
  cardClock,
  kitchenWait,
  newlyTreatableOrderRefs,
  treatableAttentionKeys,
  treatableOrderRefs,
} from "../app/presentation/board";
import {
  clockSince,
  inProgress,
  liveAge,
  queueItems,
  workingOrders,
} from "../app/presentation/queue";
import {
  gestorAttentionDecision,
  gestorAttentionStorageKey,
  gestorSeenKeys,
  previousServiceDay,
} from "../app/composables/useOrdersBoard";
import type {
  OrderCardProjection,
  TwoZoneQueueProjection,
} from "../app/types/orders";

const NOW = Date.parse("2026-11-18T13:00:00Z"); // 10h em São Paulo
const ago = (s: number) => new Date(NOW - s * 1000).toISOString();
const THREE_DAYS = 3 * 24 * 3600 + 4 * 3600;

function card(over: Partial<OrderCardProjection> = {}): OrderCardProjection {
  return {
    ref: "WEB-261115-E17",
    status: "accepted",
    status_label: "Aceito",
    attention: "",
    attention_since_iso: "",
    goal_minutes: 0,
    goal_label: "",
    elapsed_seconds: THREE_DAYS,
    created_at_iso: ago(THREE_DAYS),
    clock_since_iso: ago(THREE_DAYS),
    kitchen_release_at_iso: "",
    kitchen_release_label: "",
    kitchen_released_at_iso: "",
    dispatched_at_iso: "",
    ready_at_iso: "",
    ready_eta_iso: "",
    timer_class: "timer-ok",
    fulfillment_type: "pickup",
    fulfillment_label: "Retirada",
    customer_name: "Ana",
    actions: [],
    can_confirm: false,
    can_advance: true,
    can_settle_delivery_cash: false,
    equipment_back_pending: false,
    confirmation_deadline_iso: "",
    confirmation_action: "",
    schedule_label: "Hoje · 17h às 17h30",
    schedule_state: "today",
    ...over,
  } as OrderCardProjection;
}

/** A encomenda das 17h, lida de manhã: ainda espera a hora da Cozinha. */
const waiting = (over: Partial<OrderCardProjection> = {}) =>
  card({
    kitchen_release_at_iso: "2026-11-18T16:15:00-03:00",
    kitchen_release_label: "Vai para a Cozinha às 16h15",
    ...over,
  });

/** A mesma encomenda, cinco minutos depois de chegar à Cozinha. */
const arrived = (over: Partial<OrderCardProjection> = {}) =>
  card({
    attention: "start",
    attention_since_iso: ago(5 * 60),
    goal_minutes: 30,
    goal_label: "combinado para as 17h",
    kitchen_released_at_iso: ago(5 * 60),
    clock_since_iso: ago(5 * 60),
    elapsed_seconds: 5 * 60,
    ...over,
  });

function queue(prep: OrderCardProjection[]): TwoZoneQueueProjection {
  return {
    intake: [],
    preparing_count: prep.length,
    prep,
    expedition_pickup: [],
    expedition_delivery: [],
    expedition_delivery_transit: [],
    expedition_delivery_count: 0,
    expedition_count: 0,
    total_count: prep.length,
    service_day: "2026-11-18",
    service_day_ends_at: "2026-11-19T00:00:00-03:00",
    preorders: [],
    preorders_count: 0,
    ifood_negotiation_orders: [],
  } as unknown as TwoZoneQueueProjection;
}

describe("antes da hora: o cartão diz quando, e não pede ninguém", () => {
  it("a frase do servidor vira o selo da espera", () => {
    expect(kitchenWait(waiting())).toEqual({
      label: "Vai para a Cozinha às 16h15",
      icon: "i-lucide-chef-hat",
    });
    expect(kitchenWait(card())).toBeNull();
  });

  it("o relógio do cartão fica mudo: não há tempo a contar", () => {
    expect(cardClock(waiting(), NOW)).toEqual({
      text: "",
      tone: "neutral",
      countdown: false,
    });
  });

  it("na Fila e na Tabela, a frase ocupa o lugar do tempo, sem âmbar", () => {
    const [item] = queueItems([waiting()], NOW, { scope: "all" });
    expect(item!.waits).toBe("Vai para a Cozinha às 16h15");
    expect(item!.tone).toBe("neutral");
    expect(item!.urgency).toBe(0);
    expect(liveAge(waiting(), NOW)).toEqual({
      label: "Vai para a Cozinha às 16h15",
      tone: "neutral",
    });
  });

  it("quem espera não entra em \"Precisa de você\"", () => {
    expect(queueItems([waiting()], NOW)).toEqual([]);
  });

  it("não é trabalho do turno: o aviso não toca à meia-noite", () => {
    expect([...treatableOrderRefs(queue([waiting()]))]).toEqual([]);
    expect(
      gestorAttentionDecision(queue([waiting()]), new Set(), "", "2026-11-18")
        .firstUnseen,
    ).toBe("");
  });
});

describe("depois que chega: o relógio conta da chegada à Cozinha", () => {
  it("a Fila conta cinco minutos, não os três dias desde a compra", () => {
    const [item] = queueItems([arrived()], NOW);
    expect(item!.timeLabel).toBe("5 min");
    expect(item!.goalLabel).toBe("combinado para as 17h");
    expect(item!.waits).toBe("");
  });

  it("o cartão diz \"há 5 min\"", () => {
    expect(cardClock(arrived(), NOW).text).toBe("há 5 min");
  });

  it("\"Na Cozinha: o mais antigo há\" lê a chegada, não a compra", () => {
    const cooking = card({
      status: "preparing",
      clock_since_iso: ago(12 * 60),
      kitchen_released_at_iso: ago(12 * 60),
    });
    expect(clockSince(cooking)).toBe(ago(12 * 60));
    const line = inProgress([cooking], NOW).find((l) => l.key === "kitchen")!;
    expect(line.detail).toBe("o mais antigo há 12 min");
    expect(workingOrders([cooking], NOW).kitchen[0]!.ageLabel).toBe("12 min");
  });

  it("sem o campo novo, vale a criação do pedido", () => {
    expect(
      clockSince({ clock_since_iso: "", created_at_iso: "2026-11-18T12:00:00Z" }),
    ).toBe("2026-11-18T12:00:00Z");
  });
});

describe("o aviso toca uma vez, na chegada à Cozinha", () => {
  it("a chegada é um fato novo do mesmo pedido", () => {
    expect(newlyTreatableOrderRefs(queue([waiting()]), queue([arrived()]))).toEqual([
      "WEB-261115-E17",
    ]);
    const keys = treatableAttentionKeys(queue([arrived()]));
    expect([...keys.keys()]).toEqual(["WEB-261115-E17@cozinha"]);
    expect(attentionKeyRef("WEB-261115-E17@cozinha")).toBe("WEB-261115-E17");
    expect(attentionKeyRef("WEB-261115-E17")).toBe("WEB-261115-E17");
  });

  it("quem viu o aceite ontem ainda ouve a chegada de hoje", () => {
    const seenYesterday = new Set(["WEB-261115-E17"]);
    const decision = gestorAttentionDecision(
      queue([arrived()]),
      seenYesterday,
      "",
      "2026-11-18",
    );
    expect(decision.firstUnseen).toBe("WEB-261115-E17@cozinha");
    expect(decision.shouldStop).toBe(false);
  });

  it("vista a chegada, não repete", () => {
    const decision = gestorAttentionDecision(
      queue([arrived()]),
      new Set(["WEB-261115-E17@cozinha"]),
      "",
      "2026-11-18",
    );
    expect(decision.firstUnseen).toBe("");
    expect(decision.shouldStop).toBe(true);
  });

  it("o pedido de agora continua com uma chave só, o próprio ref", () => {
    const now = card({ ref: "WEB-261118-A01", attention: "start" });
    expect([...treatableAttentionKeys(queue([now])).keys()]).toEqual([
      "WEB-261118-A01",
    ]);
  });
});

describe("a virada do dia não zera os vistos de quem já estava na tela", () => {
  const store = (entries: Record<string, string[]>) => (key: string) =>
    key in entries ? JSON.stringify(entries[key]) : null;

  it("o dia anterior sai da data, sem fuso do tablet", () => {
    expect(previousServiceDay("2026-11-18")).toBe("2026-11-17");
    expect(previousServiceDay("2026-03-01")).toBe("2026-02-28");
    expect(previousServiceDay("2027-01-01")).toBe("2026-12-31");
    expect(previousServiceDay("ontem")).toBe("");
  });

  it("os vistos de ontem valem hoje", () => {
    const read = store({
      [gestorAttentionStorageKey("2026-11-17")]: ["WEB-ONTEM"],
      [gestorAttentionStorageKey("2026-11-18")]: ["WEB-HOJE"],
    });
    expect([...gestorSeenKeys(read, "2026-11-18")].sort()).toEqual([
      "WEB-HOJE",
      "WEB-ONTEM",
    ]);
  });

  it("o pedido aberto de ontem, já visto, não toca de novo às 00:00", () => {
    const open = card({ ref: "WEB-ONTEM", status: "ready", attention: "handoff" });
    const read = store({ [gestorAttentionStorageKey("2026-11-17")]: ["WEB-ONTEM"] });
    const decision = gestorAttentionDecision(
      queue([open]),
      gestorSeenKeys(read, "2026-11-18"),
      "2026-11-17:WEB-ONTEM",
      "2026-11-18",
    );
    expect(decision.firstUnseen).toBe("");
    expect(decision.shouldStop).toBe(true);
  });

  it("memória ilegível de um dia não apaga a do outro", () => {
    const read = (key: string) =>
      key === gestorAttentionStorageKey("2026-11-17") ? "{quebrado" : '["WEB-HOJE"]';
    expect([...gestorSeenKeys(read, "2026-11-18")]).toEqual(["WEB-HOJE"]);
  });
});

describe("Fila: a espera mora com o combinado, não no lugar do tempo", () => {
  const view = readFileSync(
    new URL("../app/components/QueueView.vue", import.meta.url),
    "utf8",
  );

  it("o selo do tempo some para quem espera a hora da Cozinha", () => {
    const time = view.slice(view.lastIndexOf("<NuxtBadge", view.indexOf("data-queue-time")), view.indexOf("data-queue-time"));
    expect(time).toContain('v-if="!item.waits"');
  });

  it("a frase aparece na coluna do pedido, quebrando a linha", () => {
    const wait = view.slice(view.lastIndexOf("<NuxtBadge", view.indexOf("data-queue-kitchen-wait")), view.indexOf("data-queue-kitchen-wait") + 200);
    expect(wait).toContain('v-if="item.waits"');
    expect(wait).toContain("whitespace-normal");
  });
});
