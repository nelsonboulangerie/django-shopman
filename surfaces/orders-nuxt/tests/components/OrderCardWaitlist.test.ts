// #3177: o pedido na fila de espera mostra o estado da fila nas DUAS formas do
// cartão. O Painel de mesa usa o enxuto, e antes o selo só existia no cheio (o do
// celular): na mesa, pedido esperando o lote parecia pedido travado.
import { describe, expect, it, vi } from "vitest";
import { computed, ref } from "vue";
import { mount } from "@vue/test-utils";

import OrderCard from "../../app/components/OrderCard.vue";
import type { OrderCardProjection } from "../../app/types/orders";

vi.stubGlobal("computed", computed);
vi.stubGlobal("useNowTick", () => ref(Date.parse("2026-11-18T13:00:00Z")));

function card(over: Partial<OrderCardProjection> = {}): OrderCardProjection {
  return {
    ref: "WEB-261115-E17",
    status: "new",
    status_label: "Novo",
    channel_ref: "web",
    channel_name: "Loja online",
    channel_icon: "language",
    customer_name: "Ana",
    created_at_iso: "2026-11-15T21:00:00Z",
    clock_since_iso: "2026-11-15T21:00:00Z",
    server_now_iso: "",
    elapsed_seconds: 3 * 24 * 3600 + 4 * 3600,
    timer_class: "timer-ok",
    items_summary: "1× Pain de Campagne",
    items_count: 1,
    total_display: "R$ 18,70",
    fulfillment_label: "Retirada",
    fulfillment_type: "pickup",
    delivery_address: "",
    can_confirm: false,
    can_advance: true,
    next_status: "preparing",
    payment_method: "pix",
    payment_method_label: "Pix",
    ifood_cancellation_notice: "",
    ifood_schedule_label: "",
    ifood_remote_ahead_label: "",
    ifood_negotiations: [],
    payment_status: "pending",
    payment_pending: false,
    can_settle_delivery_cash: false,
    fiscal_status: "",
    has_customer_note: false,
    is_gift: false,
    gift_has_recipient: false,
    assigned_operator: "",
    awaiting_work_orders: [],
    confirmation_deadline_iso: "",
    confirmation_action: "",
    attention: "",
    schedule_label: "Hoje · 17h às 17h30",
    schedule_state: "today",
    kitchen_release_at_iso: "",
    kitchen_release_label: "",
    kitchen_released_at_iso: "",
    actions: [],
    waitlist_state: "fermata",
    waitlist_label: "Na fila de espera",
    ...over,
  } as OrderCardProjection;
}

const stubs = { Icon: true, NuxtLink: { template: "<a><slot /></a>" } };
const mountCard = (props: Record<string, unknown>) =>
  mount(OrderCard, { props, global: { stubs } });

describe.each([
  ["cartão enxuto (Painel de mesa)", true],
  ["cartão cheio", false],
])("OrderCard, %s: pedido na fila de espera", (_name, compact) => {
  it("esperando o lote, diz \"Na fila de espera\"", () => {
    const w = mountCard({ card: card(), compact });

    const badge = w.get("[data-waitlist-badge]");
    expect(badge.text()).toBe("Na fila de espera");
  });

  it("com o lote pronto, diz que a vez é do cliente", () => {
    const w = mountCard({
      card: card({ waitlist_state: "confirming", waitlist_label: "Aguardando o cliente confirmar" }),
      compact,
    });

    expect(w.get("[data-waitlist-badge]").text()).toBe("Aguardando o cliente confirmar");
  });

  it("fora da fila, não há selo", () => {
    const w = mountCard({ card: card({ waitlist_state: "", waitlist_label: "" }), compact });

    expect(w.find("[data-waitlist-badge]").exists()).toBe(false);
  });
});
