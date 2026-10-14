// Lembrete TEMPORÁRIO de chamar o entregador (WP-ENTREGADOR-CHAMADA-ANTECIPADA).
// O servidor projeta `due_at_iso`; a tela mostra o aviso quando o relógio passa dele,
// na cor do aviso (warning), com "Chamar entregador" (que pergunta antes) e "Dispensar".
import { computed, ref, watch } from "vue";
import { mount } from "@vue/test-utils";
import { describe, expect, it, vi } from "vitest";
import { fixtureActions } from "../support/orderActions";
import type { CourierBlock, OrderCardProjection } from "../../app/types/orders";
import {
  COURIER_CALL_HASH,
  courierReminderLine,
  type CourierReminder,
} from "../../app/presentation/courier";

const nowMs = ref(0);
vi.stubGlobal("computed", computed);
vi.stubGlobal("ref", ref);
vi.stubGlobal("watch", watch);
vi.stubGlobal("useNowTick", () => nowMs);
const { default: Panel } = await import("../../app/components/OrderCourierPanel.vue");
const { default: OrderCard } = await import("../../app/components/OrderCard.vue");

const SINCE = Date.parse("2026-10-13T19:00:00-03:00");
const reminder: CourierReminder = {
  since_iso: "2026-10-13T19:00:00-03:00",
  due_at_iso: "2026-10-13T19:10:00-03:00",
  since_basis: "kds",
  short_ref: "0042",
};
const minutes = (m: number) => SINCE + m * 60_000;

describe("courierReminderLine", () => {
  it("cala antes da hora e fala depois, com os minutos do preparo andando", () => {
    expect(courierReminderLine(reminder, minutes(9))).toBeNull();
    expect(courierReminderLine(reminder, minutes(10))).toBe(
      "Pedido 0042 em preparo há 10 min. Já dá para chamar o entregador?",
    );
    expect(courierReminderLine(reminder, minutes(13.5))).toContain("há 13 min.");
  });
  it("sem lembrete ou com hora ilegível, nada", () => {
    expect(courierReminderLine(null, minutes(30))).toBeNull();
    expect(courierReminderLine({ ...reminder, due_at_iso: "" }, minutes(30))).toBeNull();
  });
  it("a frase não usa travessão", () => {
    expect(courierReminderLine(reminder, minutes(12))).not.toMatch(/[—–]/);
  });
});

describe("o aviso no painel do entregador", () => {
  const question = "Chamar um entregador da TaOn para o pedido 0042? A corrida é cobrada da casa.";
  const dispatchAction = { ...fixtureActions({ can_confirm: true })[0]!, ref: "courier-dispatch", enabled: true,
    confirmation: { required: true, description: question } };
  const courier = { status: "", can_quote: false, can_dispatch: true, can_cancel: false, attempts_count: 0,
    reminder } as CourierBlock;
  const mountPanel = (props: Record<string, unknown> = {}) => mount(Panel, {
    props: { courier, busy: false, dispatchAction, ...props }, global: { stubs: { Icon: true } },
  });
  const button = (w: ReturnType<typeof mountPanel>, label: string) =>
    w.findAll("button").find((item) => item.text() === label);

  it("antes da hora: só o botão de sempre", () => {
    nowMs.value = minutes(5);
    const w = mountPanel();
    try {
      expect(w.find("[data-courier-reminder]").exists()).toBe(false);
      expect(button(w, "Chamar entregador")).toBeTruthy();
    } finally { w.unmount(); }
  });

  it("na hora: o aviso leva o Chamar (que arma a mesma confirmação) e o Dispensar, sem botão repetido", async () => {
    nowMs.value = minutes(11);
    const w = mountPanel();
    try {
      const aviso = w.get("[data-courier-reminder]");
      expect(aviso.text()).toContain("Pedido 0042 em preparo há 11 min. Já dá para chamar o entregador?");
      expect(w.findAll("button").filter((item) => item.text() === "Chamar entregador")).toHaveLength(1);
      await button(w, "Chamar entregador")!.trigger("click");
      expect(w.emitted("dispatch")).toBeUndefined();
      expect(w.get('[data-testid="courier-dispatch-question"]').text()).toBe(question);
      expect(button(w, "Chamar entregador")).toBeUndefined();
      await button(w, "Confirmar chamada")!.trigger("click");
      expect(w.emitted("dispatch")).toHaveLength(1);
      await button(w, "Dispensar")!.trigger("click");
      expect(w.emitted("dismissReminder")).toHaveLength(1);
    } finally { w.unmount(); }
  });

  it("vindo do cartão (#courier-call), abre com a pergunta já armada", () => {
    nowMs.value = minutes(11);
    const w = mountPanel({ armDispatch: true });
    try {
      expect(w.get('[data-testid="courier-dispatch-question"]').text()).toBe(question);
      expect(button(w, "Confirmar chamada")).toBeTruthy();
    } finally { w.unmount(); }
  });

  it("sem poder chamar, sem aviso", () => {
    nowMs.value = minutes(30);
    const w = mountPanel({ courier: { ...courier, can_dispatch: false } });
    try {
      expect(w.find("[data-courier-reminder]").exists()).toBe(false);
    } finally { w.unmount(); }
  });
});

describe("o aviso no cartão do quadro", () => {
  function card(over: Partial<OrderCardProjection> = {}): OrderCardProjection {
    return {
      ref: "NB-261013-0042", status: "preparing", status_label: "Em preparo", status_color: "",
      channel_ref: "web", channel_icon: "language", customer_name: "Ana", created_at_display: "19:00",
      created_at_iso: "", server_now_iso: "", elapsed_seconds: 600, timer_class: "timer-ok",
      items_summary: "2× Pão", items_count: 2, total_display: "R$ 15,00", fulfillment_icon: "local_shipping",
      fulfillment_label: "Entrega", fulfillment_type: "delivery", delivery_address: "Rua das Flores, 123",
      delivery_instructions: "", can_confirm: false, can_advance: false, next_status: "ready",
      next_action_label: "", payment_method: "pix", payment_method_label: "PIX",
      ifood_cancellation_notice: "", ifood_pickup_code: "", ifood_schedule_label: "", ifood_remote_ahead_label: "",
      ifood_negotiations: [], payment_status: "captured", payment_pending: false, can_settle_delivery_cash: false,
      fiscal_status_label: "", fiscal_status: "", has_kitchen_note: false, has_customer_note: false, is_gift: false,
      gift_has_recipient: false, assigned_operator: "", awaiting_work_orders: [], confirmation_deadline_iso: "",
      confirmation_action: "confirm", revisions: {}, actions: [], courier_reminder: reminder, ...over,
    } as OrderCardProjection;
  }
  const stubs = { Icon: true, NuxtLink: { template: "<a><slot /></a>" } };

  it("pílula amarela na hora; o Chamar abre o pedido com a pergunta e o Dispensar vai ao quadro", async () => {
    nowMs.value = minutes(12);
    const w = mount(OrderCard, { props: { card: card() }, global: { stubs } });
    try {
      const pill = w.get('[data-card-notice="courier-reminder"]');
      expect(pill.text()).toBe("Chamar entregador?");
      await pill.trigger("click");
      const aviso = w.get("[data-courier-reminder]");
      expect(aviso.text()).toContain("Pedido 0042 em preparo há 12 min. Já dá para chamar o entregador?");
      expect(w.get("[data-courier-reminder-call]").attributes("to")).toBe(`/NB-261013-0042${COURIER_CALL_HASH}`);
      await w.get("[data-courier-reminder-dismiss]").trigger("click");
      expect(w.emitted("action")).toEqual([["dismiss_courier_reminder"]]);
    } finally { w.unmount(); }
  });

  it("antes da hora, ou sem lembrete, nenhuma pílula", () => {
    nowMs.value = minutes(8);
    const early = mount(OrderCard, { props: { card: card() }, global: { stubs } });
    nowMs.value = minutes(20);
    const none = mount(OrderCard, { props: { card: card({ courier_reminder: null }) }, global: { stubs } });
    try {
      expect(early.find('[data-card-notice="courier-reminder"]').exists()).toBe(false);
      expect(none.find('[data-card-notice="courier-reminder"]').exists()).toBe(false);
    } finally { early.unmount(); none.unmount(); }
  });
});
