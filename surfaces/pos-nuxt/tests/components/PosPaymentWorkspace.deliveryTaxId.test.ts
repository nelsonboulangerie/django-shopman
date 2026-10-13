import { afterEach, describe, expect, it } from "vitest";
import { mountSuspended } from "@nuxt/test-utils/runtime";

import PosPaymentWorkspace from "~/components/PosPaymentWorkspace.vue";
import { review, workspaceProps } from "../support/paymentWorkspaceProps";

// ENTREGA SEM CPF (decisão do dono, 13/10/2026, substitui a de 24/09): a praxe
// do delivery vale para todos os canais. Sem documento a entrega fecha e a
// NFC-e sai presencial, consumidor não identificado; o Validar não trava pelo
// CPF. O endereço completo continua exigido (a entrega precisa dele).

const cash = { method: "cash", amount_q: 5000, collection: "on_delivery" as const };
const cta = (wrapper: Awaited<ReturnType<typeof mountSuspended>>) =>
  wrapper.findAll("button").find((button) => /Validar|Autorizar|Atualizando/.test(button.text()));

function deliveryProps(overrides: Record<string, unknown> = {}) {
  return workspaceProps({
    fulfillmentType: "delivery",
    // Entrega tem destinatário: sem cliente a trava que fala é a do cadastro.
    customerName: "Ana",
    customerPhone: "43999990001",
    review: review(),
    paymentTenders: [cash],
    selectedTenderIndex: 0,
    selectedTenderMethod: "cash",
    paymentCovered: true,
    paymentRemainingQ: 0,
    ...overrides,
  });
}

describe("PosPaymentWorkspace — entrega sem CPF fecha", () => {
  afterEach(() => { document.body.innerHTML = ""; });

  it("sem CPF na nota, o Validar libera", async () => {
    const wrapper = await mountSuspended(PosPaymentWorkspace, { props: deliveryProps() });
    expect(wrapper.text()).not.toContain("falta o CPF");
    expect(cta(wrapper)?.attributes("disabled")).toBeUndefined();
  });

  it("com o CPF válido na nota, libera", async () => {
    const wrapper = await mountSuspended(PosPaymentWorkspace, {
      props: deliveryProps({ wantsCpfOnInvoice: true, invoiceTaxId: "529.982.247-25" }),
    });
    expect(cta(wrapper)?.attributes("disabled")).toBeUndefined();
  });

  it("endereço sem as partes da nota trava e leva ao endereço", async () => {
    const wrapper = await mountSuspended(PosPaymentWorkspace, {
      props: deliveryProps({
        wantsCpfOnInvoice: true,
        invoiceTaxId: "529.982.247-25",
        review: review({
          warnings: [{
            code: "delivery_address_incomplete",
            field: "delivery_address",
            message: "Para a nota fiscal da entrega, falta no endereço: o CEP.",
          }],
        }),
      }),
    });
    const notices = wrapper.find('[aria-label="Avisos"]').text();
    expect(notices).toContain("falta no endereço: o CEP.");
    // Dito uma vez só: o bloqueio fala, a ressalva da review não repete.
    expect(notices.split("falta no endereço").length - 1).toBe(1);
    expect(cta(wrapper)?.attributes("disabled")).toBeDefined();
    expect(wrapper.findAll("button").some((button) => button.text().includes("Completar endereço"))).toBe(true);
  });
});
