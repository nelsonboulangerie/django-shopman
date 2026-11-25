// DEV-2026-091 (dono, 25/11/2026): "Se um pedido ainda não pago nem pode ser Aceito,
// vale a pena mostrá-lo no gestor??? [...] quando o pagamento é de fato realizado, o
// gestor nem recebe um novo alerta."
//
// O servidor deixa sem `attention` o pedido novo que só espera o dinheiro online
// (`awaits_online_payment`). O aviso do Gestor segue o `attention`: o pedido não toca
// ao chegar sem pagamento e toca, como pedido novo, quando o pagamento cai. Antes ele
// tocava ao chegar ("blocked") e o pagamento passava em silêncio (o ref já era "visto").
import { describe, expect, it } from "vitest";

import { splitRef, treatableOrderRefs } from "../app/presentation/board";
import { awaitingPayment, queueItems, queueScopeCounts } from "../app/presentation/queue";
import { gestorAttentionDecision } from "../app/composables/useOrdersBoard";
import type { OrderCardProjection, TwoZoneQueueProjection } from "../app/types/orders";

const DAY = "2026-11-25";

function card(over: Partial<OrderCardProjection>): OrderCardProjection {
  return {
    ref: "NB-K12",
    status: "new",
    status_label: "Novo",
    attention: "",
    attention_since_iso: "",
    goal_minutes: 0,
    goal_label: "",
    actions: [],
    can_confirm: false,
    can_advance: false,
    awaits_online_payment: true,
    ...over,
  } as OrderCardProjection;
}

function queue(intake: OrderCardProjection[]): TwoZoneQueueProjection {
  return {
    intake,
    prep: [],
    expedition_pickup: [],
    expedition_delivery: [],
    expedition_delivery_transit: [],
    ifood_negotiation_orders: [],
    service_day: DAY,
    service_day_ends_at: "2026-11-26T00:00:00-03:00",
  } as unknown as TwoZoneQueueProjection;
}

const unpaid = card({});
const paid = card({ attention: "confirm", can_confirm: true, awaits_online_payment: false });

describe("pedido sem pagamento no Gestor (DEV-2026-091)", () => {
  it("o pedido que só espera o Pix não toca ao chegar", () => {
    expect([...treatableOrderRefs(queue([unpaid]))]).toEqual([]);
    expect(gestorAttentionDecision(queue([unpaid]), new Set(), "", DAY).firstUnseen).toBe("");
  });

  it("o pagamento que cai toca como pedido novo", () => {
    const before = gestorAttentionDecision(queue([unpaid]), new Set(), "", DAY);
    const after = gestorAttentionDecision(queue([paid]), new Set(), before.signature, DAY);
    expect(after.firstUnseen).toBe("NB-K12");
  });
});

describe("a faixa \"Aguardando pagamento\" (escolha do dono, 25/11/2026)", () => {
  const NOW = Date.parse("2026-11-25T13:00:00Z");
  const waiting = card({
    created_at_iso: new Date(NOW - 2 * 60_000).toISOString(),
    customer_name: "Ana",
    total_display: "R$ 48,70",
    payment_method_label: "Pix",
  });

  it("lista o pedido que só espera o Pix, com quem, quanto e há quanto tempo", () => {
    expect(awaitingPayment([waiting], NOW)).toEqual([
      { ref: "NB-K12", code: splitRef("NB-K12").code, who: "Ana · R$ 48,70", wait: "Aguardando Pix há 2 min" },
    ]);
  });

  it("o pedido da faixa não está na Fila nem no Todos, e não conta", () => {
    expect(queueItems([waiting], NOW, { scope: "all" })).toEqual([]);
    expect(queueScopeCounts([waiting], NOW)).toMatchObject({ attention: 0, all: 0 });
  });

  it("pago, ele sai da faixa e entra na Fila", () => {
    const nowPaid = { ...waiting, attention: "confirm", awaits_online_payment: false } as OrderCardProjection;
    expect(awaitingPayment([nowPaid], NOW)).toEqual([]);
    expect(queueItems([nowPaid], NOW).map((item) => item.card.ref)).toEqual(["NB-K12"]);
  });

  it("o prazo vencido devolve o pedido à Fila, com o Cancelar não pago", () => {
    const lapsed = { ...waiting, attention: "blocked", payment_lapsed: true } as OrderCardProjection;
    expect(awaitingPayment([lapsed], NOW)).toEqual([]);
    expect(queueItems([lapsed], NOW).map((item) => item.card.ref)).toEqual(["NB-K12"]);
  });
});
