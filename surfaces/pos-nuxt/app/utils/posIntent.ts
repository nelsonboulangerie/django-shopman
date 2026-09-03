import type { POSCartItem, POSIntentCartState, POSPaymentTenderDraft, Action } from "~/types/pos";
import { POS_SALE_INTENT_VERSION } from "~/generated/posContract";

export { POS_SALE_INTENT_VERSION };

export function formatBRL(amountQ: number): string {
  return new Intl.NumberFormat("pt-BR", {
    style: "currency",
    currency: "BRL",
  }).format((Number.isFinite(amountQ) ? amountQ : 0) / 100);
}

export function cartTotalQ(items: POSCartItem[]): number {
  return items.reduce((sum, item) => sum + item.price_q * item.qty, 0);
}

/**
 * A identidade de uma linha nova do carrinho — `L-` + 8 caracteres.
 *
 * Quem gera é o CLIENTE, e é isto que sustenta o modelo: duas linhas do mesmo
 * SKU precisam nascer distintas aqui, na tela, no instante do toque. Deduzir a
 * identidade do SKU (como era) fazia "mais um chá" virar `qty: 2` numa linha já
 * disparada — o servidor deduplicava por `line_id` e a cozinha nunca via o
 * segundo. O servidor preserva o id que recebe.
 *
 * O formato é curto de propósito (cabe num log e num payload de comanda) e
 * estável: `crypto.randomUUID` quando existe, relógio + aleatório quando não.
 */
export function newLineId(): string {
  const random = globalThis.crypto?.randomUUID?.().replace(/-/g, "")
    ?? `${Date.now().toString(16)}${Math.random().toString(16).slice(2)}`;
  return `L-${random.slice(0, 8)}`;
}

export function moneyInputToQ(value: string): number {
  const raw = String(value || "").trim();
  const normalized = raw.includes(",") ? raw.replace(/\./g, "").replace(",", ".") : raw;
  const parsed = Number.parseFloat(normalized);
  return Number.isFinite(parsed) && parsed > 0 ? Math.round(parsed * 100) : 0;
}

export function qToMoneyInput(amountQ: number): string {
  return (Math.max(0, amountQ) / 100).toFixed(2).replace(".", ",");
}

export interface ResolvedPayment {
  paymentMethod: string;
  paymentTenders: POSPaymentTenderDraft[];
  tenderedQ: number | null;
}

/**
 * Map operator-injected tender lines onto the backend payment contract (Odoo-style:
 * no "mixed" selection — you inject amounts in different forms; the method is derived).
 * - A single cash tender covering the total → single-cash path, so overpayment becomes
 *   change (tendered_q). The backend rejects overpay inside the tenders list, so
 *   cash change only exists for a lone cash payment.
 * - A single non-cash tender → just the method; the backend builds the tender from the
 *   total (no need to replay a tender line — and the spec forbids replaying saved ones).
 * - Two or more tenders → "mixed" with the lines (they must sum to the total).
 */
export function resolvePayment(tenders: POSPaymentTenderDraft[], totalQ: number): ResolvedPayment {
  const only = tenders.length === 1 ? tenders[0] : undefined;
  if (only) {
    if (only.method === "cash" && only.amount_q >= totalQ) {
      return { paymentMethod: "cash", paymentTenders: [], tenderedQ: only.amount_q };
    }
    return { paymentMethod: only.method, paymentTenders: [], tenderedQ: null };
  }
  if (tenders.length >= 2) {
    // Strip internal fields (e.g. `_virgin`) — the intent carries only the contract shape.
    const clean = tenders.map((t) => ({
      method: t.method,
      amount_q: t.amount_q,
      collection: t.collection,
      ...(t.reference ? { reference: t.reference } : {}),
    }));
    return { paymentMethod: "mixed", paymentTenders: clean, tenderedQ: null };
  }
  return { paymentMethod: "", paymentTenders: [], tenderedQ: null };
}

export function actionHref(
  actions: Action[] | undefined,
  ref: string,
  fallback: string,
): string {
  return actions?.find((action) => action.ref === ref)?.href || fallback;
}

export function concreteActionHref(
  actions: Action[] | undefined,
  ref: string,
  fallback: string,
  params: Record<string, string>,
): string {
  let href = actionHref(actions, ref, fallback);
  for (const [key, value] of Object.entries(params)) {
    href = href.replace(`{${key}}`, encodeURIComponent(value));
  }
  return href;
}

export function buildPosSaleIntent(
  state: POSIntentCartState,
  intentVersion = POS_SALE_INTENT_VERSION,
): Record<string, unknown> {
  const payload: Record<string, unknown> = {
    intent_version: intentVersion || POS_SALE_INTENT_VERSION,
    tab_ref: state.tabRef,
    tab_session_key: state.tabSessionKey,
    items: state.items.map((item) => ({
      // A identidade viaja SEMPRE. Sem ela o servidor gerava um id novo a cada
      // save e perdia o vínculo com o ticket de KDS já disparado — era por isso
      // que ele precisava adivinhar qual linha era qual pelo SKU.
      line_id: item.line_id,
      sku: item.sku,
      name: item.name,
      qty: item.qty,
      unit_price_q: item.price_q,
      // A ETIQUETA viaja junto porque a review precisa dela para aplicar a mesma
      // regra do kernel ("maior desconto ganha"): sem saber o preço de tabela,
      // ela media o desconto manual da linha contra o preço já descontado e
      // prometia abatimento que a venda não dava.
      ...(typeof item.list_price_q === "number" ? { list_price_q: item.list_price_q } : {}),
      notes: item.notes,
      ...(item.discount && item.discount.value > 0
        ? {
            discount: {
              // O formato viaja: "percent" (0-100) ou "fixed" (reais por
              // unidade). Era fixo em "percent", e um desconto em R$ subia como
              // percentual — R$ 2,00 virava 2%.
              type: item.discount.type || "percent",
              value: item.discount.value,
              reason: item.discount.reason,
            },
          }
        : {}),
    })),
    fulfillment_type: state.fulfillmentType,
    payment_method: state.paymentMethod,
    payment_collection: state.paymentCollection,
    // Emitir ou não NÃO sobe daqui: é decisão da regra no servidor. O sinal do
    // balcão é o CPF pedido, que já viaja em `customer_tax_id`.
    receipt_channels: state.receiptChannels || [],
    client_request_id: state.clientRequestId,
  };

  if (state.customerName.trim()) payload.customer_name = state.customerName.trim();
  if (state.customerRef.trim()) payload.customer_ref = state.customerRef.trim();
  if (state.customerPhone.trim()) payload.customer_phone = state.customerPhone.replace(/\D/g, "");
  if (state.customerTaxId.trim()) payload.customer_tax_id = state.customerTaxId.replace(/\D/g, "");
  // O CPF da NOTA viaja em campo próprio: pedir documento na nota não é
  // cadastrar documento de cliente, e o checkout pode pedir outro (o do marido,
  // o da empresa) sem redefinir a identidade de ninguém.
  if (state.invoiceTaxId.trim()) payload.fiscal_tax_id = state.invoiceTaxId.replace(/\D/g, "");
  if (state.customerEmail.trim()) payload.customer_email = state.customerEmail.trim();
  if (state.customerMemoryAction.trim()) payload.customer_memory_action = state.customerMemoryAction.trim();

  // QUANDO — fato do PEDIDO, e por isso FORA do bloco de entrega.
  //
  // Estas duas linhas moravam lá dentro, e era o terceiro portão do mesmo
  // mal-entendido (os outros dois eram do servidor: a review não respondia para
  // retirada, e o commit descartava as chaves). O operador combinava quinta às
  // 10h para retirar, a tela mostrava "Amanhã, 10:00 às 10:30" — e o intent
  // subia sem data nenhuma. O pedido nascia para hoje, calado.
  if (state.deliveryDate.trim()) payload.delivery_date = state.deliveryDate.trim();
  if (state.deliveryTimeSlot.trim()) payload.delivery_time_slot = state.deliveryTimeSlot.trim();

  if (state.fulfillmentType === "delivery") {
    payload.delivery_address = state.deliveryAddress.trim();
    payload.delivery_address_structured = {
      ...state.deliveryAddressStructured,
      complement: state.deliveryComplement.trim() || state.deliveryAddressStructured.complement,
      delivery_instructions: state.deliveryInstructions.trim() || state.deliveryAddressStructured.delivery_instructions,
    };
    // A TAXA não viaja daqui. Quem a resolve é o motor de entrega do servidor
    // (zona de CEP → faixa de distância → frete grátis por valor), o mesmo que a
    // loja usa. O que sobe é só a EXCEÇÃO que o operador assumiu — e ela só
    // existe quando ele a declara: `null` significa "resolva", nunca "zero".
    if (state.deliveryFeeOverrideQ !== null) {
      payload.delivery_fee_override_q = Math.max(0, state.deliveryFeeOverrideQ);
    }
  }

  if (state.orderNotes.trim()) payload.order_notes = state.orderNotes.trim();
  if (state.paymentMethod === "mixed" && state.paymentTenders.length) payload.payment_tenders = state.paymentTenders;
  if (
    state.paymentMethod === "cash"
    && state.paymentCollection === "terminal"
    && state.tenderedQ !== null
    && state.tenderedQ > 0
  ) {
    payload.tendered_q = state.tenderedQ;
  }
  // "Troco para quanto?" só existe no dinheiro NA ENTREGA (COD) — fora dele o
  // servidor descarta; aqui nem viaja.
  if (
    state.fulfillmentType === "delivery"
    && state.paymentCollection === "on_delivery"
    && state.changeForQ > 0
  ) {
    payload.change_for_q = state.changeForQ;
  }
  if (state.receiptEmail.trim()) payload.receipt_email = state.receiptEmail.trim();
  if (state.manualDiscount) payload.manual_discount = state.manualDiscount;
  if (state.managerApproval) payload.manager_approval = state.managerApproval;

  return payload;
}
