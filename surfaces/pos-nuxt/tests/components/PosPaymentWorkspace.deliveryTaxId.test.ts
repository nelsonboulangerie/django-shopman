import { afterEach, describe, expect, it } from "vitest";
import { mountSuspended } from "@nuxt/test-utils/runtime";

import PosPaymentWorkspace from "~/components/PosPaymentWorkspace.vue";
import { review, workspaceProps } from "../support/paymentWorkspaceProps";

// ENTREGA COM NOTA (decisão do dono, 24/09/2026): a nota da entrega não sai sem
// o CPF/CNPJ do cliente, e a recusa da SEFAZ chegava com o entregador na rua.
// O servidor diz se ESTA entrega vai com nota (`delivery_tax_id_required`); o
// Validar trava enquanto "CPF na nota" não tem um documento válido.

const cash = { method: "cash", amount_q: 5000, collection: "on_delivery" as const };
const cta = (wrapper: Awaited<ReturnType<typeof mountSuspended>>) =>
  wrapper.findAll("button").find((button) => /Validar|Autorizar|Atualizando/.test(button.text()));

function deliveryProps(overrides: Record<string, unknown> = {}) {
  return workspaceProps({
    fulfillmentType: "delivery",
    // Entrega tem destinatário: sem cliente a trava que fala é a do cadastro.
    customerName: "Ana",
    customerPhone: "43999990001",
    review: review({ delivery_tax_id_required: true }),
    paymentTenders: [cash],
    selectedTenderIndex: 0,
    selectedTenderMethod: "cash",
    paymentCovered: true,
    paymentRemainingQ: 0,
    ...overrides,
  });
}

describe("PosPaymentWorkspace — entrega com nota exige o CPF", () => {
  afterEach(() => { document.body.innerHTML = ""; });

  it("sem CPF, o Validar trava com o motivo e o toque que abre o campo", async () => {
    const wrapper = await mountSuspended(PosPaymentWorkspace, { props: deliveryProps() });

    const notices = wrapper.find('[aria-label="Avisos"]').text();
    expect(notices).toContain("Entrega com nota fiscal: falta o CPF ou CNPJ do cliente.");
    expect(notices).toContain("a retirada continua");
    expect(cta(wrapper)?.attributes("disabled")).toBeDefined();

    const fill = wrapper.findAll("button").find((button) => button.text().includes("Preencher CPF na nota"));
    await fill!.trigger("click");
    expect(wrapper.emitted("update:wantsCpfOnInvoice")?.[0]).toEqual([true]);
  });

  it("com o CPF válido na nota, libera", async () => {
    const wrapper = await mountSuspended(PosPaymentWorkspace, {
      props: deliveryProps({ wantsCpfOnInvoice: true, invoiceTaxId: "529.982.247-25" }),
    });
    expect(wrapper.text()).not.toContain("falta o CPF ou CNPJ");
    expect(cta(wrapper)?.attributes("disabled")).toBeUndefined();
  });

  it("entrega sem nota prevista não pede CPF", async () => {
    const wrapper = await mountSuspended(PosPaymentWorkspace, {
      props: deliveryProps({ review: review({ delivery_tax_id_required: false }) }),
    });
    expect(wrapper.text()).not.toContain("falta o CPF ou CNPJ");
    expect(cta(wrapper)?.attributes("disabled")).toBeUndefined();
  });

  it("endereço sem as partes da nota trava e leva ao endereço", async () => {
    const wrapper = await mountSuspended(PosPaymentWorkspace, {
      props: deliveryProps({
        wantsCpfOnInvoice: true,
        invoiceTaxId: "529.982.247-25",
        review: review({
          delivery_tax_id_required: true,
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
