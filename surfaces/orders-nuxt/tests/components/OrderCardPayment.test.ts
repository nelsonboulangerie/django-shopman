// O pagamento como o servidor o diz chega ao cartão (WP-G09, laudo do Gestor P2-09).
//
// "Pagamento simulado, sem dinheiro" e "Cobrança recusada" existiam no servidor
// (`payment_status_label`) e nenhuma forma do cartão os escrevia: o selo dizia só o
// meio ("Pix", "Cartão"). Quem entregava um pedido de pagamento simulado lia "Pix" em
// âmbar, sem palavra nenhuma que explicasse a cor.
import { mount } from "@vue/test-utils";
import { describe, expect, it, vi } from "vitest";
import { ref } from "vue";

import { paymentAlert, paymentLabel } from "../../app/presentation/board";
import type { OrderCardProjection } from "../../app/types/orders";

vi.stubGlobal("useNowTick", () => ref(Date.parse("2026-11-19T15:00:00Z")));

const { default: OrderCard } = await import("../../app/components/OrderCard.vue");

function card(over: Partial<OrderCardProjection> = {}): OrderCardProjection {
  return {
    ref: "WEB-261119-J40", status: "accepted", status_label: "Aceito", channel_ref: "web",
    channel_name: "Loja online", channel_icon: "language", customer_name: "Clara Teste",
    created_at_iso: "", server_now_iso: "", elapsed_seconds: 120, timer_class: "timer-ok",
    items_summary: "1x Pain de Campagne", items_count: 1, total_display: "R$ 18,70",
    fulfillment_label: "Retirada", fulfillment_type: "pickup", delivery_address: "",
    can_confirm: false, can_advance: true, next_status: "preparing",
    payment_method: "pix", payment_method_label: "Pix", payment_status: "captured",
    payment_status_label: "Pago", payment_pending: false, payment_tone: "success",
    advance_block_label: "", advance_block_reason: "", can_settle_delivery_cash: false,
    fiscal_status: "", has_customer_note: false, is_gift: false, gift_has_recipient: false,
    assigned_operator: "", awaiting_work_orders: [], actions: [], undo: null,
    ...over,
  } as OrderCardProjection;
}

const SIMULATED = {
  payment_status_label: "Pagamento simulado, sem dinheiro",
  payment_tone: "warning",
};
const CAPTURE_FAILED = {
  payment_method: "card", payment_method_label: "Cartão", payment_status: "authorized",
  payment_status_label: "Cobrança recusada", payment_tone: "danger",
};

const stubs = { Icon: true, NuxtLink: { template: "<a><slot /></a>" } };
const mountCard = (props: Record<string, unknown>) =>
  mount(OrderCard, { props, global: { stubs } });

describe("a frase do pagamento é a do servidor", () => {
  it("o meio e a situação, numa frase; sem situação, só o meio", () => {
    expect(paymentLabel(card())).toBe("Pix · Pago");
    expect(paymentLabel(card(SIMULATED))).toBe("Pix · Pagamento simulado, sem dinheiro");
    expect(paymentLabel(card(CAPTURE_FAILED))).toBe("Cartão · Cobrança recusada");
    expect(
      paymentLabel(card({ payment_method_label: "Dinheiro na entrega", payment_status_label: "" })),
    ).toBe("Dinheiro na entrega");
    expect(paymentLabel(card({ payment_method_label: "", payment_status_label: "" }))).toBe("");
  });

  it("o aviso do cartão enxuto segue o tom do servidor, e não repete a pílula do bloqueio", () => {
    expect(paymentAlert(card())).toBeNull();
    expect(paymentAlert(card(SIMULATED))).toMatchObject({
      label: "Pix · Pagamento simulado, sem dinheiro",
      color: "warning",
    });
    expect(paymentAlert(card({ ...CAPTURE_FAILED, status: "preparing" }))).toMatchObject({
      label: "Cartão · Cobrança recusada",
      color: "error",
    });
    // Quem ainda espera o pagamento já tem o fato na pílula do bloqueio.
    expect(paymentAlert(card({ ...CAPTURE_FAILED, payment_pending: true }))).toBeNull();
    expect(
      paymentAlert(card({ payment_status_label: "Aguardando pagamento", payment_tone: "warning", payment_pending: true })),
    ).toBeNull();
    // Dinheiro a receber é neutro: não é aviso.
    expect(paymentAlert(card({ payment_tone: "neutral", payment_status_label: "" }))).toBeNull();
  });
});

describe("OrderCard: o pagamento simulado e a cobrança recusada aparecem", () => {
  it("cartão inteiro (celular): o selo do pagamento escreve o meio e a situação", () => {
    expect(mountCard({ card: card() }).get("[data-card-payment]").text()).toBe("Pix · Pago");
    expect(mountCard({ card: card(SIMULATED) }).get("[data-card-payment]").text()).toBe(
      "Pix · Pagamento simulado, sem dinheiro",
    );
    expect(
      mountCard({ card: card({ ...CAPTURE_FAILED, status: "preparing" }) })
        .get("[data-card-payment]")
        .text(),
    ).toBe("Cartão · Cobrança recusada");
  });

  it("cartão enxuto (Painel de mesa): só o pagamento que pede um olhar ganha selo", () => {
    expect(
      mountCard({ card: card(), compact: true }).find("[data-card-payment-alert]").exists(),
    ).toBe(false);
    expect(
      mountCard({ card: card(SIMULATED), compact: true }).get("[data-card-payment-alert]").text(),
    ).toBe("Pix · Pagamento simulado, sem dinheiro");
    expect(
      mountCard({ card: card({ ...CAPTURE_FAILED, status: "preparing" }), compact: true })
        .get("[data-card-payment-alert]")
        .text(),
    ).toBe("Cartão · Cobrança recusada");
  });

  it("pedido sem canal: o nome do cliente sozinho, sem travessão nem ponto sobrando", () => {
    const w = mountCard({ card: card({ channel_ref: "", channel_name: "" }) });
    expect(w.get("[data-card-who]").text()).toBe("Clara Teste");
    expect(w.text()).not.toContain("—");
  });
});
