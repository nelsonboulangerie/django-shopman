// Presentation — a venda de balcão SEM CONEXÃO (WP-PDV-SEM-CONEXAO).
//
// Transforms puros: o que pode ser vendido sem rede, o total que a tela mostra
// sem o servidor, o que fazer com cada resposta do reenvio e as frases do aviso.
// Quem guarda e reenvia é `usePosOfflineSales`; aqui não há I/O.
//
// A régua de fundo: a venda sem conexão é a MESMA venda, com o mesmo
// `client_request_id` e o mesmo `expected_total_q`. O servidor já é idempotente
// por essa chave (`close_sale`, `idempotent_replay.safe_for_offline_queue`), e é
// isso que torna o reenvio seguro: mandar duas vezes devolve o mesmo pedido.

import type { POSCartItem, POSSaleReviewProjection } from "~/types/pos";
import { cartTotalQ, formatBRL } from "~/utils/posIntent";

/** Formas que se recebem sem rede: dinheiro, e a maquininha com chip e 4G próprios. */
export const OFFLINE_PAYMENT_METHODS = ["cash", "credit", "debit", "external"] as const;

export type OfflineSaleStatus = "pending" | "conflict";

export interface OfflineSaleError {
  code: string;
  message: string;
  /** `total_changed`: o total que o servidor calculou, para o "Enviar com R$ X". */
  newTotalQ?: number;
}

/** Uma venda guardada na fila local, esperando o servidor. */
export interface OfflineSale {
  /** = `client_request_id`. É a chave do servidor e a da fila. */
  id: string;
  /** Hora em que o balcão cobrou (ISO com fuso). */
  capturedAt: string;
  /** Hora da leitura de preços que a tela usou (ISO com fuso). */
  pricesAt: string;
  /** O corpo do `close_sale`, como seria enviado com conexão. */
  body: Record<string, unknown>;
  totalQ: number;
  itemCount: number;
  paymentLabel: string;
  status: OfflineSaleStatus;
  attempts: number;
  lastError?: OfflineSaleError;
}

export interface OfflineSaleInputs {
  salesMode: "counter" | "order" | string;
  fulfillmentType: string;
  items: POSCartItem[];
  /** O desconto da VENDA digitado no Pagamento (vazio = nenhum). */
  orderDiscountValue: string;
  /** As formas lançadas (método por linha). */
  tenderMethods: string[];
  /** Cobrança na entrega/retirada: o dinheiro não entra agora. */
  paymentCollection: string;
}

/**
 * O que impede ESTA venda de seguir sem conexão, na ordem em que o operador
 * resolve. Lista vazia = pode guardar e seguir.
 *
 * Cada recusa tem dono no servidor e nenhum substituto na tela: encomenda e
 * entrega dependem de agenda, taxa e cliente; desconto passa por autorização de
 * gerente, que é conferida no servidor; Pix, cartão online e link são cobranças
 * da rede. A comanda NÃO está na lista: a aberta antes da queda fecha com a
 * revisão que a tela conhecia (se outro dispositivo a mudou, o servidor fecha só
 * as linhas cobradas aqui e o resto segue aberto na comanda; se ela já foi paga,
 * não cobra de novo e só registra ao gerente: decisão C do dono, 10/10/2026), e
 * a aberta sem conexão vira
 * venda de balcão direta.
 */
export function offlineSaleBlockers(input: OfflineSaleInputs): string[] {
  const blockers: string[] = [];
  if (input.salesMode === "order") {
    blockers.push("Encomenda só nasce com conexão.");
  } else if (input.fulfillmentType === "delivery") {
    blockers.push("Entrega só nasce com conexão.");
  }
  if (input.paymentCollection === "on_delivery") {
    blockers.push("Receber depois só com conexão. Receba agora, em dinheiro ou na maquininha.");
  }
  const discounted = input.items.some((item) => (item.discount?.value || 0) > 0)
    || Boolean(String(input.orderDiscountValue || "").trim() && Number.parseFloat(String(input.orderDiscountValue).replace(",", ".")) > 0);
  if (discounted) {
    blockers.push("Desconto precisa de conexão. Tire o desconto ou espere a conexão voltar.");
  }
  if (input.items.some((item) => !(item.price_q > 0))) {
    blockers.push("Há item sem preço na última leitura do catálogo.");
  }
  const online = input.tenderMethods.filter((method) => !(OFFLINE_PAYMENT_METHODS as readonly string[]).includes(method));
  if (online.length) {
    blockers.push(`${paymentMethodLabel(online[0] || "")} precisa de conexão. Receba em dinheiro ou na maquininha.`);
  }
  return blockers;
}

export function paymentMethodLabel(method: string): string {
  switch (method) {
    case "cash": return "Dinheiro";
    case "credit": return "Crédito";
    case "debit": return "Débito";
    case "external": return "Maquininha";
    case "pix": return "Pix";
    case "link": return "Link de pagamento";
    case "account": return "Conta da casa";
    case "card": return "Cartão online";
    default: return "Esta forma";
  }
}

/** "Dinheiro", "Dinheiro + Débito" — o rótulo da venda guardada. */
export function offlinePaymentLabel(methods: string[]): string {
  const unique = [...new Set(methods.filter(Boolean))];
  return unique.length ? unique.map(paymentMethodLabel).join(" + ") : "Dinheiro";
}

/** "14:05" na hora da loja (o relógio do dispositivo). */
export function clockLabel(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
}

/**
 * A revisão que a tela monta SEM o servidor, no mesmo formato da dele.
 *
 * Só existe para a venda que passou em `offlineSaleBlockers` (sem desconto, sem
 * taxa, sem entrega), e por isso a conta é a mesma que o servidor confere no
 * fechamento (`_payload_total_q`: soma de preço × quantidade, com a linha pesada
 * pelo preço do quilo da última leitura). O `warnings` diz de onde vieram os
 * preços: a tela nunca apresenta esse total como se o servidor o tivesse visto.
 */
export function offlineSaleReview(input: {
  items: POSCartItem[];
  tenders: Array<{ method: string; amount_q: number }>;
  intentVersion: string;
  pricesAt: string;
}): POSSaleReviewProjection {
  const totalQ = cartTotalQ(input.items);
  const tenderTotalQ = input.tenders.reduce((sum, tender) => sum + Math.max(0, tender.amount_q || 0), 0);
  const onlyCash = input.tenders.length === 1 && input.tenders[0]?.method === "cash";
  const tenderedQ = onlyCash ? tenderTotalQ : 0;
  const changeQ = onlyCash ? Math.max(0, tenderTotalQ - totalQ) : 0;
  const prices = clockLabel(input.pricesAt);
  return {
    intent_version: input.intentVersion,
    tab_ref: "",
    subtotal_q: totalQ,
    subtotal_display: formatBRL(totalQ),
    discount_q: 0,
    discount_display: formatBRL(0),
    line_discount_q: 0,
    line_discount_display: formatBRL(0),
    order_discount_q: 0,
    order_discount_display: formatBRL(0),
    delivery_fee_q: 0,
    delivery_fee_display: formatBRL(0),
    total_q: totalQ,
    total_display: formatBRL(totalQ),
    payment_method: input.tenders.length > 1 ? "mixed" : input.tenders[0]?.method || "",
    payment_collection: "terminal",
    tender_total_q: tenderTotalQ,
    tender_total_display: formatBRL(tenderTotalQ),
    tender_count: input.tenders.length,
    tendered_q: tenderedQ,
    tendered_amount_display: formatBRL(tenderedQ),
    change_q: changeQ,
    change_display: formatBRL(changeQ),
    requires_manager_approval: false,
    manager_approval_threshold_q: 0,
    approval_reasons: [],
    receipt_channels: [],
    fiscal_tax_id_requested: false,
    warnings: [{ code: "offline_prices", field: "", message: offlineTotalNote(prices) }],
    delivery_fee_source: "",
    delivery_distance_km: null,
    delivery_date: "",
    delivery_slots: [],
    offline: { prices_at: input.pricesAt },
  };
}

/** A nota que acompanha o total sem conexão. */
export function offlineTotalNote(pricesClock: string): string {
  return pricesClock
    ? `Sem conexão: total pelos preços das ${pricesClock}. A venda é enviada quando a conexão voltar.`
    : "Sem conexão: total pelos preços da última leitura. A venda é enviada quando a conexão voltar.";
}

/** Como o reenvio de UMA venda terminou. */
export type OfflineSendOutcome =
  | { kind: "sent"; orderRef: string }
  /** Rede, servidor fora ou sessão: para a rodada e tenta depois, sem marcar nada. */
  | { kind: "retry"; stop: true; reason: "network" | "server" | "session" }
  /** O servidor RECUSOU esta venda: ela fica na fila com o motivo, e a rodada segue. */
  | { kind: "conflict"; error: OfflineSaleError };

interface HttpFailure {
  status: number;
  data?: unknown;
}

/** Decide o destino de uma resposta (ou falha) do `close_sale` reenviado. */
export function classifyOfflineSend(input: { response?: unknown; failure?: HttpFailure }): OfflineSendOutcome {
  if (input.response !== undefined) {
    const body = input.response && typeof input.response === "object" ? input.response as Record<string, unknown> : {};
    const orderRef = typeof body.order_ref === "string" ? body.order_ref.trim() : "";
    if (body.ok === true && orderRef) return { kind: "sent", orderRef };
    // Resposta sem prova de pedido: não marca enviada nem recusada. O reenvio
    // com a mesma chave devolve a venda se ela tiver nascido.
    return { kind: "retry", stop: true, reason: "server" };
  }
  const failure = input.failure || { status: 0 };
  const status = Number(failure.status || 0);
  const error = (failure.data as { error?: Record<string, unknown>; detail?: string } | null)?.error;
  // Pedido criado e cobrança com desfecho incerto do lado do servidor: a venda
  // EXISTE. Sair da fila é o certo; o pedido aparece nas Últimas vendas.
  if (error?.order_created && typeof error.order_ref === "string" && error.order_ref) {
    return { kind: "sent", orderRef: error.order_ref };
  }
  if (!status || status >= 500 || status === 408 || status === 429) {
    return { kind: "retry", stop: true, reason: status ? "server" : "network" };
  }
  if (status === 401 || (status === 403 && error?.code === "station_locked")) {
    return { kind: "retry", stop: true, reason: "session" };
  }
  const code = typeof error?.code === "string" ? error.code : `http_${status}`;
  const detail = (failure.data as { detail?: string } | null)?.detail;
  const message = typeof error?.message === "string" && error.message
    ? error.message
    : typeof detail === "string" && detail
      ? detail
      : "Esta venda não entrou.";
  const context = error?.context as { new_total_q?: unknown } | undefined;
  const newTotalQ = typeof context?.new_total_q === "number" ? context.new_total_q : undefined;
  return { kind: "conflict", error: { code, message, ...(newTotalQ !== undefined ? { newTotalQ } : {}) } };
}

export interface OfflineQueueAlert {
  color: "warning" | "info" | "error";
  title: string;
  description: string;
  actionLabel: string;
}

/**
 * O aviso do cabeçalho. Sempre acionável: a ação abre a lista das vendas
 * guardadas, que diz o que cada uma espera.
 */
export function offlineQueueAlert(input: {
  online: boolean;
  pending: number;
  conflicts: number;
  sending: boolean;
}): OfflineQueueAlert | null {
  const { online, pending, conflicts, sending } = input;
  if (conflicts > 0) {
    return {
      color: "error",
      title: conflicts === 1 ? "1 venda guardada não entrou." : `${conflicts} vendas guardadas não entraram.`,
      description: "Cada uma diz por quê. O caixa só fecha depois de resolver.",
      actionLabel: "Resolver",
    };
  }
  if (!online) {
    return {
      color: "warning",
      title: pending
        ? `Sem conexão. ${pending === 1 ? "1 venda esperando envio." : `${pending} vendas esperando envio.`}`
        : "Sem conexão. O balcão continua vendendo.",
      description: pending
        ? "Elas seguem sozinhas quando a conexão voltar. Não limpe os dados do navegador."
        : "Em dinheiro e na maquininha. Pix, entrega, encomenda e desconto esperam a conexão.",
      actionLabel: pending ? "Ver vendas guardadas" : "O que funciona agora",
    };
  }
  if (pending > 0) {
    return {
      color: "info",
      title: sending
        ? `Enviando ${pending === 1 ? "1 venda guardada" : `${pending} vendas guardadas`}…`
        : `${pending === 1 ? "1 venda guardada espera" : `${pending} vendas guardadas esperam`} envio.`,
      description: "Seguem sozinhas. Repetir o envio não duplica a venda.",
      actionLabel: "Ver vendas guardadas",
    };
  }
  return null;
}

/** A frase que barra o fechamento do caixa com a fila cheia. */
export function cashCloseBlockedByQueue(pending: number): string {
  if (pending <= 0) return "";
  return pending === 1
    ? "1 venda feita sem conexão ainda não foi enviada. Envie antes de fechar o caixa."
    : `${pending} vendas feitas sem conexão ainda não foram enviadas. Envie antes de fechar o caixa.`;
}

/** O identificador curto que a tela e o recibo mostram enquanto não há pedido. */
export function offlineSaleLabel(id: string): string {
  const tail = id.replace(/[^a-zA-Z0-9]/g, "").slice(-4).toUpperCase();
  return `Sem conexão ${tail}`;
}
