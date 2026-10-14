// O ENTREGADOR no painel do Balcão: além de chamar, "Cancelar a corrida" (antes da
// coleta) e "Entregador voltou" moram aqui, com as ações do Gestor (dono, P=1,
// 14/10/2026). A frase "No Gestor de pedidos: cancelar a corrida e registrar a
// volta..." saiu: contradizia a tela.
import { afterEach, describe, expect, it } from "vitest";
import { enableAutoUnmount } from "@vue/test-utils";
import { mountSuspended } from "@nuxt/test-utils/runtime";

import PosCourierPanel from "~/components/PosCourierPanel.vue";
import type { PreorderCourier } from "~/types/preorders";
import type { OrderDetailAction } from "../../../operator-kit/app/types/orderDetail";

enableAutoUnmount(afterEach);

function courier(overrides: Partial<PreorderCourier> = {}): PreorderCourier {
  return {
    provider: "machine", status: "P", status_label: "Procurando entregador", active: true, driver: null,
    tracking_url: "", confirmation_code: "", attempts_count: 0, error: null, can_dispatch: false,
    can_dispatch_again: false, can_cancel: false, ...overrides,
  };
}

function action(ref: string, label: string, enabled = true): OrderDetailAction {
  return {
    ref, kind: "mutation", label, enabled, reason: enabled ? "" : "Confira o estado da corrida.",
    method: "POST", idempotency: "required", confirmation: { required: true },
    payload_schema: { base_revision: `rev-${ref}`, expected_actor_id: 7 },
  } as OrderDetailAction;
}

const card = { courier_label: "Procurando entregador", courier_tone: "neutral" };

describe("PosCourierPanel: cancelar a corrida e entregador voltou", () => {
  it("antes da coleta, Cancelar a corrida pede o segundo toque e só então emite", async () => {
    const wrapper = await mountSuspended(PosCourierPanel, {
      props: { courier: courier({ can_cancel: true }), card, busy: false,
        cancelAction: action("courier-cancel", "Solicitar cancelamento da corrida") },
    });
    const cancel = () => wrapper.find("[data-pos-courier-cancel]");
    expect(cancel().text()).toBe("Cancelar a corrida");
    await cancel().trigger("click");
    expect(wrapper.emitted("cancel")).toBeUndefined();
    expect(cancel().text()).toBe("Confirmar o cancelamento?");
    await cancel().trigger("click");
    expect(wrapper.emitted("cancel")).toHaveLength(1);
  });

  it("depois da coleta (sem can_cancel) não há Cancelar a corrida", async () => {
    const wrapper = await mountSuspended(PosCourierPanel, {
      props: { courier: courier({ status: "E", can_cancel: false }), card, busy: false,
        cancelAction: action("courier-cancel", "Solicitar cancelamento da corrida", false) },
    });
    expect(wrapper.find("[data-pos-courier-cancel]").exists()).toBe(false);
  });

  it("Entregador voltou mostra a lista do que deve estar na mão e fecha a saída no Conferido", async () => {
    const lines = ["A Maquininha Azul", "R$ 22,00 de troco"];
    const wrapper = await mountSuspended(PosCourierPanel, {
      props: { courier: courier({ status: "E", status_label: "Saiu para entrega" }), card, busy: false,
        backAction: action("courier-back", "Entregador voltou"), returnLines: lines },
    });
    const returned = wrapper.find("[data-pos-courier-returned]");
    expect(returned.text()).toBe("Entregador voltou");
    await returned.trigger("click");
    expect(wrapper.findAll("[data-pos-courier-back-lines] li").map((li) => li.text())).toEqual(lines);
    expect(wrapper.find("[data-pos-courier-back-different]").text()).toContain("Gestor de pedidos");
    // Voltar desarma sem gravar.
    await wrapper.find("[data-pos-courier-back-cancel]").trigger("click");
    expect(wrapper.emitted("back")).toBeUndefined();
    await wrapper.find("[data-pos-courier-returned]").trigger("click");
    await wrapper.find("[data-pos-courier-back-done]").trigger("click");
    expect(wrapper.emitted("back")).toHaveLength(1);
  });

  it("a frase que mandava cancelar e registrar a volta no Gestor saiu", async () => {
    const wrapper = await mountSuspended(PosCourierPanel, {
      props: { courier: courier({ status: "A" }), card, busy: false },
    });
    expect(wrapper.find("[data-pos-courier-gestor]").exists()).toBe(false);
    expect(wrapper.text()).not.toContain("No Gestor de pedidos");
  });

  it("sem permissão (ação apagada), os botões vêm desligados", async () => {
    const wrapper = await mountSuspended(PosCourierPanel, {
      props: { courier: courier({ status: "A", can_cancel: true }), card, busy: false,
        cancelAction: action("courier-cancel", "Solicitar cancelamento da corrida", false),
        backAction: action("courier-back", "Entregador voltou", false) },
    });
    expect(wrapper.find("[data-pos-courier-cancel]").attributes("disabled")).toBeDefined();
    expect(wrapper.find("[data-pos-courier-returned]").attributes("disabled")).toBeDefined();
  });
});
