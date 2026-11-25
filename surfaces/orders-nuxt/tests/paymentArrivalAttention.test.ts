// DEV-2026-091 (dono, 25/11/2026): "Se um pedido ainda não pago nem pode ser Aceito,
// vale a pena mostrá-lo no gestor??? [...] quando o pagamento é de fato realizado, o
// gestor nem recebe um novo alerta."
//
// O servidor deixa sem `attention` o pedido novo que só espera o dinheiro online
// (`awaits_online_payment`). O aviso do Gestor segue o `attention`: o pedido não toca
// ao chegar sem pagamento e toca, como pedido novo, quando o pagamento cai. Antes ele
// tocava ao chegar ("blocked") e o pagamento passava em silêncio (o ref já era "visto").
import { describe, expect, it } from "vitest";

import { treatableOrderRefs } from "../app/presentation/board";
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
