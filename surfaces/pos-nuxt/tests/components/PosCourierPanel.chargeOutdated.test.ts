// P2-28: a encomenda se edita no Balcão, e a corrida da TaOn já chamada leva a
// cobrança antiga na observação. O painel diz o que a corrida leva, o de agora, e
// que cancelar para chamar de novo é no Gestor.
import { describe, expect, it } from "vitest";
import { mountSuspended } from "@nuxt/test-utils/runtime";

import PosCourierPanel from "~/components/PosCourierPanel.vue";

const COURIER = {
  provider: "machine", status: "A", status_label: "Entregador a caminho da loja", active: true,
  driver: null, tracking_url: "", confirmation_code: "", attempts_count: 0, error: null,
  can_dispatch: false, can_dispatch_again: false,
  charge_outdated: {
    sent: "Cobrar R$ 50,00 em dinheiro · troco para R$ 100,00",
    current: "Cobrar R$ 50,00 no cartão (maquininha)",
    collected: false,
  },
};

async function render(courier: Record<string, unknown> = {}) {
  return mountSuspended(PosCourierPanel, {
    props: {
      courier: { ...COURIER, ...courier },
      card: { courier_label: "Entregador a caminho da loja", courier_tone: "info" },
      busy: false,
    },
  });
}

describe("PosCourierPanel — a corrida leva a cobrança antiga", () => {
  it("diz o que a corrida leva, o de agora e onde cancelar", async () => {
    const wrapper = await render();
    const aviso = wrapper.get("[data-pos-courier-charge-outdated]").text();

    expect(aviso).toContain("O pedido mudou depois da chamada");
    expect(aviso).toContain("Na corrida: Cobrar R$ 50,00 em dinheiro · troco para R$ 100,00.");
    expect(aviso).toContain("No pedido: Cobrar R$ 50,00 no cartão (maquininha).");
    expect(aviso).toContain("no Gestor de pedidos, solicite o cancelamento e chame o entregador de novo");
  });

  it("cobrança em dia, sem aviso", async () => {
    const wrapper = await render({ charge_outdated: null });

    expect(wrapper.find("[data-pos-courier-charge-outdated]").exists()).toBe(false);
  });
});
