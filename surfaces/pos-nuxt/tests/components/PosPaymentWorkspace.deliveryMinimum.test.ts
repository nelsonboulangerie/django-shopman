import { afterEach, describe, expect, it } from "vitest";
import { mountSuspended } from "@nuxt/test-utils/runtime";

import PosPaymentWorkspace from "~/components/PosPaymentWorkspace.vue";
import { review, workspaceProps } from "../support/paymentWorkspaceProps";

// MÍNIMO DE ENTREGA: a gêmea do `DeliveryZoneRule`. Antes, a recusa só aparecia
// ao Validar, como 500, e o PDV acendia "Resultado da cobrança não confirmado"
// por um pedido que nunca existiu. Agora a review traz a frase do commit e o
// Validar trava aqui, com os dois caminhos que resolvem.

const MINIMUM = "Pedido mínimo para entrega: R$ 25,00.";
const cash = { method: "cash", amount_q: 5000, collection: "on_delivery" as const };
const cta = (wrapper: Awaited<ReturnType<typeof mountSuspended>>) =>
  wrapper.findAll("button").find((button) => /Validar|Autorizar|Atualizando/.test(button.text()));

function deliveryProps(overrides: Record<string, unknown> = {}) {
  return workspaceProps({
    fulfillmentType: "delivery",
    customerName: "Ana",
    customerPhone: "43999990001",
    review: review({
      delivery_tax_id_required: false,
      warnings: [{ code: "below_delivery_minimum", field: "items", message: MINIMUM }],
    }),
    paymentTenders: [cash],
    selectedTenderIndex: 0,
    selectedTenderMethod: "cash",
    paymentCovered: true,
    paymentRemainingQ: 0,
    ...overrides,
  });
}

describe("PosPaymentWorkspace — mínimo de entrega", () => {
  afterEach(() => { document.body.innerHTML = ""; });

  it("abaixo do mínimo, o Validar trava com a frase do commit, dita uma vez", async () => {
    const wrapper = await mountSuspended(PosPaymentWorkspace, { props: deliveryProps() });
    const notices = wrapper.find('[aria-label="Avisos"]').text();
    expect(notices.split(MINIMUM).length - 1).toBe(1);
    expect(cta(wrapper)?.attributes("disabled")).toBeDefined();

    const add = wrapper.findAll("button").find((button) => button.text().includes("Acrescentar itens"));
    await add!.trigger("click");
    expect(wrapper.emitted("back")).toBeTruthy();
    expect(wrapper.findAll("button").some((button) => button.text().includes("Trocar para retirada"))).toBe(true);
  });

  it("sem o aviso da review, libera", async () => {
    const wrapper = await mountSuspended(PosPaymentWorkspace, {
      props: deliveryProps({ review: review({ delivery_tax_id_required: false }) }),
    });
    expect(wrapper.text()).not.toContain("Pedido mínimo para entrega");
    expect(cta(wrapper)?.attributes("disabled")).toBeUndefined();
  });
});
