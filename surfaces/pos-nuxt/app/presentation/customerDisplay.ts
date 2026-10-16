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
import { formatBRL } from "~/utils/posIntent";
import { isWeighedLine, lineQtyLabel, lineUnits } from "~/presentation/weighed";

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
    qtyLabel: lineQtyLabel(item),
    unitDisplay: formatBRL(unitChargedQ(item)) + (isWeighedLine(item) ? "/kg" : ""),
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

/** Os três números do rodapé da venda: total, desconto e o total riscado. */
export interface SaleTotalsView {
  totalDisplay: string;
  /** "" quando não há desconto. */
  discountDisplay: string;
  /** "" quando não há desconto — riscar um número igual ao cobrado é ruído. */
  grossTotalDisplay: string;
}

/** Os números da parede, todos da revisão do servidor (já formatados). Com
 *  desconto, o total ANTES dele, para ser riscado. */
export function saleTotalsView(review: POSSaleReviewProjection): SaleTotalsView {
  const view: SaleTotalsView = { totalDisplay: review.total_display, discountDisplay: "", grossTotalDisplay: "" };
  if (review.discount_q > 0) {
    view.discountDisplay = review.discount_display;
    view.grossTotalDisplay = formatBRL(review.total_q + review.discount_q);
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
    totalPending: false,
    pix: null,
    changeDisplay: "",
    customerFirstName: "",
    orderRef: "",
    publishedAtMs: nowMs,
  };

  if (phase === "sale" || (phase === "payment" && !inputs.result)) {
    snapshot.items = inputs.items.map((item) => displayItemView(item, inputs.discountReasons));
    snapshot.itemCount = inputs.items.reduce((sum, item) => sum + lineUnits(item), 0);
    // O total é o do servidor ou nenhum, na venda E no pagamento (regra do
    // dono, 09/10). Na venda a fonte é a revisão silenciosa da tela de venda;
    // no pagamento, a do checkout. Sem ela (o operador acabou de lançar um
    // item, mexer no desconto ou na entrega), a parede diz que o total está
    // sendo calculado: mostrar a soma do carrinho ali seria anunciar ao
    // cliente um valor que pode mudar na frente dele. Com desconto, o total
    // ANTES dele viaja junto, para ser riscado.
    if (!inputs.review) {
      snapshot.totalPending = true;
      return snapshot;
    }
    Object.assign(snapshot, saleTotalsView(inputs.review));
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
