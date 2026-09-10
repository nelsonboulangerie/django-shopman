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
import { lineDiscountBadge, lineTotalQ, unitChargedQ } from "~/presentation/lineDiscounts";
import { cartNetTotalQ } from "~/presentation/receipt";
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
  // Mesma regra da linha do carrinho: preço do servidor, quantidade da tela.
  // O cliente lê esta tela em voz alta com o operador — os dois números têm que
  // ser o mesmo número.
  return {
    name: item.name,
    qty: item.qty,
    unitDisplay: formatBRL(unitChargedQ(item)),
    totalDisplay: formatBRL(lineTotalQ(item)),
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

/**
 * Total do carrinho ANTES do desconto manual, em centavos: o preço de
 * RESTAURAÇÃO da linha (`price_q`, que já é pós-desconto automático e
 * pré-desconto manual — ver `lineTotalQ`) × a quantidade da tela. É a mesma
 * régua do review do orquestrador, onde `total_q + discount_q` é o total antes
 * do desconto manual — as duas fontes riscam o MESMO número na parede.
 */
export function cartGrossTotalQ(items: POSCartItem[]): number {
  return items.reduce((sum, item) => sum + item.price_q * item.qty, 0);
}

/** Os três números do rodapé da venda: total, desconto e o total riscado. */
export interface SaleTotalsView {
  totalDisplay: string;
  /** "" quando não há desconto. */
  discountDisplay: string;
  /** "" quando não há desconto — riscar um número igual ao cobrado é ruído. */
  grossTotalDisplay: string;
}

/**
 * O review do orquestrador, quando existe, prevalece (é a autoridade final e
 * já vem formatado). Sem ele, a MESMA estimativa da tela de venda
 * (`cartNetTotalQ`), com o desconto medido pela mesma régua — assim o rodapé
 * não muda de história quando o review chega no "Cobrar".
 */
export function saleTotalsView(items: POSCartItem[], review: POSSaleReviewProjection | null): SaleTotalsView {
  const view: SaleTotalsView = { totalDisplay: "", discountDisplay: "", grossTotalDisplay: "" };
  view.totalDisplay = review?.total_display || formatBRL(cartNetTotalQ(items));
  if (review) {
    if (review.discount_q > 0) {
      view.discountDisplay = review.discount_display;
      view.grossTotalDisplay = formatBRL(review.total_q + review.discount_q);
    }
    return view;
  }
  const netQ = cartNetTotalQ(items);
  const grossQ = cartGrossTotalQ(items);
  if (grossQ > netQ) {
    view.discountDisplay = formatBRL(grossQ - netQ);
    view.grossTotalDisplay = formatBRL(grossQ);
  }
  return view;
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
    grossTotalDisplay: "",
    pix: null,
    changeDisplay: "",
    customerFirstName: "",
    orderRef: "",
    publishedAtMs: nowMs,
  };

  if (phase === "sale" || (phase === "payment" && !inputs.result)) {
    snapshot.items = inputs.items.map((item) => displayItemView(item, inputs.discountReasons));
    snapshot.itemCount = inputs.items.reduce((sum, item) => sum + item.qty, 0);
    // A MESMA soma da tela de venda (`cartNetTotalQ`). O review, quando existe,
    // prevalece. Com desconto, o total ANTES dele viaja junto, para ser riscado.
    Object.assign(snapshot, saleTotalsView(inputs.items, inputs.review));
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
