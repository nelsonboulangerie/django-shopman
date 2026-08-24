// Tela do cliente (customer display) — contrato do snapshot que a estação
// publica no BroadcastChannel e que a janela `/display` renderiza. O snapshot é
// SEMPRE um objeto plano e pronto para exibir (strings formatadas): o display
// não calcula preço, não busca dado e não decide política — só mostra.
import type { POSCartItem, POSProjection, POSSaleReviewProjection } from "~/types/pos";
import type { PaymentProofView } from "~/presentation/payment";
import type { PosReceiptSnapshot } from "~/presentation/receipt";

/** Em que momento da venda o cliente está olhando. */
export type CustomerDisplayPhase = "idle" | "sale" | "payment" | "result";

export interface CustomerDisplayItem {
  name: string;
  qty: number;
  unitDisplay: string;
  /** Total da linha JÁ com o desconto da linha aplicado (estimativa local). */
  totalDisplay: string;
  /** Por que o preço mudou, quando mudou: "Cortesia −10%". "" = sem desconto. */
  discountLabel: string;
}

/** PIX aguardando no balcão: QR grande + estado honesto. */
export interface CustomerDisplayPixView {
  /** `<img src>` pronto (data URI ou http). "" = gateway sem QR. */
  qrCodeSrc: string;
  /** `expired` = desistimos de confirmar sozinhos; o atendente resolve. */
  status: "waiting" | "expired";
}

export interface CustomerDisplaySnapshot {
  phase: CustomerDisplayPhase;
  shopName: string;
  items: CustomerDisplayItem[];
  itemCount: number;
  totalDisplay: string;
  /** Desconto agregado do review ("R$ 2,00"); "" quando não há. */
  discountDisplay: string;
  pix: CustomerDisplayPixView | null;
  /** Troco a devolver ("R$ 33,70"); "" quando não há. */
  changeDisplay: string;
  /** Primeiro nome do cliente vinculado, para o obrigado. "" = sem vínculo. */
  customerFirstName: string;
  orderRef: string;
  publishedAtMs: number;
}

/** O que a tela de venda congela do resultado para o display (subset do `result`). */
export interface PosDisplayResult {
  payment: PaymentProofView | null;
  receipt: PosReceiptSnapshot;
}

/**
 * Fontes vivas da tela de venda, lidas por GETTER (nunca refs crus: `Ref` é
 * invariante e obrigaria a tela a estreitar os tipos dela). Montado UMA vez no
 * setup do `index.vue` e entregue ao `<PosDisplayPublisher>` — a integração na
 * tela de venda fica nessas duas linhas.
 */
export interface PosDisplaySources {
  pos: () => POSProjection | null;
  items: () => POSCartItem[];
  review: () => POSSaleReviewProjection | null;
  result: () => PosDisplayResult | null;
  pixStatus: () => "idle" | "polling" | "paid" | "expired";
  paymentChangeQ: () => number;
  checkoutMode: () => boolean;
}
