// P1-4: cartão da loja online autorizado e ninguém aceita. A reserva vence no Stripe
// (7 dias) e o dinheiro some do pedido. O cartão do quadro avisa com o prazo e dá os
// dois gestos que resolvem (Aceitar, Recusar), na cor do aviso (D8).
import { describe, expect, it, vi } from "vitest";
import { computed, ref } from "vue";
import { mount } from "@vue/test-utils";

import OrderCard from "../../app/components/OrderCard.vue";
import {
  cardAuthorizationNotice,
  cardDeadlineLabel,
} from "../../app/presentation/board";
import type { OrderCardProjection } from "../../app/types/orders";
import { fixtureActions } from "../support/orderActions";

const NOW = Date.parse("2026-10-13T18:00:00Z");
const nowMs = ref(NOW);
vi.stubGlobal("computed", computed);
vi.stubGlobal("useNowTick", () => nowMs);

const DAY = 24 * 60 * 60_000;
const iso = (ms: number) => new Date(ms).toISOString();

function card(over: Partial<OrderCardProjection> = {}): OrderCardProjection {
  return {
    ref: "WEB-20261013-0042",
    status: "new",
    status_label: "Novo",
    status_color: "",
    channel_ref: "web",
    channel_icon: "language",
    customer_name: "Ana",
    created_at_display: "15:00",
    created_at_iso: "",
    server_now_iso: "",
    elapsed_seconds: 30,
    timer_class: "timer-ok",
    items_summary: "2× Pão",
    items_count: 2,
    total_display: "R$ 15,00",
    fulfillment_icon: "storefront",
    fulfillment_label: "Retirada",
    fulfillment_type: "pickup",
    payment_method: "card",
    payment_method_label: "Cartão",
    payment_status: "authorized",
    payment_tone: "warning",
    can_confirm: true,
    confirmation_deadline_iso: "",
    confirmation_action: "",
    card_authorization_expires_iso: "",
    ifood_negotiations: [],
    awaiting_work_orders: [],
    revisions: {},
    actions: fixtureActions({ can_confirm: true }),
    undo: null,
    kitchen: null,
    ...over,
  } as OrderCardProjection;
}

const stubs = { Icon: true, NuxtLink: { template: "<a><slot /></a>" } };
const mountCard = (c: OrderCardProjection) =>
  mount(OrderCard, { props: { card: c }, global: { stubs } });

describe("cardAuthorizationNotice", () => {
  it("com folga: aviso amarelo com o prazo por extenso e a data", () => {
    const notice = cardAuthorizationNotice(iso(NOW + 6 * DAY + 3600_000), NOW);
    expect(notice).toMatchObject({
      tone: "warning",
      label: "Cartão vence em 6 dias",
      title: "A autorização do cartão vence em 6 dias",
      expired: false,
    });
    expect(notice!.description).toContain("Até 19/10 às 16h00");
    expect(notice!.description).toContain("Aceite para cobrar ou recuse");
    expect(notice!.description).not.toMatch(/—|–/);
  });

  it("nas últimas 24 h: vermelho, em horas", () => {
    const notice = cardAuthorizationNotice(
      iso(NOW + 5 * 3600_000 + 60_000),
      NOW,
    );
    expect(notice).toMatchObject({
      tone: "error",
      label: "Cartão vence em 5 horas",
    });
  });

  it("vencida: diz que nada foi cobrado, sem gesto de aceitar", () => {
    const notice = cardAuthorizationNotice(iso(NOW - 60_000), NOW);
    expect(notice).toMatchObject({
      tone: "error",
      expired: true,
      label: "Cartão venceu",
    });
    expect(notice!.description).toContain("Nada foi cobrado");
  });

  it("sem autorização de pé: nada", () => {
    expect(cardAuthorizationNotice("", NOW)).toBeNull();
    expect(cardAuthorizationNotice(undefined, NOW)).toBeNull();
  });

  it("a data sai no fuso da loja", () => {
    expect(cardDeadlineLabel("2026-10-20T17:25:00Z")).toBe("20/10 às 14h25");
  });
});

describe("OrderCard: cartão autorizado esperando aceite", () => {
  it("pílula com o prazo; o aviso abre com Aceitar e Recusar na cor dele", async () => {
    const w = mountCard(
      card({ card_authorization_expires_iso: iso(NOW + 6 * DAY + 3600_000) }),
    );
    const pill = w.get('[data-card-notice="card-authorization"]');
    expect(pill.text()).toBe("Cartão vence em 6 dias");
    await pill.trigger("click");

    const accept = w.get("[data-card-authorization-accept]");
    const reject = w.get("[data-card-authorization-reject]");
    expect(accept.text()).toBe("Aceitar");
    expect(reject.text()).toBe("Recusar");

    await accept.trigger("click");
    await reject.trigger("click");
    expect(w.emitted("action")).toEqual([["confirm"], ["reject"]]);
  });

  it("sem autorização (Pix, pago, aceito): nenhum aviso de cartão", () => {
    const w = mountCard(card());
    expect(w.find('[data-card-notice="card-authorization"]').exists()).toBe(
      false,
    );
  });
});
