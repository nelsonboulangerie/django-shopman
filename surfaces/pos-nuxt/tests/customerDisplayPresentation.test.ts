// Tela do cliente — a montagem do snapshot e as transições de fase são
// presentation PURA: o que o cliente vê na parede nasce aqui, e aqui se prova.
import { describe, expect, it } from "vitest";

import {
  buildCustomerDisplaySnapshot,
  type CustomerDisplayInputs,
  displayItemView,
  displayPhase,
  firstName,
  itemDiscountLabel,
} from "~/presentation/customerDisplay";
import type { PaymentProofView } from "~/presentation/payment";
import { cartNetTotalQ, type PosReceiptSnapshot } from "~/presentation/receipt";
import type { POSCartItem, POSCheckoutOptionProjection, POSSaleReviewProjection } from "~/types/pos";
import { formatBRL } from "~/utils/posIntent";

function item(overrides: Partial<POSCartItem> = {}): POSCartItem {
  return { sku: "PAO", name: "Pão francês", price_q: 500, qty: 2, notes: "", ...overrides };
}

const REASONS: POSCheckoutOptionProjection[] = [
  { ref: "cortesia", label: "Cortesia", description: "" },
  { ref: "liquidacao", label: "Liquidação", description: "" },
];

function review(overrides: Partial<POSSaleReviewProjection> = {}): POSSaleReviewProjection {
  return {
    total_display: "R$ 10,00",
    total_q: 1000,
    discount_q: 0,
    discount_display: "",
    ...overrides,
  } as POSSaleReviewProjection;
}

function receipt(overrides: Partial<PosReceiptSnapshot> = {}): PosReceiptSnapshot {
  return {
    orderRef: "PDV-001",
    tabDisplay: "1007",
    customerName: "",
    items: [],
    totalDisplay: "R$ 10,00",
    payments: [],
    fulfillmentLabel: "Retirada",
    printedAtMs: 0,
    ...overrides,
  };
}

function pixProof(overrides: Partial<PaymentProofView> = {}): PaymentProofView {
  return {
    method: "pix",
    icon: "lucide:qr-code",
    amountDisplay: "R$ 10,00",
    status: "pending",
    tone: "info",
    message: "",
    qrCodeSrc: "data:image/png;base64,abc",
    copyPaste: "000201...",
    checkoutUrl: "",
    isPix: true,
    isCard: false,
    hasProof: true,
    ...overrides,
  };
}

/** Resultado congelado do fechamento — o troco (`changeQ`) viaja dentro dele. */
function res(payment: PaymentProofView | null, receiptSnap: PosReceiptSnapshot, changeQ = 0) {
  return { payment, receipt: receiptSnap, changeQ };
}

function inputs(overrides: Partial<CustomerDisplayInputs> = {}): CustomerDisplayInputs {
  return {
    shopName: "Nelson Boulangerie",
    checkoutMode: false,
    items: [],
    review: null,
    result: null,
    pixStatus: "idle",
    discountReasons: REASONS,
    ...overrides,
  };
}

describe("firstName — o obrigado chama pelo primeiro nome", () => {
  it("corta no primeiro espaço", () => {
    expect(firstName("Maria da Silva")).toBe("Maria");
  });
  it("vazio segue vazio (obrigado sem nome)", () => {
    expect(firstName("")).toBe("");
    expect(firstName("   ")).toBe("");
  });
});

describe("itemDiscountLabel — o preço nunca muda calado", () => {
  it("usa o rótulo do contrato quando o motivo é conhecido", () => {
    const it_ = item({ discount: { value: 15, reason: "liquidacao" } });
    expect(itemDiscountLabel(it_, REASONS)).toBe("Liquidação −15%");
  });
  it("mostra o motivo cru quando o contrato não o conhece", () => {
    const it_ = item({ discount: { value: 10, reason: "Happy hour" } });
    expect(itemDiscountLabel(it_, REASONS)).toBe("Happy hour −10%");
  });
  it("sem motivo, ainda nomeia: 'Desconto'", () => {
    const it_ = item({ discount: { value: 5, reason: "" } });
    expect(itemDiscountLabel(it_, REASONS)).toBe("Desconto −5%");
  });
  it("sem desconto, sem rótulo", () => {
    expect(itemDiscountLabel(item(), REASONS)).toBe("");
  });
});

describe("displayItemView — a linha que o cliente lê", () => {
  it("formata unitário e total líquido (desconto de linha aplicado)", () => {
    const view = displayItemView(item({ qty: 2, price_q: 500, discount: { value: 10, reason: "cortesia" } }), REASONS);
    expect(view.qty).toBe(2);
    expect(view.unitDisplay).toBe(formatBRL(500));
    // 2 × 500 − 2 × 50 = 900
    expect(view.totalDisplay).toBe(formatBRL(900));
    expect(view.discountLabel).toBe("Cortesia −10%");
  });
});

describe("cartNetTotalQ — a mesma estimativa da tela de venda", () => {
  it("soma as linhas líquidas", () => {
    const items = [
      item({ qty: 2, price_q: 500 }),
      item({ sku: "CAFE", qty: 1, price_q: 300, discount: { value: 10, reason: "cortesia" } }),
    ];
    expect(cartNetTotalQ(items)).toBe(1000 + 270);
  });
});

describe("displayPhase — as transições que o cliente acompanha", () => {
  it("sem comanda e sem itens: boas-vindas", () => {
    expect(displayPhase(inputs())).toBe("idle");
  });
  it("itens no carrinho: venda em andamento (com ou sem comanda)", () => {
    expect(displayPhase(inputs({ items: [item()] }))).toBe("sale");
  });
  it("Cobrar (checkout) vira pagamento", () => {
    expect(displayPhase(inputs({ checkoutMode: true, items: [item()] }))).toBe("payment");
  });
  it("fechou em dinheiro: resultado direto (troco e obrigado)", () => {
    const result = res(null, receipt());
    expect(displayPhase(inputs({ result }))).toBe("result");
  });
  it("fechou em PIX: SEGUE em pagamento enquanto o QR aguarda", () => {
    const result = res(pixProof(), receipt());
    expect(displayPhase(inputs({ result, pixStatus: "polling" }))).toBe("payment");
  });
  it("PIX confirmado: vira resultado", () => {
    const result = res(pixProof(), receipt());
    expect(displayPhase(inputs({ result, pixStatus: "paid" }))).toBe("result");
  });
  it("PIX expirado: continua em pagamento (o atendente resolve na frente do cliente)", () => {
    const result = res(pixProof(), receipt());
    expect(displayPhase(inputs({ result, pixStatus: "expired" }))).toBe("payment");
  });
  it("a próxima venda derruba o resultado: comanda nova com itens volta a 'sale'", () => {
    expect(displayPhase(inputs({ items: [item()], result: null }))).toBe("sale");
  });
});

describe("buildCustomerDisplaySnapshot — o que viaja para a parede", () => {
  it("idle: só a loja, nada de venda", () => {
    const snap = buildCustomerDisplaySnapshot(inputs(), 123);
    expect(snap.phase).toBe("idle");
    expect(snap.shopName).toBe("Nelson Boulangerie");
    expect(snap.items).toEqual([]);
    expect(snap.totalDisplay).toBe("");
    expect(snap.publishedAtMs).toBe(123);
  });

  it("venda: itens ao vivo + total interino líquido quando não há review", () => {
    const snap = buildCustomerDisplaySnapshot(inputs({
      items: [item({ qty: 3, price_q: 500 })],
    }));
    expect(snap.phase).toBe("sale");
    expect(snap.itemCount).toBe(3);
    expect(snap.items[0]?.name).toBe("Pão francês");
    expect(snap.totalDisplay).toBe(formatBRL(1500));
    expect(snap.discountDisplay).toBe("");
  });

  it("pagamento (pré-fechamento): o total do review prevalece e o desconto aparece", () => {
    const snap = buildCustomerDisplaySnapshot(inputs({
      checkoutMode: true,
      items: [item()],
      review: review({ total_display: "R$ 8,00", discount_q: 200, discount_display: "R$ 2,00" }),
    }));
    expect(snap.phase).toBe("payment");
    expect(snap.totalDisplay).toBe("R$ 8,00");
    expect(snap.discountDisplay).toBe("R$ 2,00");
    expect(snap.pix).toBeNull();
  });

  it("desconto zerado no review não vira linha de desconto", () => {
    const snap = buildCustomerDisplaySnapshot(inputs({
      checkoutMode: true,
      items: [item()],
      review: review({ discount_q: 0, discount_display: "R$ 0,00" }),
    }));
    expect(snap.discountDisplay).toBe("");
  });

  it("PIX aguardando: QR grande + total do gateway", () => {
    const snap = buildCustomerDisplaySnapshot(inputs({
      result: res(pixProof({ amountDisplay: "R$ 42,00" }), receipt()),
      pixStatus: "polling",
    }));
    expect(snap.phase).toBe("payment");
    expect(snap.totalDisplay).toBe("R$ 42,00");
    expect(snap.pix).toEqual({ qrCodeSrc: "data:image/png;base64,abc", status: "waiting" });
  });

  it("PIX expirado: o estado é honesto", () => {
    const snap = buildCustomerDisplaySnapshot(inputs({
      result: res(pixProof(), receipt()),
      pixStatus: "expired",
    }));
    expect(snap.pix?.status).toBe("expired");
  });

  it("resultado em dinheiro: troco congelado em destaque + obrigado com nome", () => {
    const snap = buildCustomerDisplaySnapshot(inputs({
      result: res(null, receipt({ customerName: "Maria da Silva", orderRef: "PDV-042" }), 3370),
    }));
    expect(snap.phase).toBe("result");
    expect(snap.changeDisplay).toBe(formatBRL(3370));
    expect(snap.customerFirstName).toBe("Maria");
    expect(snap.orderRef).toBe("PDV-042");
  });

  it("sem troco e sem cliente: obrigado simples, sem campos fantasmas", () => {
    const snap = buildCustomerDisplaySnapshot(inputs({
      result: res(null, receipt()),
    }));
    expect(snap.changeDisplay).toBe("");
    expect(snap.customerFirstName).toBe("");
  });

  it("o snapshot é um objeto plano: sobrevive ao structuredClone do canal", () => {
    const snap = buildCustomerDisplaySnapshot(inputs({
      items: [item({ discount: { value: 10, reason: "cortesia" } })],
    }));
    expect(structuredClone(snap)).toEqual(snap);
  });
});
