import { afterEach, describe, expect, it } from "vitest";
import { mountSuspended } from "@nuxt/test-utils/runtime";

import PosPaymentWorkspace from "~/components/PosPaymentWorkspace.vue";
import { workspaceProps } from "../support/paymentWorkspaceProps";

// Encomenda com saldo NA RETIRADA: quem recebe é o próprio balcão, em
// Encomendas → "Receber e entregar". O aviso mandava "registrar no Gestor" e
// levava à fila de outro app para um gesto que mora aqui (29/09/2026).
const cashOnPickup = {
  paymentCollection: "on_delivery",
  fulfillmentType: "pickup",
  paymentTenders: [{ method: "cash", amount_q: 1000, collection: "on_delivery" as const }],
};

async function abrir(overrides: Record<string, unknown>) {
  return mountSuspended(PosPaymentWorkspace, { props: workspaceProps(overrides) });
}

describe("PosPaymentWorkspace — saldo na retirada se recebe em Encomendas", () => {
  afterEach(() => { document.body.innerHTML = ""; });

  it("dinheiro na retirada aponta Encomendas, sem mandar ao Gestor", async () => {
    const avisos = (await abrir(cashOnPickup)).find('[aria-label="Avisos"]').text();

    expect(avisos).toContain("Dinheiro na retirada. Quando o cliente vier buscar, receba em Encomendas.");
    expect(avisos).not.toContain("Gestor");
  });

  it("cartão na retirada diz o mesmo", async () => {
    const avisos = (await abrir({
      ...cashOnPickup,
      paymentTenders: [{ method: "debit", amount_q: 1000, collection: "on_delivery" as const }],
    })).find('[aria-label="Avisos"]').text();

    expect(avisos).toContain("Cartão na retirada. Quando o cliente vier buscar, receba em Encomendas.");
    expect(avisos).not.toContain("Gestor");
  });

  it("na entrega o aviso continua sendo o do despacho", async () => {
    const avisos = (await abrir({ ...cashOnPickup, fulfillmentType: "delivery" }))
      .find('[aria-label="Avisos"]').text();

    expect(avisos).toContain("O troco calculado será separado no despacho");
    expect(avisos).not.toContain("Encomendas");
  });
});
