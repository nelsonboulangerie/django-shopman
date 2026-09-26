// Contrato da seção Encomendas — espelho de `shopman/backstage/projections/preorders.py`.
// `GET /api/v1/backstage/pos/preorders/?date_from=&date_to=&q=` e
// `GET /api/v1/backstage/pos/preorders/<ref>/` e
// `POST /api/v1/backstage/pos/preorders/<ref>/hand-over/`.

import type { POSManagerProjection } from "./pos";

export type PreorderSituation =
  | "to_pay"
  | "paid"
  | "on_account"
  | "check_payment"
  | "ready"
  | "out_for_delivery"
  | "delivered";

/**
 * O DINHEIRO, à parte da mercadoria (a situação diz "Pronto" mesmo com saldo).
 * É o que os filtros Todas · A receber · Pagas leem. `on_account` nunca é "a
 * receber" nem "paga"; `check` (o Payman não respondeu) tem aviso próprio.
 */
export type PreorderPaymentState = "to_receive" | "paid" | "on_account" | "check";

export interface PreorderCard {
  ref: string;
  /** Número do iFood, só quando o ref não o carrega (mesma régua do Gestor). */
  channel_display_id: string;
  customer_name: string;
  channel_ref: string;
  channel_label: string;
  fulfillment_type: "pickup" | "delivery" | string;
  fulfillment_label: string;
  commitment_date: string;
  commitment_date_display: string;
  window_label: string;
  /** "HH:MM" ou "" quando não houve janela combinada. */
  window_start: string;
  status: string;
  situation: PreorderSituation;
  situation_label: string;
  payment_state: PreorderPaymentState;
  total_q: number;
  total_display: string;
  /** `null` = o Payman não respondeu; a situação diz "Conferir pagamento". */
  balance_q: number | null;
  balance_display: string;
  items_summary: string;
  items_count: number;
}

export interface PreorderDay {
  date: string;
  date_display: string;
  weekday_display: string;
  day_display: string;
  is_today: boolean;
  orders_count: number;
  total_q: number;
  total_display: string;
  /** Soma dos saldos "a receber" do dia (sem conta da casa, sem "a conferir"). */
  to_receive_q: number;
  to_receive_display: string;
  orders: PreorderCard[];
}

export interface PreorderListResponse {
  ok: boolean;
  date_from: string;
  date_to: string;
  today: string;
  query: string;
  count: number;
  total_q: number;
  total_display: string;
  to_receive_q: number;
  to_receive_display: string;
  days: PreorderDay[];
}

export interface PreorderItem {
  name: string;
  qty_display: string;
  line_total_display: string;
}

export interface PreorderDetailResponse {
  ok: boolean;
  card: PreorderCard;
  items: PreorderItem[];
  payment_method_label: string;
  delivery_address: string;
  delivery_instructions: string;
  customer_note: string;
  customer_phone: string;
  customer_phone_uri: string;
  customer_relay_phone: string;
  customer_relay_code: string;
  ticket_printed: boolean;
  /** Base das mutações: a revisão operacional do pedido e quem está identificado. */
  revision: string;
  actor_id: number | null;
  hand_over: PreorderHandOver;
  cancel: PreorderCancel;
  /** Quem pode assinar o cancelamento de pedido pago (a lista do PDV). */
  managers: POSManagerProjection[];
}

/** Entregar no balcão — a régua é do servidor (`counter_hand_over_block`). */
export interface PreorderHandOver {
  allowed: boolean;
  /** Há saldo: o gesto é receber e entregar num toque. */
  needs_payment: boolean;
  amount_q: number;
  amount_display: string;
  /** A forma que o cliente combinou, quando é de balcão; "" quando não disse. */
  suggested_method: "" | CounterMethod;
  block_reason: string;
}

export type CounterMethod = "cash" | "debit" | "credit";

/** Cancelar pelo PDV — a mesma régua, política e permissão do Gestor. */
export interface PreorderCancel {
  allowed: boolean;
  requires_approval: boolean;
  block_reason: string;
}

export interface PreorderHandOverResponse {
  ok: boolean;
  ref: string;
  received_q: number;
  status: string;
}
