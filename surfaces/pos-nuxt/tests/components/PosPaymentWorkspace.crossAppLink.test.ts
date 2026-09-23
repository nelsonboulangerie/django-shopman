import { afterEach, describe, expect, it } from "vitest";
import { mountSuspended } from "@nuxt/test-utils/runtime";

import PosPaymentWorkspace from "~/components/PosPaymentWorkspace.vue";
import { workspaceProps } from "../support/paymentWorkspaceProps";

// O DEFEITO de 22/09/2026: o aviso mandava "registre o recebimento NO GESTOR" e
// não levava — menção, não ação, com o `ordersUrl` já no `runtimeConfig`. Aqui
// o pedido ainda não existe (é o checkout, antes do commit), então não há
// `order_ref` para apontar: a porta honesta é a FILA, e o rótulo promete a fila.
const cashOnPickup = {
  paymentCollection: "on_delivery",
  fulfillmentType: "pickup",
  paymentTenders: [{ method: "cash", amount_q: 1000, collection: "on_delivery" as const }],
};

async function abrir(overrides: Record<string, unknown>) {
  return mountSuspended(PosPaymentWorkspace, { props: workspaceProps(overrides) });
}

describe("PosPaymentWorkspace — 'no Gestor' virou porta", () => {
  afterEach(() => { document.body.innerHTML = ""; });

  it("dinheiro pendente na retirada oferece a fila do Gestor", async () => {
    const wrapper = await abrir(cashOnPickup);

    expect(wrapper.find('[aria-label="Avisos"]').text()).toContain("Registre o recebimento no Gestor");
    const link = wrapper.find("[data-notice-app-link]");
    expect(link.exists()).toBe(true);
    expect(link.text()).toContain("Abrir a fila do Gestor");
    expect(link.attributes("href")).toBeTruthy();
    // O destino é a fila, sem `ref` inventado para um pedido que não nasceu.
    expect(link.attributes("href")).not.toContain("undefined");
  });

  // Maquininha (crédito/débito) na retirada: mesma pendência, mesma porta.
  it("cartão na maquininha, na retirada, tem a mesma pendência e a mesma porta", async () => {
    const wrapper = await abrir({
      paymentCollection: "on_delivery",
      fulfillmentType: "pickup",
      paymentTenders: [{ method: "debit", amount_q: 1000, collection: "on_delivery" as const }],
    });

    expect(wrapper.find('[aria-label="Avisos"]').text()).toContain("registre o recebimento no Gestor");
    expect(wrapper.find("[data-notice-app-link]").exists()).toBe(true);
  });

  // Na ENTREGA o recebimento é no acerto do entregador, não no Gestor: o aviso
  // diz outra coisa e não deve ganhar uma porta que não serve.
  it("na entrega não há porta para o Gestor, porque o aviso não manda lá", async () => {
    const wrapper = await abrir({ ...cashOnPickup, fulfillmentType: "delivery" });

    const avisos = wrapper.find('[aria-label="Avisos"]').text();
    expect(avisos).toContain("O troco calculado será separado no despacho");
    expect(avisos).not.toContain("no Gestor");
    expect(wrapper.find("[data-notice-app-link]").exists()).toBe(false);
  });

  it("o link cross-app não escreve `_blank` na mão — quem decide é o kit", async () => {
    const wrapper = await abrir(cashOnPickup);

    expect(wrapper.html()).not.toContain('target="_blank" rel="noopener"');
    expect(wrapper.find("[data-notice-app-link]").attributes("target")).toBe("_self");
  });
});
