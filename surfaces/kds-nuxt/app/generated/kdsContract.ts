// AUTO-GENERATED — do not edit by hand.
// Source of truth: shopman/backstage/projections/kds.py
// Regenerate with: python manage.py export_kds_schema

/** A single item within a KDS ticket. */
export interface KDSItemProjection {
  sku: string;
  name: string;
  qty: number | string;
  notes: string;
  stock_warning: string;
}

/** A KDS ticket card (prep/picking station). */
export interface KDSTicketProjection {
  pk: number;
  order_ref: string;
  channel_icon: string;
  customer_name: string;
  fulfillment_icon: string;
  created_at_display: string;
  elapsed_seconds: number;
  target_seconds: number;
  timer_class: string;
  items: KDSItemProjection[];
  status: string;
  previous_tab_ref: string;
  is_scheduled: boolean;
  is_expedition: boolean;
  status_label: string;
  is_cancelled: boolean;
  cancelled_at_display: string;
  completed_at_display: string;
  kitchen_note: string;
  customer_note: string;
  test_order_label: string;
}

/** An order card in the Saída board (``expedition``: hand over / dispatch). */
export interface KDSExpeditionCardProjection {
  pk: number;
  order_ref: string;
  channel_icon: string;
  customer_name: string;
  fulfillment_icon: string;
  fulfillment_label: string;
  is_delivery: boolean;
  units_count: string;
  line_count: number;
  total_display: string;
  items: KDSItemProjection[];
  is_scheduled: boolean;
  is_expedition: boolean;
  advance_block_label: string;
  advance_block_reason: string;
  test_order_label: string;
}

/** Uma estação do pedido, vista da Saída: em que pé ela está com ele. */
export interface KDSExitStationChipProjection {
  station_ref: string;
  station_name: string;
  prints: boolean;
  state: string;
  state_label: string;
  paper_label: string;
  paper_failed: boolean;
  cancelled_items: number;
  can_mark_ready: boolean;
}

/** Um pedido que ainda espera alguma estação — a coluna "Em preparo" da Saída. */
export interface KDSExitPreparingCardProjection {
  pk: number;
  order_ref: string;
  channel_icon: string;
  customer_name: string;
  fulfillment_icon: string;
  fulfillment_label: string;
  is_delivery: boolean;
  fired_at_display: string;
  elapsed_seconds: number;
  stations: KDSExitStationChipProjection[];
  is_scheduled: boolean;
  test_order_label: string;
}

/** A KDS instance in the index (station selector). */
export interface KDSInstanceSummaryProjection {
  ref: string;
  name: string;
  type: string;
  type_display: string;
  active_count: number;
}

/** Top-level read model for a KDS display. */
export interface KDSBoardProjection {
  instance_ref: string;
  instance_name: string;
  instance_type: string;
  is_expedition: boolean;
  tickets: (KDSTicketProjection | KDSExpeditionCardProjection)[];
  counts: Record<string, number>;
  service_date: string;
  service_date_display: string;
  today: string;
  available_dates: string[];
  cancelled_tickets: KDSTicketProjection[];
  recent_done: KDSTicketProjection[];
  preparing: KDSExitPreparingCardProjection[];
}

/** Privacy-safe order status for a customer-facing ready board. */
export interface KDSCustomerOrderProjection {
  ref: string;
  status: string;
  status_label: string;
  updated_at_display: string;
}

/** Customer-facing KDS status split by preparation and pickup readiness. */
export interface KDSCustomerStatusProjection {
  preparing: KDSCustomerOrderProjection[];
  ready: KDSCustomerOrderProjection[];
  updated_at_display: string;
}
