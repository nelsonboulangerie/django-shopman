import { describe, expect, it } from "vitest";
import { orderPaymentGuidance, paymentCollectionLabel, collectionsForFulfillment } from "../app/presentation/payment";
import type { POSPaymentCollectionProjection } from "../app/types/pos";

const collections: POSPaymentCollectionProjection[] = [
  { ref: "terminal", label: "Receber no caixa", description: "", fulfillment_types: ["pickup", "delivery"], payment_method_refs: ["cash", "pix", "link"] },
  { ref: "on_delivery", label: "Receber ao entregar o pedido", description: "", fulfillment_types: ["pickup", "delivery"], payment_method_refs: ["cash", "credit", "debit"] },
];

describe("pagamento da encomenda pelo contrato existente", () => {
  it("preserva o balcão e só oferece pagamento na retirada para encomendas", () => {
    expect(paymentCollectionLabel(collections[0]!, "counter")).toBe("Receber no caixa");
    expect(orderPaymentGuidance({ salesMode: "counter", fulfillmentType: "pickup", collection: "terminal", methods: [] })).toBe("");
    expect(collectionsForFulfillment(collections, "pickup", "counter").map((entry) => entry.ref)).toEqual(["terminal"]);
    expect(collectionsForFulfillment(collections, "pickup", "order").map((entry) => entry.ref)).toEqual(["terminal", "on_delivery"]);
    expect(paymentCollectionLabel(collections[1]!, "order", "pickup")).toBe("Na retirada");
    expect(orderPaymentGuidance({ salesMode: "order", fulfillmentType: "pickup", collection: "on_delivery", methods: ["cash"] })).toContain("quando o cliente buscar");
  });
  it("distingue antecipado de cobrança futura na entrega", () => {
    expect(collections.map((entry) => paymentCollectionLabel(entry, "order"))).toEqual(["No balcão", "Na entrega"]);
    expect(orderPaymentGuidance({ salesMode: "order", fulfillmentType: "delivery", collection: "on_delivery", methods: ["credit"] })).toContain("o entregador recebe e o Gestor registra");
  });
  it("explica retirada pendente via gateway sem dizer que dinheiro já foi recebido", () => {
    expect(orderPaymentGuidance({ salesMode: "order", fulfillmentType: "pickup", collection: "terminal", methods: ["cash"] })).toBe("Cobra agora, no balcão.");
    for (const method of ["pix", "link"]) {
      expect(orderPaymentGuidance({ salesMode: "order", fulfillmentType: "pickup", collection: "terminal", methods: [method] })).toContain("até o provedor confirmar");
    }
  });
});
