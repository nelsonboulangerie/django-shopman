// P2-28: o pedido mudou depois de chamar o entregador e a observação da corrida
// (o que cobrar na porta) ficou para trás. A TaOn não muda a corrida aberta: o aviso
// diz o que a corrida leva e o de agora, e o "Solicitar cancelamento" dele arma a
// MESMA confirmação de baixo. Depois da coleta, só o telefone.
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
const cancelAction = { ...fixtureActions({ can_confirm: true })[0]!, ref: "courier-cancel", enabled: true };
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

  it("o Solicitar cancelamento do aviso arma a confirmação de baixo, sem cancelar no primeiro toque", async () => {
    const w = mountPanel();
    try {
      expect(w.find("[data-courier-charge-cancel]").exists()).toBe(true);
      // um lugar só: o botão de baixo espera o aviso armar a confirmação
      expect(buttons(w, "Solicitar cancelamento")).toHaveLength(1);
      await w.get("[data-courier-charge-cancel]").trigger("click");
      expect(w.emitted("cancel")).toBeUndefined();
      expect(w.find("[data-courier-charge-cancel]").exists()).toBe(false);
      await buttons(w, "Confirmar solicitação?")[0]!.trigger("click");
      expect(w.emitted("cancel")).toHaveLength(1);
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

  it("cobrança em dia, sem aviso e com o Solicitar cancelamento de sempre", () => {
    const w = mountPanel({ charge_outdated: null });
    try {
      expect(w.find("[data-courier-charge-outdated]").exists()).toBe(false);
      expect(buttons(w, "Solicitar cancelamento")).toHaveLength(1);
    } finally { w.unmount(); }
  });
});
