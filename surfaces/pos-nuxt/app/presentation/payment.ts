// Presentation — payment screen shaping (spec §2.4, Odoo-style tender injection).
//
// Pure transforms for the payment screen: the method affordances, the tender
// line views, the "remaining/change/covered" math, the cash quick-add presets,
// and the digital payment proof (PIX QR / card checkout link). Zero policy: the
// orchestrator's `review` is authoritative for the total; remaining/change/
// covered here are a UX gate over the operator's tender draft, recomputed live
// so the screen can disable Finalize until the total is covered. The backend
// re-derives and seals everything on review/commit.

import type {
  POSCheckoutContractProjection,
  POSPaymentCollectionProjection,
  POSPaymentMethodProjection,
  POSPaymentResultProjection,
  POSPaymentTenderDraft,
} from "~/types/pos";
import { formatBRL } from "~/utils/posIntent";

const PAYMENT_ICONS: Record<string, string> = {
  cash: "lucide:banknote",
  pix: "lucide:qr-code",
  card: "lucide:credit-card",
  mixed: "lucide:layers",
  external: "lucide:ellipsis",
  account: "lucide:book-user",
};

/** O método "em conta", que só existe para cliente com conta na casa. */
export const ACCOUNT_METHOD: POSPaymentMethodProjection = { ref: "account", label: "Em conta" };

export function paymentIcon(ref: string): string {
  return PAYMENT_ICONS[ref] || "lucide:wallet";
}

/**
 * Methods the operator can inject as a tender. The derived "mixed" pseudo-method
 * is never a button — the method is derived from the set of tenders, not picked
 * (see `resolvePayment`).
 */
export function injectableMethods(
  methods: POSPaymentMethodProjection[],
  options: { houseAccount?: boolean } = {},
): POSPaymentMethodProjection[] {
  const base = methods.filter((method) => method.ref !== "mixed" && method.ref !== ACCOUNT_METHOD.ref);
  // "Em conta" só aparece para cliente com conta na casa: dado opcional faz a
  // tela crescer; sem a flag a opção nem existe (e o servidor recusa de todo jeito).
  return options.houseAccount ? [...base, ACCOUNT_METHOD] : base;
}

// Fallback pt-BR quando o contrato não conhece o ref — o operador nunca deve
// ler um ref cru tipo "external" numa linha de pagamento.
const METHOD_LABEL_FALLBACKS: Record<string, string> = {
  cash: "Dinheiro",
  pix: "Pix",
  card: "Cartão",
  mixed: "Misto",
  external: "Outro meio",
  account: "Em conta",
};

export function methodLabel(ref: string, methods: POSPaymentMethodProjection[]): string {
  return methods.find((method) => method.ref === ref)?.label
    || METHOD_LABEL_FALLBACKS[ref]
    || "Outro meio";
}

export function tenderSumQ(tenders: POSPaymentTenderDraft[]): number {
  return tenders.reduce((sum, tender) => sum + (tender.amount_q || 0), 0);
}

/**
 * Amount still due. Can go negative once overpaid (cash change) — clamp at the
 * call site for display. Driven by the authoritative `totalQ` from the review.
 */
export function paymentRemainingQ(tenders: POSPaymentTenderDraft[], totalQ: number): number {
  return totalQ - tenderSumQ(tenders);
}

/** Soma das linhas em espécie — a única origem possível de troco. */
export function cashTenderSumQ(tenders: POSPaymentTenderDraft[]): number {
  return tenders.reduce((sum, tender) => sum + (tender.method === "cash" ? tender.amount_q || 0 : 0), 0);
}

/**
 * Troco = o excedente que veio EM DINHEIRO. Somar todas as linhas fazia o PDV
 * anunciar troco por um cartão digitado a mais — numa venda de R$ 42,00 com
 * R$ 5.000,00 na linha do cartão ele mandava devolver R$ 4.958,00 da gaveta.
 * Cartão e Pix cobram o que foi passado na maquininha; não há troco neles.
 */
export function paymentChangeQ(tenders: POSPaymentTenderDraft[], totalQ: number): number {
  return Math.min(Math.max(0, tenderSumQ(tenders) - totalQ), cashTenderSumQ(tenders));
}

/**
 * Excedente em linhas que NÃO são dinheiro: erro de digitação a corrigir, nunca
 * troco. Alimenta o aviso da tela (o servidor manda o mesmo em `warnings`).
 */
export function nonCashExcessQ(tenders: POSPaymentTenderDraft[], totalQ: number): number {
  const excess = Math.max(0, tenderSumQ(tenders) - totalQ);
  return excess - Math.min(excess, cashTenderSumQ(tenders));
}

/** UX gate: at least one tender and the total fully covered. */
export function isPaymentCovered(tenders: POSPaymentTenderDraft[], totalQ: number): boolean {
  return tenders.length > 0 && paymentRemainingQ(tenders, totalQ) <= 0;
}

export interface TenderLineView {
  method: string;
  label: string;
  icon: string;
  amountQ: number;
  amountDisplay: string;
}

export function tenderLineView(
  tender: POSPaymentTenderDraft,
  methods: POSPaymentMethodProjection[],
): TenderLineView {
  return {
    method: tender.method,
    label: methodLabel(tender.method, methods),
    icon: paymentIcon(tender.method),
    amountQ: tender.amount_q,
    amountDisplay: formatBRL(tender.amount_q),
  };
}

// The Brazilian cash notes, in cents — the fallback when the channel contract
// does not carry a denomination set. These are the bills the customer hands
// over: tapping a note ADDS it to the received amount (Odoo's +10/+20/+50
// pattern), so two R$50 notes = two taps; "Limpar" resets.
const BRL_CASH_NOTES_Q = [200, 500, 1000, 2000, 5000, 10000];

/**
 * O trilho de cédulas do checkout, vindo do CONTRATO
 * (`cash_tender_delta_presets_q`, só valores positivos) — policy mora na
 * Projection, nunca na tela. Sem contrato (ou vazio), as cédulas BR padrão.
 */
export function cashNotesQ(contract: POSCheckoutContractProjection | null = null): number[] {
  const presets = contract?.cash_tender_delta_presets_q;
  const positive = Array.isArray(presets) ? presets.filter((value) => Number.isFinite(value) && value > 0) : [];
  return positive.length ? positive : BRL_CASH_NOTES_Q;
}

/** Collections offered for the current fulfillment type (e.g. on-delivery vs terminal). */
export function collectionsForFulfillment(
  collections: POSPaymentCollectionProjection[],
  fulfillmentType: string,
): POSPaymentCollectionProjection[] {
  return collections.filter((collection) => collection.fulfillment_types.includes(fulfillmentType as "pickup" | "delivery"));
}

export type PaymentProofTone = "info" | "warning" | "success" | "danger" | "neutral";

const PROOF_TONES: Record<string, PaymentProofTone> = {
  pending: "info",
  unavailable: "warning",
  error: "danger",
};

export interface PaymentProofView {
  method: string;
  icon: string;
  amountDisplay: string;
  status: string;
  tone: PaymentProofTone;
  message: string;
  /** Render-ready `<img src>` for the PIX QR (data URI or http), or "". */
  qrCodeSrc: string;
  copyPaste: string;
  checkoutUrl: string;
  isPix: boolean;
  isCard: boolean;
  /** Has gateway data worth surfacing (QR / copy-paste / checkout link). */
  hasProof: boolean;
}

/**
 * Normalize the gateway QR field into an `<img src>`. Efi returns the QR as a
 * base64 PNG (sometimes already a data URI); pass through http(s)/data URIs and
 * wrap a bare base64 payload. Empty in, empty out.
 */
export function qrCodeSrc(qrCode: string): string {
  if (!qrCode) return "";
  if (qrCode.startsWith("data:") || qrCode.startsWith("http")) return qrCode;
  return `data:image/png;base64,${qrCode}`;
}

/**
 * Shape the close_sale `payment` result into a render-ready proof, or null when
 * there is nothing to show (cash, or a digital method without gateway data).
 *
 * PCI SAQ A: the screen only DISPLAYS the gateway's QR / copy-paste / checkout
 * link — it never captures card data. The webhook is the authoritative return.
 */
export function paymentProofView(
  result: POSPaymentResultProjection | null | undefined,
): PaymentProofView | null {
  if (!result || !result.method) return null;
  const method = result.method;
  if (method !== "pix" && method !== "card") return null;
  const qrSrc = qrCodeSrc(result.qr_code || "");
  const copyPaste = result.copy_paste || "";
  const checkoutUrl = result.checkout_url || "";
  return {
    method,
    icon: paymentIcon(method),
    amountDisplay: result.amount_display || "",
    status: result.status || "",
    tone: PROOF_TONES[result.status || ""] || "neutral",
    message: result.message || "",
    qrCodeSrc: qrSrc,
    copyPaste,
    checkoutUrl,
    isPix: method === "pix",
    isCard: method === "card",
    hasProof: Boolean(qrSrc || copyPaste || checkoutUrl),
  };
}
