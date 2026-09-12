import { describe, expect, it } from "vitest";
import { orderPaymentGuidance, paymentCollectionLabel, collectionsForFulfillment } from "../app/presentation/payment";
import type { POSPaymentCollectionProjection } from "../app/types/pos";

const collections: POSPaymentCollectionProjection[] = [
  { ref: "terminal", label: "Receber no caixa", description: "", fulfillment_types: ["pickup", "delivery"], payment_method_refs: ["cash", "pix", "link"] },
  { ref: "on_delivery", label: "Receber na entrega", description: "", fulfillment_types: ["delivery"], payment_method_refs: ["cash", "credit", "debit"] },
];

describe("pagamento da encomenda pelo contrato existente", () => {
  it("preserva o balcão e não oferece COD para retirada", () => {
    expect(paymentCollectionLabel(collections[0]!, "counter")).toBe("Receber no caixa");
    expect(orderPaymentGuidance({ salesMode: "counter", fulfillmentType: "pickup", collection: "terminal", methods: [] })).toBe("");
    expect(collectionsForFulfillment(collections, "pickup").map((entry) => entry.ref)).toEqual(["terminal"]);
  });
  it("distingue antecipado de cobrança futura na entrega", () => {
    expect(collections.map((entry) => paymentCollectionLabel(entry, "order"))).toEqual(["Pagamento antecipado", "Cobrar na entrega"]);
    expect(orderPaymentGuidance({ salesMode: "order", fulfillmentType: "delivery", collection: "on_delivery", methods: ["credit"] })).toContain("pendente até o acerto no Gestor");
  });
  it("explica retirada pendente via gateway sem dizer que dinheiro já foi recebido", () => {
    expect(orderPaymentGuidance({ salesMode: "order", fulfillmentType: "pickup", collection: "terminal", methods: ["cash"] })).toContain("registram recebimento agora");
    for (const method of ["pix", "link"]) {
      expect(orderPaymentGuidance({ salesMode: "order", fulfillmentType: "pickup", collection: "terminal", methods: [method] })).toContain("pendente até a confirmação automática");
    }
  });
});
