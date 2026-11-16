// P2-28: o pedido mudou depois de chamar o entregador e a observação da corrida
// (o que cobrar na porta) ficou para trás. A TaOn não muda a corrida aberta: o aviso
// diz o que a corrida leva e o de agora, e o "Cancelar corrida" dele arma a MESMA
// confirmação de baixo (`CourierCancelConfirm`). Depois da coleta, só o telefone.
import { computed, ref, watch } from "vue";
import { mount } from "@vue/test-utils";
import { describe, expect, it, vi } from "vitest";
import { fixtureActions } from "../support/orderActions";
import type { CourierBlock } from "../../app/types/orders";

vi.stubGlobal("computed", computed);
vi.stubGlobal("ref", ref);
vi.stubGlobal("watch", watch);
vi.stubGlobal("useNowTick", () => ref(Date.parse("2026-10-13T19:00:00-03:00")));
const { default: Panel } = await import("../../app/components/OrderCourierPanel.vue");

const outdated = {
  sent: "Cobrar R$ 50,00 em dinheiro · troco para R$ 100,00",
  current: "Cobrar R$ 50,00 no cartão (maquininha)",
  collected: false,
};
const cancelAction = {
  ...fixtureActions({ can_confirm: true })[0]!, ref: "courier-cancel", label: "Cancelar corrida", enabled: true,
  confirmation: {
    required: true, description: "Cancelar a corrida B? A47 volta para Aguardando.", confirm_label: "Cancelar a corrida B",
    reason_question: "Por que cancelar a corrida B?", consequence: "A47 volta para Aguardando.",
    reasons: [
      { id: 12, label: "O entregador não está vindo" },
      { id: 37, label: "Está demorando demais" },
      { id: 40, label: "Não consegui falar com o entregador" },
    ],
  },
};
const courier = {
  status: "A", status_label: "Entregador a caminho da loja", active: true, can_quote: false,
  can_dispatch: false, can_cancel: true, attempts_count: 0, charge_outdated: outdated,
} as unknown as CourierBlock;
const mountPanel = (over: Partial<CourierBlock> = {}) => mount(Panel, {
  props: { courier: { ...courier, ...over }, busy: false, cancelAction }, global: { stubs: { Icon: true } },
});
const buttons = (w: ReturnType<typeof mountPanel>, label: string) =>
  w.findAll("button").filter((item) => item.text() === label);

describe("a corrida leva a cobrança antiga", () => {
  it("o aviso diz o que a corrida leva e o de agora", () => {
    const w = mountPanel();
    try {
      const aviso = w.get("[data-courier-charge-outdated]");
      expect(aviso.text()).toContain("O pedido mudou depois da chamada");
      expect(aviso.text()).toContain("Na corrida: Cobrar R$ 50,00 em dinheiro · troco para R$ 100,00.");
      expect(aviso.text()).toContain("No pedido: Cobrar R$ 50,00 no cartão (maquininha).");
    } finally { w.unmount(); }
  });

  it("o Cancelar corrida do aviso arma a confirmação de baixo, sem cancelar no primeiro toque", async () => {
    const w = mountPanel();
    try {
      expect(w.find("[data-courier-charge-cancel]").exists()).toBe(true);
      // um lugar só: o botão de baixo espera o aviso armar a confirmação
      expect(buttons(w, "Cancelar corrida")).toHaveLength(1);
      await w.get("[data-courier-charge-cancel]").trigger("click");
      expect(w.emitted("cancel")).toBeUndefined();
      expect(w.find("[data-courier-charge-cancel]").exists()).toBe(false);
      // a corrida já foi aceita: o motivo é o próprio botão
      await w.get('[data-courier-cancel-reason="37"]').trigger("click");
      expect(w.emitted("cancel")).toEqual([[37]]);
    } finally { w.unmount(); }
  });

  it("depois da coleta: o telefone, sem botão de cancelar no aviso", () => {
    const w = mountPanel({ status: "E", can_cancel: false, charge_outdated: { ...outdated, collected: true } });
    try {
      const aviso = w.get("[data-courier-charge-outdated]");
      expect(aviso.text()).toContain("O entregador já coletou: ligue para ele e passe a cobrança nova.");
      expect(w.find("[data-courier-charge-cancel]").exists()).toBe(false);
    } finally { w.unmount(); }
  });

  it("cobrança em dia, sem aviso e com o Cancelar corrida de sempre", () => {
    const w = mountPanel({ charge_outdated: null });
    try {
      expect(w.find("[data-courier-charge-outdated]").exists()).toBe(false);
      expect(buttons(w, "Cancelar corrida")).toHaveLength(1);
    } finally { w.unmount(); }
  });
});
