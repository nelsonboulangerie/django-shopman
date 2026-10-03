// UX-G3 (SUITE-UX §15: uma Saída só, no Gestor). O que a Saída da Cozinha fazia e
// o cartão do Gestor passa a fazer: progresso por estação, "Pronto de Lanches" da
// estação sem tela, "Voltar para…" no menu do pedido pronto, alvos de 48 px no
// posto de saída, e o cartão de quem só expede (sem detalhe nem "Atender").
import { describe, expect, it, vi } from "vitest";
import { computed, ref } from "vue";
import { mount } from "@vue/test-utils";

import OrderCard from "../../app/components/OrderCard.vue";
import {
  kitchenChips,
  kitchenChipView,
  kitchenRecallOptions,
  stationReadyPath,
  stationRecallPath,
} from "../../app/presentation/kitchen";
import type { KitchenProgressProjection, KitchenStationProjection } from "../../app/generated/ordersContract";
import type { OrderCardProjection } from "../../app/types/orders";

vi.stubGlobal("computed", computed);
vi.stubGlobal("useNowTick", () => ref(Date.parse("2026-10-03T15:00:00Z")));

function station(over: Partial<KitchenStationProjection> = {}): KitchenStationProjection {
  return {
    station_ref: "cafes", station_name: "Cafés", prints: false, state: "in_progress", state_label: "em preparo",
    paper_label: "", paper_failed: false, cancelled_items: 0, can_mark_ready: false, recall_ticket_pk: null,
    ...over,
  };
}

function kitchen(stations: KitchenStationProjection[], missing_label = ""): KitchenProgressProjection {
  return { order_pk: 42, stations, missing_label };
}

function card(over: Partial<OrderCardProjection> = {}): OrderCardProjection {
  return {
    ref: "WEB-20261003-A47", status: "preparing", status_label: "Em preparo", status_color: "", channel_ref: "web",
    channel_icon: "language", customer_name: "Ana", created_at_display: "14:50", created_at_iso: "", server_now_iso: "",
    elapsed_seconds: 600, timer_class: "timer-ok", items_summary: "2× Pão", items_count: 2, total_display: "R$ 15,00",
    fulfillment_icon: "storefront", fulfillment_label: "Retirada", fulfillment_type: "pickup", delivery_address: "",
    delivery_instructions: "", can_confirm: false, can_advance: false, next_status: "",
    next_action_label: "", payment_method: "cash", payment_method_label: "Dinheiro",
    ifood_cancellation_notice: "", ifood_pickup_code: "", ifood_schedule_label: "", ifood_remote_ahead_label: "",
    ifood_negotiations: [], payment_status: "captured", payment_pending: false, can_settle_delivery_cash: false,
    fiscal_status_label: "", fiscal_status: "", has_kitchen_note: false, has_customer_note: false, is_gift: false,
    gift_has_recipient: false, assigned_operator: "", awaiting_work_orders: [], confirmation_deadline_iso: "",
    confirmation_action: "", revisions: {}, actions: [], undo: null, kitchen: null,
    ...over,
  } as OrderCardProjection;
}

const stubs = { Icon: true, NuxtLink: { template: "<a data-link><slot /></a>" } };
const mountCard = (c: OrderCardProjection, props: Record<string, unknown> = {}) =>
  mount(OrderCard, { props: { card: c, ...props }, global: { stubs } });

describe("kitchen presentation", () => {
  it("estação sem tela com papel na bancada: o horário do papel e o Pronto", () => {
    const view = kitchenChipView(station({ station_ref: "lanches", station_name: "Lanches", prints: true, state: "pending", state_label: "na fila", paper_label: "impresso às 10:42", can_mark_ready: true }));
    expect(view).toMatchObject({ station: "Lanches", detail: "impresso às 10:42", tone: "waiting", canMarkReady: true });
  });

  it("papel que não saiu: alerta, sem travessão", () => {
    const view = kitchenChipView(station({ prints: true, paper_failed: true, paper_label: "não imprimiu", can_mark_ready: true }));
    expect(view.tone).toBe("alert");
    expect(view.detail).toBe("não imprimiu: avise a estação");
    expect(view.detail).not.toContain("—");
  });

  it("estação de tela não oferece Pronto (dá baixa sozinha)", () => {
    expect(kitchenChipView(station({ can_mark_ready: true })).canMarkReady).toBe(false);
  });

  it("itens cancelados por extenso", () => {
    expect(kitchenChipView(station({ cancelled_items: 2 })).cancelledNote).toBe("2 itens cancelados");
  });

  it("todas prontas: sem chips (a coluna já diz), e o recall vai para o menu", () => {
    const done = kitchen([station({ state: "done", state_label: "pronto", recall_ticket_pk: 7 })]);
    expect(kitchenChips(done)).toEqual([]);
    expect(kitchenRecallOptions(done)).toEqual([{ ticketPk: 7, stationRef: "cafes", label: "Voltar para Cafés" }]);
  });

  it("os endpoints são os da Saída da Cozinha (nenhuma regra nova)", () => {
    expect(stationReadyPath(42, "lanches")).toBe("/api/v1/backstage/kds/expedition/42/printed-stations/lanches/done/");
    expect(stationRecallPath(7)).toBe("/api/v1/backstage/kds/tickets/7/recall/");
  });
});

describe("OrderCard: a Cozinha no cartão", () => {
  it("Preparo: diz quem falta e dá o Pronto da estação sem tela", async () => {
    const wrapper = mountCard(card({
      kitchen: kitchen([
        station({ station_ref: "lanches", station_name: "Lanches", prints: true, state: "pending", state_label: "na fila", can_mark_ready: true }),
        station(),
      ], "Faltam Cafés e Lanches"),
    }));
    expect(wrapper.get("[data-kitchen-missing]").text()).toBe("Faltam Cafés e Lanches");
    expect(wrapper.findAll("[data-kitchen-station]")).toHaveLength(2);
    const ready = wrapper.get("[data-kitchen-ready]");
    expect(ready.text()).toBe("Pronto de Lanches");
    await ready.trigger("click");
    expect(wrapper.emitted("station-ready")).toEqual([["lanches"]]);
  });

  it("pedido pronto: o Voltar para… mora no menu do pedido", async () => {
    const wrapper = mountCard(card({
      status: "ready",
      kitchen: kitchen([station({ state: "done", state_label: "pronto", recall_ticket_pk: 7 })]),
    }));
    expect(wrapper.find("[data-kitchen]").exists()).toBe(false);
    expect(wrapper.find("[data-card-recall]").exists()).toBe(false);
    await wrapper.get("[data-card-menu]").trigger("click");
    const recall = wrapper.get("[data-card-recall]");
    expect(recall.text()).toBe("Voltar para Cafés");
    await recall.trigger("click");
    expect(wrapper.emitted("station-recall")).toEqual([[7]]);
  });

  it("sem Cozinha no pedido: nada de bloco nem menu", () => {
    const wrapper = mountCard(card());
    expect(wrapper.find("[data-kitchen]").exists()).toBe(false);
    expect(wrapper.find("[data-card-menu]").exists()).toBe(false);
  });

  it("posto de saída: alvos de 48 px", () => {
    const wrapper = mountCard(card({ kitchen: kitchen([station({ station_ref: "lanches", station_name: "Lanches", prints: true, can_mark_ready: true })], "Falta Lanches") }), { touch: true });
    expect(wrapper.get("[data-kitchen-ready]").classes()).toContain("min-h-action");
    expect(wrapper.get("[data-link]").classes()).toContain("min-h-action");
  });

  it("quem só expede: o código não abre o detalhe e o Atender some", () => {
    const wrapper = mountCard(card(), { canOpen: false });
    expect(wrapper.find("[data-link]").exists()).toBe(false);
    expect(wrapper.get("[data-card-code]").text()).toContain("A47");
    expect(wrapper.find('[aria-label="Atender este pedido"]').exists()).toBe(false);
  });
});
