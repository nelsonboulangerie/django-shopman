// Contrato da seção Encomendas — espelho de `shopman/backstage/projections/preorders.py`.
// `GET /api/v1/backstage/pos/preorders/?date_from=&date_to=&q=` e
// `GET /api/v1/backstage/pos/preorders/<ref>/`.

export type PreorderSituation =
  | "to_pay"
  | "paid"
  | "on_account"
  | "check_payment"
  | "ready"
  | "out_for_delivery"
  | "delivered";

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
}
