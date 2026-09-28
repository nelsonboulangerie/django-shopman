// Contrato da seção Encomendas — espelho de `shopman/backstage/projections/preorders.py`.
// `GET /api/v1/backstage/pos/preorders/?date_from=&date_to=&q=` e
// `GET /api/v1/backstage/pos/preorders/<ref>/` e
// `POST /api/v1/backstage/pos/preorders/<ref>/hand-over/`.

import type { POSManagerProjection, POSTabPayload } from "./pos";

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
  reschedule: PreorderReschedule;
  edit: PreorderEdit;
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
  /**
   * Pix ou link pendente que o balcão cancela ao receber: a linha que o diálogo
   * mostra antes de confirmar. "" quando não há cobrança digital viva.
   */
  digital_charge_notice: string;
}

export type CounterMethod = "cash" | "debit" | "credit";

/** Cancelar pelo PDV — a mesma régua, política e permissão do Gestor. */
export interface PreorderCancel {
  allowed: boolean;
  requires_approval: boolean;
  block_reason: string;
}

/** Reagendar pelo PDV — a régua do orquestrador (`reschedule.state_refusal`). */
export interface PreorderReschedule {
  allowed: boolean;
  block_reason: string;
  /** O combinado de hoje. */
  date: string;
  slot: string;
  /** Os itens: a janela oferecível depende deles. */
  skus: string[];
  /**
   * A base do gesto: a revisão da DATA, que é a que o reagendar confere. A
   * revisão geral do detalhe (`revision`) é outra, e mandá-la aqui fazia todo
   * reagendamento pelo PDV voltar 409.
   */
  revision: string;
}

/** Editar pelo PDV — a régua do orquestrador (`order_edit.state_refusal`). */
export interface PreorderEdit {
  allowed: boolean;
  block_reason: string;
  /** A NFC-e já saiu: o caminho é cancelar e refazer, não editar. */
  cancel_and_redo: boolean;
  /** A base da gravação da edição (revisão `edit`). */
  revision: string;
}

export interface PreorderRescheduleResponse {
  ok: boolean;
  changed: boolean;
  activated_now: boolean;
}

export interface PreorderHandOverResponse {
  ok: boolean;
  ref: string;
  received_q: number;
  status: string;
}

// ── Editar a encomenda na tela de venda (WP-E6) ─────────────────────────────

/** A encomenda como estava ao abrir a edição — para mandar só o que mudou. */
export interface OrderEditOriginal {
  items: { line_id: string; sku: string; qty: number | string }[];
  fulfillment_type: "pickup" | "delivery";
  delivery_address: string;
  delivery_address_structured: Record<string, unknown>;
  delivery_date: string;
  delivery_time_slot: string;
  order_notes: string;
  fiscal_tax_id: string;
  delivery_fee_override_q?: number | null;
}

/** O contexto da comanda virtual da edição (`POST pos/preorders/<ref>/edit-session/`). */
export interface OrderEditContext {
  order_ref: string;
  /** A revisão `edit` que a gravação confere. */
  base_revision: string;
  actor_id: number | null;
  original: OrderEditOriginal;
}

export interface OrderEditSessionResponse {
  ok: boolean;
  tab: POSTabPayload;
  edit: OrderEditContext;
}

export type OrderEditSettlementKind = "none" | "collect" | "refund_gateway" | "refund_cash" | "refund_card_machine";

export interface OrderEditPreviewItem {
  line_id: string;
  sku: string;
  name: string;
  qty: number | string;
  unit_price_q: number;
  line_total_q: number;
  is_new: boolean;
  is_delivery_fee: boolean;
}

/** A prévia da edição — a régua do servidor (`order_edit.plan`). */
export interface OrderEditPreview {
  changed: boolean;
  items_changed: boolean;
  items: OrderEditPreviewItem[];
  previous_total_q: number;
  total_q: number;
  difference_q: number;
  notes: { before: string; after: string; changed: boolean };
  fulfillment: {
    before: "pickup" | "delivery";
    after: "pickup" | "delivery";
    changed: boolean;
    delivery_address: string;
    delivery_fee_before_q: number;
    delivery_fee_after_q: number;
  };
  schedule: { changed: boolean; date: string; slot: string };
  settlement: { kind: OrderEditSettlementKind; amount_q: number; method: string };
  balance_before_q: number;
  balance_after_q: number;
  requires_manager_approval: boolean;
  /** A frase que o cliente recebe no aviso "pedido atualizado". */
  customer_note: string;
}

export interface OrderEditPreviewResponse {
  ok: boolean;
  ref: string;
  base_revision: string;
  preview: OrderEditPreview;
}

export interface OrderEditResponse {
  ok: boolean;
  changed: boolean;
  revision: number | null;
  preview: OrderEditPreview;
}
