import { describe, expect, it } from "vitest";
import { mountSuspended } from "@nuxt/test-utils/runtime";

import PosPaymentWorkspace from "~/components/PosPaymentWorkspace.vue";
import { review, workspaceProps } from "../support/paymentWorkspaceProps";

/**
 * Na retirada (beta test de 05/11/2026, PDV2-05 e PDV2-11): a tela dizia "Sem
 * cobrança agora" e, ao lado, "TOTAL A COBRAR", "TROCO R$ 23,00", as cédulas e o
 * "Restante". Nada se recebe agora: o total é o que se recebe na retirada, e não
 * há troco nem nota para contar.
 */
describe("PosPaymentWorkspace: pagamento na retirada", () => {
  const naRetirada = (overrides: Record<string, unknown> = {}) => workspaceProps({
    salesMode: "order",
    paymentCollection: "on_delivery",
    review: review({ total_q: 1300, total_display: "R$ 13,00" }),
    paymentTenders: [{ method: "cash", amount_q: 3600, collection: "on_delivery" }],
    selectedTenderIndex: 0,
    selectedTenderMethod: "cash",
    paymentTotalQ: 1300,
    paymentRemainingQ: 0,
    paymentChangeQ: 2300,
    paymentCovered: true,
    ...overrides,
  });

  it("o total se chama 'A receber na retirada' e não há troco", async () => {
    const w = await mountSuspended(PosPaymentWorkspace, { props: naRetirada() });
    const total = w.find("[data-pos-total]");
    expect(total.attributes("aria-label")).toBe("A receber na retirada");
    expect(total.text()).toContain("R$ 13,00");
    expect(total.text()).not.toContain("Troco");
    expect(total.text()).not.toContain("Total a cobrar");
  });

  it("sem Restante e sem cédulas", async () => {
    const w = await mountSuspended(PosPaymentWorkspace, { props: naRetirada() });
    expect(w.text()).not.toContain("Restante");
    expect(w.find('[aria-label="Teclado de valor"]').exists()).toBe(true);
    expect(w.text()).not.toMatch(/R\$ 100,00/);
  });

  it("na entrega o rótulo diz entrega", async () => {
    const w = await mountSuspended(PosPaymentWorkspace, { props: naRetirada({ fulfillmentType: "delivery" }) });
    expect(w.find("[data-pos-total]").attributes("aria-label")).toBe("A receber na entrega");
  });

  it("no balcão nada muda: Total a cobrar e Troco", async () => {
    const w = await mountSuspended(PosPaymentWorkspace, {
      props: naRetirada({ salesMode: "counter", paymentCollection: "terminal", paymentTenders: [{ method: "cash", amount_q: 3600, collection: "terminal" }] }),
    });
    expect(w.find("[data-pos-total]").attributes("aria-label")).toBe("Troco");
  });
});
