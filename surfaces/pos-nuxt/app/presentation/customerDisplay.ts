// Presentation — tela do cliente (customer display, segundo monitor do balcão).
//
// Transforms puros que montam o snapshot publicado pela estação e consumido
// pela janela `/display`. Zero política: o total autoritativo é o do `review`
// do orquestrador (quando existe) ou a mesma estimativa local que a tela de
// venda mostra ao operador — o display NUNCA diverge do que a estação vê.
// Transparência de preço é regra: toda linha com desconto carrega o rótulo do
// desconto que o dado já trouxe; preço nunca muda calado na frente do cliente.

import type {
  POSCartItem,
  POSCheckoutOptionProjection,
  POSSaleReviewProjection,
} from "~/types/pos";
import type {
  CustomerDisplayItem,
  CustomerDisplayPhase,
  CustomerDisplaySnapshot,
  PosDisplayResult,
} from "~/types/customerDisplay";
import { lineDiscountBadge } from "~/presentation/lineDiscounts";
import { cartNetTotalQ, receiptLineTotalQ } from "~/presentation/receipt";
import { formatBRL } from "~/utils/posIntent";

export interface CustomerDisplayInputs {
  shopName: string;
  checkoutMode: boolean;
  items: POSCartItem[];
  review: POSSaleReviewProjection | null;
  /** O troco congelado do fechamento viaja DENTRO dele (`result.changeQ`). */
  result: PosDisplayResult | null;
  pixStatus: "idle" | "polling" | "paid" | "expired";
  /** Opções do contrato de checkout, para trocar ref de motivo por rótulo. */
  discountReasons: POSCheckoutOptionProjection[];
}

/** Primeiro nome, para o obrigado ("Maria Silva" → "Maria"). */
export function firstName(fullName: string): string {
  return (fullName || "").trim().split(/\s+/)[0] || "";
}

/** Linha pronta para o cliente ler: nome, qtd, unitário e total líquido. */
export function displayItemView(
  item: POSCartItem,
  reasons: POSCheckoutOptionProjection[],
): CustomerDisplayItem {
  const netQ = receiptLineTotalQ({
    name: item.name,
    qty: item.qty,
    price_q: item.price_q,
    discountPct: item.discount?.value || 0,
  });
  return {
    name: item.name,
    qty: item.qty,
    unitDisplay: formatBRL(item.price_q),
    totalDisplay: formatBRL(netQ),
    discountLabel: lineDiscountBadge(item, reasons),
  };
}

/**
 * A fase que o cliente vê. O resultado com PIX ainda não confirmado continua em
 * "payment" (o QR é o que importa na parede); confirmou (ou não era PIX), vira
 * "result" — troco e obrigado.
 */
export function displayPhase(inputs: {
  checkoutMode: boolean;
  items: POSCartItem[];
  result: PosDisplayResult | null;
  pixStatus: "idle" | "polling" | "paid" | "expired";
}): CustomerDisplayPhase {
  if (inputs.result) {
    const proof = inputs.result.payment;
    const pixPending = Boolean(proof?.isPix && proof?.hasProof) && inputs.pixStatus !== "paid";
    return pixPending ? "payment" : "result";
  }
  if (!inputs.items.length) return "idle";
  // Itens no carrinho = venda em andamento — com ou sem comanda (o contrato
  // permite checkout direto sem comanda, e o cliente vê a venda do mesmo jeito).
  return inputs.checkoutMode ? "payment" : "sale";
}

/** Monta o snapshot plano que viaja pelo BroadcastChannel. */
export function buildCustomerDisplaySnapshot(
  inputs: CustomerDisplayInputs,
  nowMs: number = Date.now(),
): CustomerDisplaySnapshot {
  const phase = displayPhase(inputs);
  const snapshot: CustomerDisplaySnapshot = {
    phase,
    shopName: inputs.shopName,
    items: [],
    itemCount: 0,
    totalDisplay: "",
    discountDisplay: "",
    pix: null,
    changeDisplay: "",
    customerFirstName: "",
    orderRef: "",
    publishedAtMs: nowMs,
  };

  if (phase === "sale" || (phase === "payment" && !inputs.result)) {
    snapshot.items = inputs.items.map((item) => displayItemView(item, inputs.discountReasons));
    snapshot.itemCount = inputs.items.reduce((sum, item) => sum + item.qty, 0);
    // A MESMA estimativa local da tela de venda (`cartNetTotalQ`, descontos de
    // linha aplicados). O review, quando existe, prevalece.
    snapshot.totalDisplay = inputs.review?.total_display
      || formatBRL(cartNetTotalQ(inputs.items));
    snapshot.discountDisplay = inputs.review && inputs.review.discount_q > 0
      ? inputs.review.discount_display
      : "";
    return snapshot;
  }

  if (phase === "payment" && inputs.result) {
    // PIX aguardando no balcão: total a pagar + QR grande.
    const proof = inputs.result.payment;
    snapshot.totalDisplay = proof?.amountDisplay || inputs.result.receipt.totalDisplay;
    snapshot.pix = {
      qrCodeSrc: proof?.qrCodeSrc || "",
      status: inputs.pixStatus === "expired" ? "expired" : "waiting",
    };
    return snapshot;
  }

  if (phase === "result" && inputs.result) {
    snapshot.totalDisplay = inputs.result.receipt.totalDisplay;
    snapshot.changeDisplay = inputs.result.changeQ > 0 ? formatBRL(inputs.result.changeQ) : "";
    snapshot.customerFirstName = firstName(inputs.result.receipt.customerName);
    snapshot.orderRef = inputs.result.receipt.orderRef;
  }

  return snapshot;
}
