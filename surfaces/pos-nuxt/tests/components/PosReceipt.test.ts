import { describe, expect, it } from "vitest";
import { mountSuspended } from "@nuxt/test-utils/runtime";

import PosReceipt from "~/components/PosReceipt.vue";
import type { PosReceiptSnapshot } from "~/presentation/receipt";
import { formatBRL } from "~/utils/posIntent";

const methods = [{ ref: "cash", label: "Dinheiro" }, { ref: "card", label: "Cartão" }] as never;

function receipt(overrides: Partial<PosReceiptSnapshot> = {}): PosReceiptSnapshot {
  return {
    orderRef: "PDV-042",
    tabDisplay: "",
    customerName: "",
    items: [{ name: "Pão", qty: 1, price_q: 4200, discountPct: 0 }],
    totalDisplay: formatBRL(4200),
    payments: [{ method: "cash", amount_q: 10000, collection: "terminal" }],
    fulfillmentLabel: "Retirada",
    printedAtMs: 0,
    ...overrides,
  };
}

/**
 * O recibo do navegador é o FALLBACK da bobina: tem que dizer o que o ESC/POS
 * do servidor diz — "Dinheiro R$ 42 / Recebido R$ 100 / Troco R$ 58", e
 * "PAGAMENTO PENDENTE" quando o papel sai antes do dinheiro.
 */
describe("PosReceipt — o fallback imprime como o servidor", () => {
  it("dinheiro com troco: forma pelo total, Recebido e Troco", async () => {
    const w = await mountSuspended(PosReceipt, {
      props: { receipt: receipt({ tenderedQ: 10000, changeQ: 5800 }), terminalLabel: "Caixa 1", paymentMethods: methods },
    });
    const text = w.text();
    expect(text).toContain(`Dinheiro${formatBRL(4200)}`);
    expect(text).toContain(`Recebido${formatBRL(10000)}`);
    expect(text).toContain(`Troco${formatBRL(5800)}`);
    expect(w.find("[data-payment-pending]").exists()).toBe(false);
  });

  it("cobrança na entrega: PAGAMENTO PENDENTE, sem Recebido nem Troco", async () => {
    const w = await mountSuspended(PosReceipt, {
      props: {
        receipt: receipt({ payments: [{ method: "cash", amount_q: 10000, collection: "on_delivery" }], paymentPending: true }),
        terminalLabel: "Caixa 1",
        paymentMethods: methods,
      },
    });
    expect(w.find("[data-payment-pending]").text()).toBe("*** PAGAMENTO PENDENTE ***");
    expect(w.text()).not.toContain("Recebido");
    expect(w.text()).not.toContain("Troco");
  });
});
