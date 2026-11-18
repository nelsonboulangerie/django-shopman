// WP-E2 (D-041): encomenda acima da fornada planejada da data bloqueia e só o
// gerente libera, vendo os dois números; encomenda de outro dia não oferece "Na
// retirada". A presentation só diz o que o servidor apura.
import { describe, expect, it } from "vitest";
import {
  collectionsForFulfillment,
  overPlanNumbers,
  overPlanSummary,
  planLineFact,
} from "../app/presentation/payment";
import { approvalPortrait } from "../app/utils/posIntent";
import type { POSPaymentCollectionProjection } from "../app/types/pos";

const collections: POSPaymentCollectionProjection[] = [
  { ref: "terminal", label: "Receber no caixa", description: "", fulfillment_types: ["pickup", "delivery"], payment_method_refs: ["cash", "pix"] },
  { ref: "on_delivery", label: "Receber ao entregar o pedido", description: "", fulfillment_types: ["pickup", "delivery"], payment_method_refs: ["cash", "credit"] },
];

describe("a linha da encomenda mostra a fornada da data", () => {
  it("dentro do plano: '22 planejadas para 17/11'", () => {
    expect(planLineFact(20, { planned_qty: 22, free_qty: 22 }, "2026-11-17")).toEqual({
      text: "22 planejadas para 17/11",
      over: false,
    });
  });
  it("acima do livre: a linha avisa que passa do plano", () => {
    expect(planLineFact(200, { planned_qty: 22, free_qty: 22 }, "2026-11-17")?.over).toBe(true);
  });
  it("com reservas de outras encomendas, o livre vem junto (é contra ele que se mede)", () => {
    expect(planLineFact(10, { planned_qty: 22, free_qty: 7 }, "2026-11-17")).toEqual({
      text: "22 planejadas para 17/11, 7 livres",
      over: true,
    });
  });
  it("sem lastro informado (hoje, ou SKU sem controle), a linha não inventa nada", () => {
    expect(planLineFact(3, undefined, "2026-11-17")).toBeNull();
    expect(planLineFact(3, { planned_qty: 22, free_qty: 22 }, "")).toBeNull();
  });
  it("vitrine que dura sem fornada da data: diz o livre", () => {
    expect(planLineFact(3, { planned_qty: 0, free_qty: 5 }, "2026-11-17")?.text).toBe("5 livres para 17/11");
  });
});

describe("o Validar travado diz os dois números", () => {
  const k16 = { sku: "BF", name: "Baguette de Tradition", date: "2026-11-17", requested_qty: 200, planned_qty: 22, free_qty: 22 };
  it("'200 pedidas, 22 planejadas para 17/11'", () => {
    expect(overPlanNumbers(k16)).toBe("200 pedidas, 22 planejadas para 17/11");
    expect(overPlanSummary([k16])).toBe("Baguette de Tradition: 200 pedidas, 22 planejadas para 17/11.");
  });
  it("com o livre abaixo do plano, os três números", () => {
    expect(overPlanNumbers({ ...k16, requested_qty: 10, free_qty: 7 })).toBe("10 pedidas, 22 planejadas para 17/11 (7 livres)");
  });
  it("sem linha, nada", () => {
    expect(overPlanSummary([])).toBe("");
    expect(overPlanSummary(undefined)).toBe("");
  });
  it("a copy não usa travessão", () => {
    expect(overPlanSummary([k16])).not.toMatch(/[—–]/);
  });
});

describe("encomenda de outro dia não oferece 'Na retirada'", () => {
  it("retirada de outro dia: só cobrar agora", () => {
    expect(collectionsForFulfillment(collections, "pickup", "order", true).map((c) => c.ref)).toEqual(["terminal"]);
  });
  it("retirada de hoje segue oferecendo", () => {
    expect(collectionsForFulfillment(collections, "pickup", "order", false).map((c) => c.ref)).toEqual(["terminal", "on_delivery"]);
  });
  it("a entrega de outro dia não muda (a decisão é sobre a retirada)", () => {
    expect(collectionsForFulfillment(collections, "delivery", "order", true).map((c) => c.ref)).toEqual(["terminal", "on_delivery"]);
  });
});

describe("a assinatura do gerente é do plano DESTA data", () => {
  it("trocar a data da encomenda dá outro retrato", () => {
    const base = {
      tabRef: "", tabSessionKey: "", items: [], discountType: "percent", discountValue: "",
      paymentCollection: "terminal", paymentTenders: [], customerRef: "C1", deliveryFeeOverrideQ: null,
    };
    expect(approvalPortrait({ ...base, deliveryDate: "2026-11-17" })).not.toBe(approvalPortrait({ ...base, deliveryDate: "2026-11-18" }));
  });
});
