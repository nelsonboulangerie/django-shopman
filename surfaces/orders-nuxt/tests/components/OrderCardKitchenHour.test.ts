// WP-G02: o cartão da encomenda do dia que ainda espera a hora da Cozinha.
// Diz quando chega, cala o relógio e deixa "Adiantar" em segundo plano; depois da
// chegada, volta a pedir "Iniciar preparo" e a contar o tempo.
import { describe, expect, it, vi } from "vitest";
import { computed, ref } from "vue";
import { mount } from "@vue/test-utils";

import OrderCard from "../../app/components/OrderCard.vue";
import OrderPreorderList from "../../app/components/OrderPreorderList.vue";
import type { Action } from "../../app/generated/ordersContract";
import type { OrderCardProjection } from "../../app/types/orders";

vi.stubGlobal("computed", computed);
vi.stubGlobal("useNowTick", () => ref(Date.parse("2026-11-18T13:00:00Z")));

const advance = (label: string, priority: string): Action =>
  ({
    ref: "advance", label, enabled: true, reason: "", priority, kind: "mutation", href: "",
    method: "POST", idempotency: "required", confirmation: {},
    payload_schema: { expected_actor_id: 1, base_revision: "fixture-base", target_status: "preparing" },
  }) as Action;

function card(over: Partial<OrderCardProjection> = {}): OrderCardProjection {
  return {
    ref: "WEB-261115-E17",
    status: "accepted",
    status_label: "Aceito",
    status_color: "",
    channel_ref: "web",
    channel_icon: "language",
    customer_name: "Ana",
    created_at_display: "15/11 18h",
    created_at_iso: "2026-11-15T21:00:00Z",
    clock_since_iso: "2026-11-15T21:00:00Z",
    server_now_iso: "",
    elapsed_seconds: 3 * 24 * 3600 + 4 * 3600,
    timer_class: "timer-ok",
    items_summary: "1× Pain de Campagne",
    items_count: 1,
    total_display: "R$ 18,70",
    fulfillment_icon: "storefront",
    fulfillment_label: "Retirada",
    fulfillment_type: "pickup",
    delivery_address: "",
    delivery_instructions: "",
    can_confirm: false,
    can_advance: true,
    next_status: "preparing",
    next_action_label: "Adiantar",
    payment_method: "pix",
    payment_method_label: "Pix",
    ifood_cancellation_notice: "",
    ifood_pickup_code: "",
    ifood_schedule_label: "",
    ifood_remote_ahead_label: "",
    ifood_negotiations: [],
    payment_status: "captured",
    payment_pending: false,
    can_settle_delivery_cash: false,
    fiscal_status_label: "",
    fiscal_status: "",
    has_kitchen_note: false,
    has_customer_note: false,
    is_gift: false,
    gift_has_recipient: false,
    assigned_operator: "",
    awaiting_work_orders: [],
    confirmation_deadline_iso: "",
    confirmation_action: "",
    revisions: {},
    attention: "",
    schedule_label: "Hoje · 17h às 17h30",
    schedule_state: "today",
    kitchen_release_at_iso: "2026-11-18T16:15:00-03:00",
    kitchen_release_label: "Vai para a Cozinha às 16h15",
    kitchen_released_at_iso: "",
    actions: [advance("Adiantar", "secondary")],
    ...over,
  } as OrderCardProjection;
}

const stubs = { Icon: true, NuxtLink: { template: "<a><slot /></a>" } };
const mountCard = (props: Record<string, unknown>) =>
  mount(OrderCard, { props, global: { stubs } });

describe.each([
  ["cartão enxuto (Painel de mesa)", true],
  ["cartão cheio", false],
])("OrderCard, %s: antes da hora da Cozinha", (_name, compact) => {
  it("diz quando chega, ao lado do combinado", () => {
    const w = mountCard({ card: card(), compact });

    expect(w.get("[data-card-kitchen-wait]").text()).toBe("Vai para a Cozinha às 16h15");
    expect(w.get("[data-card-promise]").text()).toBe("Hoje · 17h às 17h30");
  });

  it("não mostra o tempo desde a compra", () => {
    const w = mountCard({ card: card(), compact });

    expect(w.text()).not.toContain("há 3d");
    expect(w.text()).not.toMatch(/há \d/);
  });

  it("\"Adiantar\" existe, mas não é o botão principal", () => {
    const w = mountCard({ card: card(), compact });

    expect(w.find("[data-card-primary]").exists()).toBe(false);
    expect(w.findAll("button").some((b) => b.text() === "Adiantar")).toBe(true);
    expect(w.text()).not.toContain("Iniciar preparo");
  });
});

describe("OrderCard: o selo do cartão enxuto de quem espera", () => {
  it("diz só a situação, sem moldura de atenção", () => {
    const w = mountCard({ card: card(), compact: true });

    expect(w.get("[data-card-clock]").text()).toBe("Aceito");
    // Controle positivo no teste de quem chegou: ali a mesma leitura devolve "true".
    expect(w.get("article").attributes("data-highlight")).toBeUndefined();
  });
});

describe("OrderCard: depois que a encomenda chega à Cozinha", () => {
  const arrived = card({
    attention: "start",
    kitchen_release_at_iso: "",
    kitchen_release_label: "",
    kitchen_released_at_iso: "2026-11-18T12:55:00Z",
    clock_since_iso: "2026-11-18T12:55:00Z",
    elapsed_seconds: 5 * 60,
    next_action_label: "Iniciar preparo",
    actions: [advance("Iniciar preparo", "primary")],
  });

  it("pede \"Iniciar preparo\" e conta da chegada", () => {
    const w = mountCard({ card: arrived, compact: true });

    expect(w.find("[data-card-kitchen-wait]").exists()).toBe(false);
    expect(w.get("[data-card-primary]").text()).toBe("Iniciar preparo");
    expect(w.get("[data-card-clock]").text()).toContain("há 5 min");
    expect(w.get("article").attributes("data-highlight")).toBe("true");
  });
});

// Decisão do dono (18/11/2026): a encomenda aceita espera a hora da Cozinha na lista
// "Encomendas", abaixo do quadro, e não numa coluna do dia.
describe("Encomendas: a de hoje que espera a hora da Cozinha", () => {
  vi.stubGlobal("useRuntimeConfig", () => ({ public: { posUrl: "" } }));
  const listStubs = {
    ...stubs,
    NuxtLink: { props: ["to"], template: '<a :href="to"><slot /></a>' },
    OperatorCountChip: { props: ["count"], template: "<span>{{ count }}</span>" },
  };

  it("a linha diz quando ela vai para a Cozinha", () => {
    const w = mount(OrderPreorderList, {
      props: {
        groups: [{ date: "2026-11-18", label: "hoje", cards: [card({ commitment_date_display: "hoje" })] }],
        count: 1,
      },
      global: { stubs: listStubs },
    });

    expect(w.get("h3").text()).toBe("Hoje");
    const row = w.get('[data-preorder-row="WEB-261115-E17"]');
    expect(row.get("[data-preorder-kitchen-wait]").html()).toContain("Vai para a Cozinha às 16h15");
    expect(row.get("a").attributes("href")).toBe("/WEB-261115-E17");
    expect(row.get("[data-preorder-when]").text()).toBe("Hoje · 17h às 17h30");
  });

  it("a de outro dia não ganha a frase", () => {
    const w = mount(OrderPreorderList, {
      props: {
        groups: [{ date: "2026-11-19", label: "amanhã", cards: [card({ kitchen_release_label: "", kitchen_release_at_iso: "" })] }],
        count: 1,
      },
      global: { stubs: listStubs },
    });

    expect(w.find("[data-preorder-kitchen-wait]").exists()).toBe(false);
  });
});
