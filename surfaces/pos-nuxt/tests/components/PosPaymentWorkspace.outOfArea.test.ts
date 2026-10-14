import { afterEach, describe, expect, it } from "vitest";
import { mountSuspended } from "@nuxt/test-utils/runtime";

import PosPaymentWorkspace from "~/components/PosPaymentWorkspace.vue";
import { review, workspaceProps } from "../support/paymentWorkspaceProps";

// FORA DA ÁREA (P1-6 dos cenários de pedido): a revisão dizia "não bloqueia,
// confira o combinado", o fechamento recusava, e a taxa combinada à mão também
// era recusada. Agora é uma regra só: sem taxa combinada, o Validar trava aqui
// com a frase do fechamento e as duas saídas; com a taxa combinada, libera, e o
// pedido guarda quem combinou.

const OUT = "Endereço fora da área de entrega (12,4 km).";
const cash = { method: "cash", amount_q: 5000, collection: "on_delivery" as const };
const cta = (wrapper: Awaited<ReturnType<typeof mountSuspended>>) =>
  wrapper.findAll("button").find((button) => /Validar|Autorizar|Atualizando/.test(button.text()));

function deliveryProps(overrides: Record<string, unknown> = {}) {
  return workspaceProps({
    fulfillmentType: "delivery",
    customerName: "Ana",
    customerPhone: "43999990001",
    review: review({
      warnings: [{ code: "delivery_out_of_area", field: "delivery_address", message: OUT }],
    }),
    paymentTenders: [cash],
    selectedTenderIndex: 0,
    selectedTenderMethod: "cash",
    paymentCovered: true,
    paymentRemainingQ: 0,
    ...overrides,
  });
}

describe("PosPaymentWorkspace — entrega fora da área", () => {
  afterEach(() => { document.body.innerHTML = ""; });

  it("sem taxa combinada, o Validar trava com a frase do fechamento, dita uma vez, e as duas saídas", async () => {
    const wrapper = await mountSuspended(PosPaymentWorkspace, { props: deliveryProps() });
    expect(wrapper.text().split(OUT).length - 1).toBe(1);
    expect(cta(wrapper)?.attributes("disabled")).toBeDefined();

    const agree = wrapper.findAll("button").find((button) => button.text().includes("Combinar taxa"));
    await agree!.trigger("click");
    expect(wrapper.emitted("update:deliveryFeeOverride")?.[0]).toEqual([true]);
    expect(wrapper.findAll("button").some((button) => button.text().includes("Trocar para retirada"))).toBe(true);
  });

  it("com a taxa combinada, libera", async () => {
    const wrapper = await mountSuspended(PosPaymentWorkspace, {
      props: deliveryProps({
        deliveryFeeOverride: true,
        deliveryFeeOverrideInput: "15,00",
        review: review({
          warnings: [{
            code: "delivery_out_of_area_agreed",
            field: "delivery_address",
            message: "Endereço fora da área de entrega, com taxa combinada por marina. Fica registrado no pedido.",
          }],
        }),
      }),
    });
    expect(wrapper.text()).toContain("taxa combinada por marina");
    expect(cta(wrapper)?.attributes("disabled")).toBeUndefined();
  });
});
