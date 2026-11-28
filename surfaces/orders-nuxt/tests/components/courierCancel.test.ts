// Cancelar a corrida da TaOn (revisão das Entregas, F1a): um toque NUNCA cancela.
// O primeiro arma a confirmação; antes do aceite o segundo confirma, e depois do
// aceite o motivo é o próprio botão (o `reason_id` que a central recebe). O pedido
// de cancelamento e a recusa da TaOn aparecem na tela, no Painel do pedido e no
// detalhe da corrida da seção Entregas.
import { computed, ref, watch } from "vue";
import { mount } from "@vue/test-utils";
import { describe, expect, it, vi } from "vitest";
import { fixtureActions } from "../support/orderActions";
import type { CourierBlock } from "../../app/types/orders";
import type { Action, DeliveryRideProjection } from "../../app/generated/ordersContract";

vi.stubGlobal("computed", computed);
vi.stubGlobal("ref", ref);
vi.stubGlobal("watch", watch);
vi.stubGlobal("useNowTick", () => ref(Date.parse("2026-11-16T14:20:00-03:00")));
const { default: Panel } = await import("../../app/components/OrderCourierPanel.vue");
const { default: Detail } = await import("../../app/components/CourierRideDetail.vue");

const REASONS = [
  { id: 12, label: "O entregador não está vindo" },
  { id: 37, label: "Está demorando demais" },
  { id: 40, label: "Não consegui falar com o entregador" },
];
function cancelAction(accepted: boolean, over: Partial<Action> = {}): Action {
  return {
    ...fixtureActions({ can_confirm: true })[0]!,
    ref: "courier-cancel",
    label: "Cancelar corrida",
    enabled: true,
    confirmation: {
      required: true,
      description: "Cancelar a corrida B? A05 e C12 voltam para Aguardando.",
      confirm_label: "Cancelar a corrida B",
      ...(accepted
        ? { reason_question: "Por que cancelar a corrida B?", consequence: "A05 e C12 voltam para Aguardando.", reasons: REASONS }
        : {}),
    },
    ...over,
  };
}

// ── Painel do pedido ────────────────────────────────────────────────────────
const courier = {
  status: "D", ride_state: "searching", service_name: "TaOn", status_label: "Procurando entregador", active: true, can_quote: false,
  can_dispatch: false, can_cancel: true, attempts_count: 0, charge_outdated: null, error: null,
} as unknown as CourierBlock;
const mountPanel = (over: Partial<CourierBlock> = {}, action: Action | undefined = cancelAction(false)) =>
  mount(Panel, {
    props: { orderRef: "NB-261116-A05", courier: { ...courier, ...over }, busy: false, cancelAction: action },
    global: { stubs: { Icon: true } },
  });

describe("Painel do pedido: cancelar a corrida", () => {
  it("antes do aceite: o primeiro toque arma, o segundo confirma, sem motivo", async () => {
    const w = mountPanel();
    try {
      expect(w.find("[data-courier-cancel-confirm]").exists()).toBe(false);
      await w.get("[data-courier-cancel]").trigger("click");
      expect(w.emitted("cancel")).toBeUndefined();
      const confirm = w.get("[data-courier-cancel-confirm]");
      expect(confirm.text()).toContain("Cancelar a corrida B? A05 e C12 voltam para Aguardando.");
      expect(w.find("[data-courier-cancel-reason]").exists()).toBe(false);
      expect(w.get("[data-courier-cancel-go]").text()).toBe("Cancelar a corrida B");
      await w.get("[data-courier-cancel-go]").trigger("click");
      expect(w.emitted("cancel")).toEqual([[undefined]]);
      expect(w.find("[data-courier-cancel-confirm]").exists()).toBe(false);
    } finally { w.unmount(); }
  });

  it("depois do aceite: a confirmação traz os três motivos, e cada botão já é o motivo", async () => {
    const w = mountPanel({ status: "A", ride_state: "assigned", status_label: "Entregador a caminho da loja" }, cancelAction(true));
    try {
      await w.get("[data-courier-cancel]").trigger("click");
      expect(w.emitted("cancel")).toBeUndefined();
      const confirm = w.get("[data-courier-cancel-confirm]");
      expect(confirm.text()).toContain("Por que cancelar a corrida B?");
      expect(confirm.text()).toContain("A05 e C12 voltam para Aguardando.");
      expect(w.findAll("[data-courier-cancel-reason]").map((button) => button.text())).toEqual(
        REASONS.map((reason) => reason.label),
      );
      // sem um "confirmar" genérico: depois do aceite não se cancela sem dizer por quê
      expect(w.find("[data-courier-cancel-go]").exists()).toBe(false);
      await w.get('[data-courier-cancel-reason="40"]').trigger("click");
      expect(w.emitted("cancel")).toEqual([[40]]);
    } finally { w.unmount(); }
  });

  it("Manter a corrida desarma e nada é enviado", async () => {
    const w = mountPanel({ status: "A", ride_state: "assigned" }, cancelAction(true));
    try {
      await w.get("[data-courier-cancel]").trigger("click");
      await w.get("[data-courier-cancel-keep]").trigger("click");
      expect(w.emitted("cancel")).toBeUndefined();
      expect(w.find("[data-courier-cancel-confirm]").exists()).toBe(false);
      expect(w.find("[data-courier-cancel]").exists()).toBe(true);
    } finally { w.unmount(); }
  });

  it("a corrida mudou com a confirmação aberta (aceite): desarma, a pergunta era outra", async () => {
    const w = mountPanel();
    try {
      await w.get("[data-courier-cancel]").trigger("click");
      expect(w.find("[data-courier-cancel-confirm]").exists()).toBe(true);
      await w.setProps({
        cancelAction: cancelAction(true, { payload_schema: { expected_actor_id: 1, base_revision: "depois-do-aceite" } }),
      });
      expect(w.find("[data-courier-cancel-confirm]").exists()).toBe(false);
      expect(w.emitted("cancel")).toBeUndefined();
    } finally { w.unmount(); }
  });

  it("cancelamento pedido: a frase aparece e o botão some", () => {
    const message = "Pedido de cancelamento enviado. Esperando a TaOn confirmar.";
    const w = mountPanel({ can_cancel: false, cancel_state: { state: "pending", message, at: "2026-11-16T17:20:00Z" } });
    try {
      expect(w.get("[data-courier-cancel-state]").text()).toContain(message);
      expect(w.find("[data-courier-cancel]").exists()).toBe(false);
    } finally { w.unmount(); }
  });

  it("recusa da TaOn: aviso de erro com a letra da corrida, dispensável, e volta se o estado muda", async () => {
    const message = "A TaOn não cancelou a corrida B. Cancele pela central da TaOn.";
    const w = mountPanel({ cancel_state: { state: "failed", message, at: "2026-11-16T17:21:00Z" } });
    try {
      const notice = w.get("[data-courier-cancel-state]");
      expect(notice.text()).toContain(message);
      expect(notice.attributes("color")).toBe("error");
      // a recusa não é falha de ABRIR a corrida: o aviso de despacho não aparece
      expect(w.text()).not.toContain("Falha ao abrir a corrida");
      await notice.get('button[aria-label="Fechar"]').trigger("click");
      expect(w.find("[data-courier-cancel-state]").exists()).toBe(false);
      await w.setProps({
        courier: { ...courier, cancel_state: { state: "failed", message, at: "2026-11-16T17:25:00Z" } },
      });
      expect(w.find("[data-courier-cancel-state]").exists()).toBe(true);
    } finally { w.unmount(); }
  });
});

// ── Seção Entregas: o detalhe da corrida ────────────────────────────────────
const stop = (ref: string) => ({
  ref, code: ref.slice(-3), customer: "Ana", place: "Centro", address: "Rua das Flores, 123", latitude: null,
  longitude: null, stage: "Pronto", volumes: 1, done: false, change_out_suggested_q: 0, needs_machine: false,
  change_label: "", group_refusal: "", error: "", dispatch_action: null, dispatch_again_action: null, charge_outdated: null,
});
function ride(over: Partial<DeliveryRideProjection> = {}): DeliveryRideProjection {
  return {
    key: "776753357", number: 2, state: "searching", status_label: "Procurando entregador", service_name: "TaOn",
    stops: [stop("NB-261116-A05"), stop("NB-261116-C12")], driver: null, position: null,
    called_at: "2026-11-16T17:12:00Z", called_by: "ana", pickup_eta_at: "", arrived_pickup_at: "", picked_up_at: "",
    delivery_eta_at: "", tracking_url: "", cost_display: "", bags: 2, undeclared: [], lead_ref: "NB-261116-A05",
    back_action: null, back_lines: [], cancel_action: cancelAction(false), cancel_state: "", cancel_message: "",
    ...over,
  } as DeliveryRideProjection;
}
const mountDetail = (over: Partial<DeliveryRideProjection> = {}) =>
  mount(Detail, {
    props: { ride: ride(over), origin: null, now: Date.parse("2026-11-16T14:20:00-03:00"), busy: false },
    global: { stubs: { Icon: true, NuxtIcon: true, CourierDeliveriesMap: true } },
  });

describe("Entregas: cancelar a corrida no detalhe", () => {
  it("um toque em Cancelar corrida nunca cancela: arma a confirmação com a frase do servidor", async () => {
    const w = mountDetail();
    try {
      await w.get("[data-ride-cancel]").trigger("click");
      expect(w.emitted("cancel")).toBeUndefined();
      expect(w.get("[data-courier-cancel-confirm]").text()).toContain(
        "Cancelar a corrida B? A05 e C12 voltam para Aguardando.",
      );
      await w.get("[data-courier-cancel-go]").trigger("click");
      expect(w.emitted("cancel")).toEqual([[undefined]]);
    } finally { w.unmount(); }
  });

  it("depois do aceite o detalhe pede o motivo e manda o reason_id", async () => {
    const w = mountDetail({ state: "coming", status_label: "Entregador a caminho da loja", cancel_action: cancelAction(true) });
    try {
      await w.get("[data-ride-cancel]").trigger("click");
      expect(w.findAll("[data-courier-cancel-reason]")).toHaveLength(3);
      await w.get('[data-courier-cancel-reason="12"]').trigger("click");
      expect(w.emitted("cancel")).toEqual([[12]]);
    } finally { w.unmount(); }
  });

  it("cancelamento pendente: a frase aparece uma vez só (no aviso), e o rodapé some com o botão", () => {
    const message = "Pedido de cancelamento enviado. Esperando a TaOn confirmar.";
    const w = mountDetail({ cancel_action: null, cancel_state: "pending", cancel_message: message });
    try {
      expect(w.get("[data-ride-cancel-state]").text()).toContain(message);
      expect(w.find("[data-ride-cancel]").exists()).toBe(false);
      // O aviso do topo já diz: o rodapé não repete a mesma coisa nem fica vazio na tela.
      expect(w.find("[data-ride-footer]").exists()).toBe(false);
      expect(w.text()).not.toContain("O cancelamento já foi pedido");
      expect(w.text()).not.toContain("Ele já saiu com as sacolas");
    } finally { w.unmount(); }
  });

  it("sem botão de cancelar, o rodapé segue o estado: 'já saiu com as sacolas' só depois da coleta", () => {
    const atStore = mountDetail({ cancel_action: null, cancel_state: "", picked_up_at: "" });
    try {
      expect(atStore.get("[data-ride-footer]").text()).toContain("Para cancelar esta corrida, use a central da TaOn.");
      expect(atStore.text()).not.toContain("Ele já saiu com as sacolas");
    } finally { atStore.unmount(); }
    const onStreet = mountDetail({ cancel_action: null, cancel_state: "", picked_up_at: "2026-11-19T12:00:00-03:00" });
    try {
      expect(onStreet.get("[data-ride-footer]").text()).toContain("Ele já saiu com as sacolas");
    } finally { onStreet.unmount(); }
  });

  it("recusa da TaOn: aviso de erro, e o Cancelar corrida segue disponível", () => {
    const message = "A TaOn não cancelou a corrida B. Cancele pela central da TaOn.";
    const w = mountDetail({ cancel_state: "failed", cancel_message: message });
    try {
      const notice = w.get("[data-ride-cancel-state]");
      expect(notice.text()).toContain(message);
      expect(notice.attributes("color")).toBe("error");
      expect(w.find("[data-ride-cancel]").exists()).toBe(true);
    } finally { w.unmount(); }
  });
});
